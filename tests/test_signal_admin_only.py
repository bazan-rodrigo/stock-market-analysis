"""Escribir señales es EXCLUSIVO de un administrador (decisión del 1-ago-2026).

Motivo (signal_service.ADMIN_ONLY_MOTIVO): el catálogo de señales es curado —
una sola implementación por concepto, para que dos estrategias sean comparables
entre sí y para que ni un analista ni una IA puedan inflarlo (cada señal cuesta
una columna en signal_values_wide y un slot del tope de 1600 de PostgreSQL,
que las columnas borradas siguen ocupando hasta reescribir la tabla).

Lo que fija este archivo es que NO quede ninguna puerta lateral: son cuatro
caminos de escritura distintos y ninguno pasa por los otros — save_signal
escribe una definición, import_signal_rows escribe la suya DIRECTAMENTE (no
llama a save_signal), y import_pack entra por su propia función. Un camino
nuevo que no llame a require_signal_admin sería el agujero.

Las ESTRATEGIAS no están alcanzadas: un analista las sigue creando.
"""
import json

import pytest
import sqlalchemy as sa

from app.database import Base, Session, engine, get_session


@pytest.fixture()
def db():
    import app.models  # noqa: F401
    from app.models import signal_store

    Session.remove()
    Base.metadata.create_all(engine)
    tables = ("strategy_component", "strategy", "`signal`",
              "signal_eval_log", "indicator_definitions")
    with engine.begin() as conn:
        for t in tables:
            conn.execute(sa.text(f"DELETE FROM {t}"))
    yield
    sig, strat = signal_store._list_dynamic_tables()
    with engine.begin() as conn:
        for name in list(sig.values()) + list(strat.values()):
            conn.execute(sa.text(f"DROP TABLE IF EXISTS {name}"))
        for t in tables:
            conn.execute(sa.text(f"DELETE FROM {t}"))
    for name in list(sig.values()) + list(strat.values()):
        if name in signal_store._meta.tables:
            signal_store._meta.remove(signal_store._meta.tables[name])
    Session.remove()


_MAP = json.dumps({"map": {"bullish": 100}})


def _add_indicator():
    from app.models.indicator_definition import IndicatorDefinition

    s = get_session()
    if not s.query(IndicatorDefinition).filter(
            IndicatorDefinition.code == "trend_daily").first():
        s.add(IndicatorDefinition(code="trend_daily", name="t", category="t",
                                  type="str", keep_history=True))
        s.commit()


def _n_senales() -> int:
    from app.models import SignalDefinition
    return get_session().query(SignalDefinition).count()


def _alta_admin(key="ao_sig", owner_id=None):
    from app.services import signal_service
    return signal_service.save_signal(
        key=key, name=key, formula_type="discrete_map", params_json=_MAP,
        indicator_key="trend_daily", is_public=True,
        acting_user_id=owner_id, acting_is_admin=True)


# ── Camino 1: alta y edición ──────────────────────────────────────────────────

def test_analista_no_puede_crear_una_senal(db):
    from app.services import signal_service
    _add_indicator()

    with pytest.raises(ValueError, match="administrador"):
        signal_service.save_signal(
            key="ao_nueva", name="x", formula_type="discrete_map",
            params_json=_MAP, indicator_key="trend_daily",
            acting_user_id=7, acting_is_admin=False)

    assert _n_senales() == 0, "no debe haber escrito nada"


def test_el_dueno_analista_tampoco_edita_su_propia_senal(db):
    """El gate es por ROL, no por propiedad: es la diferencia con el modelo
    viejo (can_edit permitía al dueño). Las señales que quedaron con dueño
    analista de antes del cambio siguen existiendo, pero solo las toca un admin."""
    from app.services import signal_service
    _add_indicator()
    sig = _alta_admin(key="ao_propia", owner_id=7)   # dueño = usuario 7

    with pytest.raises(ValueError, match="administrador"):
        signal_service.save_signal(
            key="ao_propia", name="renombrada", formula_type="discrete_map",
            params_json=_MAP, indicator_key="trend_daily", signal_id=sig.id,
            acting_user_id=7, acting_is_admin=False)

    Session.remove()
    from app.models import SignalDefinition
    assert get_session().query(SignalDefinition).get(sig.id).name == "ao_propia"


def test_el_default_es_cerrado(db):
    """Un caller que se olvida del flag NO escribe. Antes el default era
    acting_is_admin=True ("para scripts/tests") y una herramienta mal cableada
    habría escrito como admin por omisión."""
    from app.services import signal_service
    _add_indicator()

    with pytest.raises(ValueError, match="administrador"):
        signal_service.save_signal(
            key="ao_olvido", name="x", formula_type="discrete_map",
            params_json=_MAP, indicator_key="trend_daily")

    assert _n_senales() == 0


# ── Camino 2: borrado ─────────────────────────────────────────────────────────

def test_analista_no_puede_borrar_ni_la_propia(db):
    from app.services import signal_service
    _add_indicator()
    sig = _alta_admin(key="ao_borrar", owner_id=7)

    with pytest.raises(ValueError, match="administrador"):
        signal_service.delete_signal(sig.id, acting_user_id=7,
                                     acting_is_admin=False)

    assert _n_senales() == 1


# ── Camino 3: import de señales (NO pasa por save_signal) ─────────────────────

def test_import_de_senales_exige_admin(db):
    from app.services import signal_service
    _add_indicator()
    filas = [{"key": "ao_imp", "name": "imp", "indicator_key": "trend_daily",
              "formula_type": "discrete_map", "params": _MAP, "publica": "si"}]

    with pytest.raises(ValueError, match="administrador"):
        signal_service.import_signal_rows(filas, owner_id=7)

    assert _n_senales() == 0, "el import escribe la definición directo: sin el " \
                              "gate propio sería la puerta lateral"


def test_import_de_senales_por_archivo_exige_admin(db):
    from app.services import signal_service
    _add_indicator()
    pack = {"spec_version": 1, "pack": "p", "signals": [
        {"key": "ao_json", "name": "j", "indicator_key": "trend_daily",
         "formula_type": "discrete_map", "params": {"map": {"bullish": 100}}}]}

    with pytest.raises(ValueError, match="administrador"):
        signal_service.import_signals_file(
            json.dumps(pack).encode("utf-8"), "p.json", owner_id=7)

    assert _n_senales() == 0


# ── Camino 4: pack ────────────────────────────────────────────────────────────

def test_pack_con_senales_exige_admin_y_no_escribe_nada(db):
    from app.services import pack_service
    _add_indicator()
    pack = {"spec_version": 1, "pack": "p", "signals": [
        {"key": "ao_pack", "name": "p", "indicator_key": "trend_daily",
         "formula_type": "discrete_map", "params": {"map": {"bullish": 100}}}]}

    with pytest.raises(ValueError, match="administrador"):
        pack_service.import_pack(json.dumps(pack).encode("utf-8"), owner_id=7)

    assert _n_senales() == 0


def test_un_pack_solo_de_estrategias_no_esta_alcanzado(db):
    """Las estrategias siguen siendo de cualquiera: el gate es de señales."""
    from app.models import Strategy
    from app.services import pack_service
    _add_indicator()
    _alta_admin(key="ao_ref")          # la señal ya existe, la puso un admin

    pack = {"spec_version": 1, "pack": "p", "strategies": [
        {"name": "E analista", "components": [{"signal_key": "ao_ref", "weight": 1}]}]}

    salida = pack_service.import_pack(json.dumps(pack).encode("utf-8"),
                                      owner_id=7, acting_is_admin=False)

    assert not salida["aborted"]
    assert all(r["status"] == "ok" for r in salida["strategies"])
    assert get_session().query(Strategy).count() == 1


# ── El admin sigue pudiendo todo ──────────────────────────────────────────────

def test_el_admin_crea_edita_y_borra_como_siempre(db):
    from app.models import SignalDefinition
    from app.services import signal_service
    _add_indicator()

    sig = _alta_admin(key="ao_admin")
    assert _n_senales() == 1

    signal_service.save_signal(
        key="ao_admin", name="editada", formula_type="discrete_map",
        params_json=_MAP, indicator_key="trend_daily", signal_id=sig.id,
        acting_is_admin=True)
    Session.remove()
    assert get_session().query(SignalDefinition).get(sig.id).name == "editada"

    signal_service.delete_signal(sig.id, acting_is_admin=True)
    assert _n_senales() == 0


def test_un_admin_edita_la_senal_de_otro(db):
    """can_edit ya lo permitía; queda fijado porque ahora es la única regla."""
    from app.models import SignalDefinition
    from app.services import signal_service
    _add_indicator()
    sig = _alta_admin(key="ao_ajena", owner_id=7)

    signal_service.save_signal(
        key="ao_ajena", name="tocada por admin", formula_type="discrete_map",
        params_json=_MAP, indicator_key="trend_daily", signal_id=sig.id,
        acting_user_id=1, acting_is_admin=True)

    Session.remove()
    assert get_session().query(SignalDefinition).get(sig.id).name == "tocada por admin"
