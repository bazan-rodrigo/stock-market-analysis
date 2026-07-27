"""Ensayo del import contra la base (pantalla /admin/packs).

Lo que fija este archivo es que el informe que se ve ANTES de importar
describa lo que después realmente pasa: si dice "crea" y el import actualiza —o
al revés— la pantalla estaría mintiendo justo donde el usuario decide.
"""
import json

import pytest
import sqlalchemy as sa

from app.database import Base, Session, engine, get_session
from app.models import signal_store
from app.services import pack_service as ps


@pytest.fixture()
def db():
    import app.models  # noqa: F401
    Session.remove()
    Base.metadata.create_all(engine)
    tablas = ("strategy_component", "strategy", "`signal`", "signal_eval_log",
              "indicator_definitions", "sectors", "users")
    with engine.begin() as conn:
        for t in tablas:
            conn.execute(sa.text(f"DELETE FROM {t}"))
    yield
    sig, strat = signal_store._list_dynamic_tables()
    with engine.begin() as conn:
        for name in list(sig.values()) + list(strat.values()):
            conn.execute(sa.text(f"DROP TABLE IF EXISTS {name}"))
        for t in tablas:
            conn.execute(sa.text(f"DELETE FROM {t}"))
    for name in list(sig.values()) + list(strat.values()):
        if name in signal_store._meta.tables:
            signal_store._meta.remove(signal_store._meta.tables[name])
    Session.remove()


def _sembrar():
    from app.models import Sector
    from app.models.indicator_definition import IndicatorDefinition
    s = get_session()
    s.add(IndicatorDefinition(code="trend_daily", name="Tendencia",
                              category="tendencia", type="str", keep_history=True))
    s.add(IndicatorDefinition(code="rsi_daily", name="RSI", category="momentum",
                              type="num", keep_history=True))
    s.add(Sector(name="Technology"))
    s.commit()


PACK = {
    "spec_version": 1,
    "pack": "prueba",
    "signals": [
        {"key": "pv_tendencia", "name": "Tendencia", "indicator_key": "trend_daily",
         "formula_type": "discrete_map",
         "params": {"map": {"bullish": 100, "bearish": -100}}, "publica": True},
        {"key": "pv_rsi", "name": "RSI", "indicator_key": "rsi_daily",
         "formula_type": "range", "params": {"min": 70, "max": 30, "clamp": True},
         "publica": True},
    ],
    "strategies": [{
        "name": "PV1", "publica": True,
        "filter": {"op": "AND", "children": [
            {"cond": {"left": {"type": "attribute", "key": "sector"},
                      "operator": "in",
                      "right": {"type": "const", "value": ["Technology"]}}}]},
        "components": [{"signal_key": "pv_tendencia", "weight": 3},
                       {"signal_key": "pv_rsi", "weight": 1}],
    }],
}


def _bytes(pack) -> bytes:
    return json.dumps(pack, ensure_ascii=False).encode("utf-8")


# ── El informe ────────────────────────────────────────────────────────────────

def test_pack_nuevo_dice_que_crea_todo(db):
    _sembrar()
    informe = ps.preview_pack(PACK)

    assert informe["errors"] == []
    assert informe["summary"] == {"crea": 3, "actualiza": 0}
    assert [f["tipo"] for f in informe["rows"]] == ["Señal", "Señal", "Estrategia"]
    assert {f["accion"] for f in informe["rows"]} == {"crea"}
    assert all(f["dueno"] == "—" for f in informe["rows"])


def test_el_informe_no_escribe_nada(db):
    """Es la propiedad central de la pantalla: revisar es gratis."""
    from app.models import SignalDefinition, Strategy
    _sembrar()
    ps.preview_pack(PACK)
    s = get_session()
    assert s.query(SignalDefinition).count() == 0
    assert s.query(Strategy).count() == 0


def test_lo_que_ya_existe_dice_actualiza(db):
    _sembrar()
    ps.import_pack(_bytes(PACK))

    informe = ps.preview_pack(PACK)
    assert informe["summary"] == {"crea": 0, "actualiza": 3}


def test_el_cruce_no_distingue_mayusculas(db):
    """El import matchea por key sin distinguir caso; si el ensayo lo hiciera
    distinto diría "crea" y el import terminaría pisando algo."""
    _sembrar()
    ps.import_pack(_bytes(PACK))

    otro = json.loads(json.dumps(PACK))
    otro["signals"][0]["key"] = "PV_TENDENCIA"
    otro["strategies"][0]["name"] = "pv1"
    informe = ps.preview_pack(otro)

    assert informe["summary"]["actualiza"] == 3, [f["accion"] for f in informe["rows"]]


def test_avisa_cuando_va_a_pisar_algo_de_otro_dueño(db):
    """Lo que el validador offline no puede saber: que la key ya existe y es de
    otra persona."""
    from app.models import User
    s = get_session()
    otro = User(username="otro", role="analyst")
    otro.set_password("x")
    s.add(otro)
    s.commit()
    otro_id = otro.id
    _sembrar()
    ps.import_pack(_bytes(PACK), owner_id=otro_id)

    informe = ps.preview_pack(PACK, acting_user_id=999)
    assert any("es de otro" in a for a in informe["warnings"])
    assert all(f["dueno"] == "otro" for f in informe["rows"])

    # Para el propio dueño no hay aviso: está actualizando lo suyo
    assert not any("es de otro" in a
                   for a in ps.preview_pack(PACK, acting_user_id=otro_id)["warnings"])


def test_el_informe_detecta_lo_que_el_validador_offline_no(db):
    """Sin catálogo el indicador no se puede verificar; contra la base sí."""
    _sembrar()
    malo = json.loads(json.dumps(PACK))
    malo["signals"][0]["indicator_key"] = "no_existe"

    assert ps.validate_pack(malo, None)["errors"] == []      # offline: pasa
    assert any("no existe" in e for e in ps.preview_pack(malo)["errors"])


def test_las_filas_del_informe_tienen_la_forma_que_la_grilla_espera(db):
    _sembrar()
    for fila in ps.preview_pack(PACK)["rows"]:
        assert set(fila) == {"tipo", "nombre", "accion", "dueno", "detail",
                             "status", "estado"}


# ── El import en un paso ──────────────────────────────────────────────────────

def test_import_pack_hace_los_dos_pasos_en_orden(db):
    from app.models import SignalDefinition, Strategy
    _sembrar()

    salida = ps.import_pack(_bytes(PACK))

    assert not salida["aborted"]
    assert all(r["status"] == "ok" for r in salida["signals"])
    assert all(r["status"] == "ok" for r in salida["strategies"])
    s = get_session()
    assert s.query(SignalDefinition).count() == 2
    assert len(s.query(Strategy).one().components) == 2


def test_si_fallan_las_señales_no_se_intentan_las_estrategias(db):
    """Seguir daría una segunda lista de errores en cascada ('señal no
    encontrada' por cada componente) que tapa el problema real."""
    from app.models import Strategy
    _sembrar()
    malo = json.loads(json.dumps(PACK))
    malo["signals"][0]["indicator_key"] = "no_existe"

    salida = ps.import_pack(_bytes(malo))

    assert salida["aborted"] is True
    assert salida["strategies"] == []
    assert any(r["status"] == "error" for r in salida["signals"])
    assert get_session().query(Strategy).count() == 0


def test_import_pack_resuelve_los_atributos_por_nombre(db):
    from app.models import Sector, Strategy
    _sembrar()
    ps.import_pack(_bytes(PACK))

    sector_id = get_session().query(Sector).one().id
    arbol = json.loads(get_session().query(Strategy).one().filter_conditions)
    assert arbol["children"][0]["cond"]["right"]["value"] == [sector_id]


def test_un_xlsx_en_esta_pantalla_se_rechaza_con_mensaje(db):
    """La pantalla es del formato único; las planillas van por los ABMs."""
    assert not ps.looks_like_json(b"PK\x03\x04", "senales.xlsx")
    with pytest.raises(ps.PackError):
        ps.import_pack(b"PK\x03\x04 no soy json")


def test_el_informe_predice_las_filas_del_resultado(db):
    """(tipo, nombre) es la clave con la que la pantalla cruza el informe con
    el resultado: si no coincidieran, la tabla quedaría con filas 'sin
    ejecutar' que sí se ejecutaron."""
    _sembrar()
    previstas = {(f["tipo"], f["nombre"]) for f in ps.preview_pack(PACK)["rows"]}
    salida = ps.import_pack(_bytes(PACK))
    reales = ({("Señal", r["key"]) for r in salida["signals"]}
              | {("Estrategia", r["name"]) for r in salida["strategies"]})
    assert previstas == reales
