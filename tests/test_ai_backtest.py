"""Backtest desde la IA: correr sin guardar, leer lo guardado, y la retención.

La pieza de fondo es la separación entre computar y persistir en
`backtest_service`. Hasta ahora correr un backtest de nivel A **guardaba
siempre**, como efecto secundario: explorar tres horizontes dejaba tres
corridas en la base y tres filas en la pantalla. Los niveles de reglas y de
cartera ya no lo hacían (`save_portfolio_run` es una función aparte), así que
esto alinea el nivel A con un patrón que ya estaba probado en el mismo repo.

Lo que estos tests fijan es que la IA pueda explorar **sin dejar rastro** y que
no exista ninguna forma de que persista.
"""
import datetime

import pytest
import sqlalchemy as sa

from app.ai import registry
from app.ai.caller import AiCaller
from app.database import Base, Session, engine, get_session

_ADMIN, _ANA, _OTRO = 1, 7, 9


@pytest.fixture()
def db():
    import app.models  # noqa: F401

    Session.remove()
    Base.metadata.create_all(engine)
    # Se limpia también lo que usan los tests de variante (activos, precios,
    # señales y las tablas anchas): sin eso, el segundo test choca contra el
    # ticker único del primero.
    tablas = ("backtest_ic_point", "backtest_quantile_stat", "backtest_run",
              "strategy_component", "strategy", "`signal`", "prices", "assets")
    anchas = ("signal_values_wide", "strategy_results_wide")

    def _limpiar(conn):
        for t in tablas:
            conn.execute(sa.text(f"DELETE FROM {t}"))
        for t in anchas:
            if sa.inspect(conn).has_table(t):
                conn.execute(sa.text(f"DELETE FROM {t}"))

    def _dropear_dinamicas():
        """Las sig_{id}/strat_res_{id} sobreviven al DELETE de las
        definiciones, y sqlite RECICLA los ids: sin esto, el segundo test
        escribe en la tabla que dejó el primero y choca contra su PK."""
        from app.models import signal_store

        sig, strat = signal_store._list_dynamic_tables()
        nombres = list(sig.values()) + list(strat.values())
        with engine.begin() as conn:
            for n in nombres:
                conn.execute(sa.text(f"DROP TABLE IF EXISTS {n}"))
        for n in nombres:
            if n in signal_store._meta.tables:
                signal_store._meta.remove(signal_store._meta.tables[n])

    _dropear_dinamicas()
    with engine.begin() as conn:
        _limpiar(conn)
    yield
    # Antes de tocar la base con otra conexión: si el test dejó una sesión
    # abierta, sqlite responde "database is locked" y el teardown se cae.
    Session.remove()
    _dropear_dinamicas()
    with engine.begin() as conn:
        _limpiar(conn)
    Session.remove()


def _estrategia(nombre="E", owner=None, publica=True) -> int:
    from app.models import Strategy

    s = get_session()
    st = Strategy(name=nombre, owner_id=owner, is_public=publica)
    s.add(st)
    s.commit()
    return st.id


def _run_guardado(strategy_id, dias_atras=0) -> int:
    """Un snapshot mínimo, como el que deja `save_backtest_run`."""
    import json

    from app.models import BacktestIcPoint, BacktestQuantileStat, BacktestRun

    s = get_session()
    r = BacktestRun(
        strategy_id=strategy_id, owner_id=_ANA, status="done",
        config=json.dumps({"horizons": [5], "n_quantiles": 10}),
        date_from=datetime.date(2024, 1, 1), date_to=datetime.date(2024, 6, 1),
        n_dates=2, duration_seconds=1.5,
        created_at=datetime.datetime.utcnow() - datetime.timedelta(days=dias_atras))
    s.add(r)
    s.commit()
    s.add(BacktestIcPoint(run_id=r.id, date=datetime.date(2024, 1, 1),
                          horizon=5, ic=0.2, spread=1.0, n_assets=30))
    s.add(BacktestIcPoint(run_id=r.id, date=datetime.date(2024, 6, 1),
                          horizon=5, ic=0.1, spread=0.5, n_assets=30))
    s.add(BacktestQuantileStat(run_id=r.id, horizon=5, quantile=10, n_dates=2,
                               mean_ret=0.03, median_ret=0.02, pct_pos=0.7))
    s.commit()
    return r.id


# ── Leer lo guardado ──────────────────────────────────────────────────────────

def test_lista_los_runs_de_una_estrategia_visible(db):
    sid = _estrategia()
    _run_guardado(sid)

    out = registry.call("list_backtest_runs", AiCaller(user_id=_ANA),
                        {"strategy_id": sid})
    assert len(out["runs"]) == 1
    assert out["runs"][0]["status"] == "done"
    assert out["runs"][0]["config"]["horizons"] == [5]


def test_no_lista_los_runs_de_una_estrategia_ajena(db):
    sid = _estrategia("privada", owner=_OTRO, publica=False)
    _run_guardado(sid)

    with pytest.raises(ValueError):
        registry.call("list_backtest_runs", AiCaller(user_id=_ANA),
                      {"strategy_id": sid})


def test_devuelve_el_resumen_de_ic_de_un_run(db):
    sid = _estrategia()
    rid = _run_guardado(sid)

    out = registry.call("get_backtest_results", AiCaller(user_id=_ANA),
                        {"run_id": rid})
    assert out["run_id"] == rid
    assert out["quantiles"][0]["mean_ret"] == 0.03
    # El IC medio de 0.2 y 0.1
    assert out["ic"][5]["mean"] == pytest.approx(0.15)


def test_no_se_leen_por_id_los_resultados_de_una_estrategia_ajena(db):
    """El run se pide por su id: sin el chequeo, alcanzaría con probar números
    para leer el backtest de una estrategia privada de otro."""
    sid = _estrategia("privada", owner=_OTRO, publica=False)
    rid = _run_guardado(sid)

    with pytest.raises(ValueError):
        registry.call("get_backtest_results", AiCaller(user_id=_ANA),
                      {"run_id": rid})


def test_un_run_inexistente_avisa(db):
    with pytest.raises(ValueError, match="no existe"):
        registry.call("get_backtest_results", AiCaller(user_id=_ANA),
                      {"run_id": 999_999})


# ── Correr sin guardar ────────────────────────────────────────────────────────

def test_la_ia_no_puede_persistir_un_backtest(db):
    """No es que esté restringido: la herramienta no existe."""
    nombres = {t.name for t in registry.all_tools()}
    assert "save_backtest_run" not in nombres
    assert "run_backtest" not in nombres


def test_la_vista_previa_no_escribe_nada(db, monkeypatch):
    """LO QUE IMPORTA de todo esto: explorar no deja rastro."""
    from app.models import BacktestRun
    from app.services import backtest_service

    sid = _estrategia()
    monkeypatch.setattr(backtest_service, "compute_backtest",
                        lambda *a, **k: {
                            "config": {"horizons": [5], "n_quantiles": 10},
                            "ic_points": [{"date": datetime.date(2024, 1, 1),
                                           "horizon": 5, "ic": 0.3,
                                           "spread": 1.0, "n_assets": 30}],
                            "quantile_stats": [{"horizon": 5, "quantile": 10,
                                                "n_dates": 1, "mean_ret": 0.05,
                                                "median_ret": 0.04,
                                                "pct_pos": 1.0}],
                            "date_from": datetime.date(2024, 1, 1),
                            "date_to": datetime.date(2024, 1, 1),
                            "n_dates": 1, "duration_seconds": 0.4})

    antes = get_session().query(BacktestRun).count()
    out = registry.call("run_backtest_preview", AiCaller(user_id=_ANA),
                        {"strategy_id": sid, "horizons": [5]})
    Session.remove()

    assert get_session().query(BacktestRun).count() == antes
    assert out["guardado"] is False
    assert "NO se guardó" in out["nota"]
    assert out["ic_in_sample"]["5"]["ic_medio"] == 0.3


def test_la_vista_previa_acota_la_cantidad_de_horizontes(db, monkeypatch):
    """Cada horizonte es una cross-section más por fecha: sin tope, una lista
    larga multiplica el cómputo de una llamada."""
    from app.services import backtest_service

    visto = {}

    def falso(strategy_id, cfg):
        visto["cfg"] = cfg
        raise ValueError("corte")

    monkeypatch.setattr(backtest_service, "compute_backtest", falso)
    sid = _estrategia()

    with pytest.raises(ValueError):
        registry.call("run_backtest_preview", AiCaller(user_id=_ANA),
                      {"strategy_id": sid, "horizons": [1, 2, 3, 4, 5, 6, 7]})
    assert len(visto["cfg"]["horizons"]) == 4


def test_la_vista_previa_respeta_la_visibilidad(db):
    sid = _estrategia("privada", owner=_OTRO, publica=False)
    with pytest.raises(ValueError):
        registry.call("run_backtest_preview", AiCaller(user_id=_ANA),
                      {"strategy_id": sid})


# ── Variante sin materializar ─────────────────────────────────────────────────

def _mundo_para_variante(n_activos=24, n_fechas=14):
    """Una estrategia con historia, dos señales y precios.

    Son 24 activos y no 2 a propósito: el IC es una correlación, así que con
    dos puntos por fecha es degenerado, y el mínimo de observaciones por
    defecto del backtest es 20. Un mundo chico haría pasar los tests por
    vacuidad (sin cross-sections que medir) en vez de por lo que dicen medir.
    """
    from app.models import (Asset, Price, SignalDefinition, signal_store)

    s = get_session()
    sid = _estrategia("Base")
    activos = [Asset(ticker=f"A{i:03d}", name=f"A{i}", price_source_id=1)
               for i in range(n_activos)]
    s.add_all(activos)
    sig_a = SignalDefinition(key="sig_a", name="A", formula_type="threshold",
                             params="{}", owner_id=_ADMIN, is_public=True)
    sig_b = SignalDefinition(key="sig_b", name="B", formula_type="threshold",
                             params="{}", owner_id=_ADMIN, is_public=True)
    s.add_all([sig_a, sig_b])
    s.commit()

    fechas = [datetime.date(2024, 1, 1) + datetime.timedelta(days=d)
              for d in range(n_fechas)]
    # Cada activo crece a un ritmo distinto: así los retornos forward difieren
    # y la correlación con el puntaje tiene algo que ordenar.
    for i, a in enumerate(activos):
        for t_i, f in enumerate(fechas):
            s.add(Price(asset_id=a.id, date=f,
                        close=100.0 + i * 0.5 + t_i * (1 + (i % 7) * 0.1)))
    s.commit()

    signal_store.ensure_signal_storage(sig_a.id)
    signal_store.ensure_signal_storage(sig_b.id)
    signal_store.ensure_strategy_storage(sid)

    # sig_b es el espejo de sig_a: sirve para comprobar que pesarla al revés
    # da lo mismo que pesar sig_a en positivo.
    valores = {activos[i].id: (i - n_activos // 2) * 8.0
               for i in range(n_activos)}

    st = signal_store.read_strat_table(s, sid)
    s.execute(st.insert(), [
        {"date": f, "asset_id": aid, "score": v, "pct": 50.0}
        for f in fechas for aid, v in valores.items()])
    for sig_id, signo in ((sig_a.id, 1.0), (sig_b.id, -1.0)):
        rt = signal_store.read_sig_table(s, sig_id)
        s.execute(rt.insert(), [
            {"date": f, "asset_id": aid, "score": v * signo}
            for f in fechas for aid, v in valores.items()])
    s.commit()
    return sid


def test_la_variante_no_crea_ni_escribe_nada(db):
    """LO CENTRAL: probar otra combinación de pesos no materializa ninguna
    estrategia. Crear una de verdad son dos ALTER TABLE sobre una tabla ancha
    compartida mas una corrida de backfill en produccion."""
    from app.models import Strategy, StrategyComponent
    from app.services import backtest_service

    sid = _mundo_para_variante()
    antes = (get_session().query(Strategy).count(),
             get_session().query(StrategyComponent).count())

    out = backtest_service.compute_variant_backtest(
        sid, [{"signal_key": "sig_a", "weight": 1}], {"horizons": [1]})
    Session.remove()

    assert (get_session().query(Strategy).count(),
            get_session().query(StrategyComponent).count()) == antes
    assert out["base"]["n_dates"] > 0
    assert out["variante"]["n_dates"] > 0


def test_la_variante_hereda_la_elegibilidad_de_la_base(db):
    """Se evalúa sobre los mismos pares (fecha, activo) que la base tiene
    puntuados: eso ES su filtro, y hace que la comparación aísle el efecto de
    los componentes en vez de mezclarlo con un cambio de universo."""
    from app.services import backtest_service

    sid = _mundo_para_variante()
    out = backtest_service.compute_variant_backtest(
        sid, [{"signal_key": "sig_a", "weight": 1}], {"horizons": [1]})

    assert out["variante"]["n_dates"] == out["base"]["n_dates"]


def test_el_peso_negativo_invierte_la_variante(db):
    """Con una sola señal, pesar −1 tiene que dar el IC opuesto al de +1. Es la
    prueba de que la variante usa la misma semántica de score que el motor
    real, incluido el divisor en valor absoluto."""
    from app.services import backtest_service

    sid = _mundo_para_variante()
    cfg = {"horizons": [1]}

    mas = backtest_service.compute_variant_backtest(
        sid, [{"signal_key": "sig_a", "weight": 1}], cfg)["variante"]
    menos = backtest_service.compute_variant_backtest(
        sid, [{"signal_key": "sig_a", "weight": -1}], cfg)["variante"]

    ic_mas = [p["ic"] for p in mas["ic_points"] if p["ic"] is not None]
    ic_menos = [p["ic"] for p in menos["ic_points"] if p["ic"] is not None]
    assert ic_mas and len(ic_mas) == len(ic_menos)
    assert all(a == pytest.approx(-b) for a, b in zip(ic_mas, ic_menos))


def test_una_senal_inexistente_avisa_con_su_nombre(db):
    from app.services import backtest_service

    sid = _mundo_para_variante()
    with pytest.raises(ValueError, match="no_existe"):
        backtest_service.compute_variant_backtest(
            sid, [{"signal_key": "no_existe", "weight": 1}])


def test_la_variante_rechaza_el_peso_cero(db):
    """Misma validación que el motor real: un componente que no aporta es un
    error de tipeo, no una intención."""
    from app.services import backtest_service

    sid = _mundo_para_variante()
    with pytest.raises(ValueError, match="no puede ser 0"):
        backtest_service.compute_variant_backtest(
            sid, [{"signal_key": "sig_a", "weight": 0}])


def test_sin_componentes_avisa(db):
    from app.services import backtest_service

    sid = _mundo_para_variante()
    with pytest.raises(ValueError, match="al menos un componente"):
        backtest_service.compute_variant_backtest(sid, [])


def test_la_herramienta_respeta_la_visibilidad(db):
    sid = _estrategia("privada", owner=_OTRO, publica=False)
    with pytest.raises(ValueError):
        registry.call("backtest_strategy_variant", AiCaller(user_id=_ANA),
                      {"strategy_id": sid,
                       "components": [{"signal_key": "sig_a", "weight": 1}]})


def test_la_herramienta_devuelve_base_y_variante_para_comparar(db):
    sid = _mundo_para_variante()
    out = registry.call("backtest_strategy_variant", AiCaller(user_id=_ANA),
                        {"strategy_id": sid,
                         "components": [{"signal_key": "sig_a", "weight": 2},
                                        {"signal_key": "sig_b", "weight": -1}],
                         "horizons": [1]})

    assert out["guardado"] is False
    assert "ic_in_sample" in out["base"] and "ic_in_sample" in out["variante"]
    # La lectura viaja con el resultado: sin eso el modelo reporta el promedio
    # como si fuera una mejora.
    assert "estabilidad" in out["variante"]
    assert "in_sample" in out["como_leerlo"]


# ── Estabilidad por tramos: la defensa contra el sobreajuste ──────────────────

def _datos_ic(valores_por_fecha):
    """Un resultado mínimo con solo lo que mira `_estabilidad`."""
    return {
        "config": {"horizons": [1]},
        "ic_points": [{"date": f, "horizon": 1, "ic": v}
                      for f, v in valores_por_fecha],
    }


def _fechas(n):
    return [datetime.date(2024, 1, 1) + datetime.timedelta(days=i)
            for i in range(n)]


def test_detecta_un_ic_que_sale_de_un_solo_tramo(db):
    """EL CASO QUE MOTIVA TODO ESTO. Un IC medio decente que en realidad viene
    de un tramo bueno y tres planos: el promedio lo esconde, los tramos lo
    muestran. Es lo que pasa cuando se prueban muchas variantes y se elige la
    que se ajustó al ruido de un período."""
    from app.ai.tools.backtest import _estabilidad

    f = _fechas(40)
    valores = [(d, 0.40) for d in f[:10]] + [(d, 0.0) for d in f[10:]]

    est = _estabilidad(_datos_ic(valores))["tramos"]["1"]

    assert est["tramos"][0]["ic_medio"] == pytest.approx(0.40)
    assert est["tramos_positivos"] == 1        # uno solo de cuatro
    assert est["ic_holdout"] == pytest.approx(0.0)


def test_una_senal_estable_se_ve_estable(db):
    from app.ai.tools.backtest import _estabilidad

    valores = [(d, 0.12) for d in _fechas(40)]
    est = _estabilidad(_datos_ic(valores))["tramos"]["1"]

    assert est["tramos_positivos"] == est["tramos_medidos"] == 4
    assert all(t["ic_medio"] == pytest.approx(0.12) for t in est["tramos"])


def test_el_holdout_es_el_ultimo_tramo(db):
    """Lo más parecido a una prueba honesta que se puede dar sin rehacer la
    elección: el final del período, que quien eligió idealmente no miró."""
    from app.ai.tools.backtest import _estabilidad

    f = _fechas(40)
    valores = [(d, 0.5) for d in f[:30]] + [(d, -0.2) for d in f[30:]]

    est = _estabilidad(_datos_ic(valores))["tramos"]["1"]
    assert est["ic_holdout"] == pytest.approx(-0.2)


def test_con_pocas_fechas_no_inventa_tramos(db):
    """Partir 5 fechas en 4 tramos daría números sin significado. Mejor decir
    que no alcanza que devolver ruido con forma de medición."""
    from app.ai.tools.backtest import _estabilidad

    out = _estabilidad(_datos_ic([(d, 0.1) for d in _fechas(5)]))
    assert out["tramos"] is None
    assert "fechas" in out["motivo"]


def test_los_tramos_cubren_todo_el_periodo_sin_huecos(db):
    """Si un tramo se comiera fechas, el promedio por tramos no reconciliaría
    con el IC total y la comparación mentiría."""
    from app.ai.tools.backtest import _estabilidad

    f = _fechas(41)          # no divisible por 4: el último tramo absorbe
    est = _estabilidad(_datos_ic([(d, 0.1) for d in f]))["tramos"]["1"]

    assert sum(t["n_fechas"] for t in est["tramos"]) == len(f)
    assert est["tramos"][0]["desde"] == str(f[0])
    assert est["tramos"][-1]["hasta"] == str(f[-1])


# ── Fechas: el bug que sqlite escondía ────────────────────────────────────────

@pytest.mark.parametrize("crudo,esperado", [
    ("2024-01-31", datetime.date(2024, 1, 31)),
    ("2024-01-31T00:00:00", datetime.date(2024, 1, 31)),
    (datetime.date(2024, 1, 31), datetime.date(2024, 1, 31)),
    (datetime.datetime(2024, 1, 31, 10, 30), datetime.date(2024, 1, 31)),
    (None, None), ("", None),
])
def test_a_fecha_normaliza_todas_las_formas(crudo, esperado):
    from app.services.backtest_service import a_fecha

    assert a_fecha(crudo) == esperado


def test_una_fecha_mal_escrita_avisa_en_castellano():
    """Antes llegaba hasta el motor y reventaba con un error de SQL."""
    from app.services.backtest_service import normalize_config

    with pytest.raises(ValueError, match="AAAA-MM-DD"):
        normalize_config({"date_from": "31/01/2024"})


def test_la_config_guarda_las_fechas_como_texto():
    """Tiene que serializarse a JSON para el snapshot del run, y un `date` no
    es JSON. Por eso la conversión va en la query, no en la config."""
    import json

    from app.services.backtest_service import normalize_config

    cfg = normalize_config({"date_from": datetime.date(2024, 1, 31)})
    assert cfg["date_from"] == "2024-01-31"
    json.dumps(cfg)


def test_la_comparacion_de_fechas_bindea_un_date_y_no_un_string(db):
    """REGRESIÓN de un bug que vivió en producción: comparar la columna `date`
    contra un string funciona en sqlite y **falla en PostgreSQL** con
    `operator does not exist: date >= character varying`. Lo pegaba también la
    pantalla de Backtest, que pasa la fecha del selector como ISO.

    Se mira la EXPRESIÓN de SQLAlchemy y no el SQL ejecutado, porque el driver
    de sqlite convierte los `date` a texto antes de bindear: a nivel de cursor
    los dos casos se ven idénticos y un test ahí pasaría por la razón
    equivocada, sin poder fallar nunca.
    """
    from app.models import signal_store
    from app.services.backtest_service import a_fecha

    sid = _mundo_para_variante()
    rt = signal_store.read_strat_table(get_session(), sid)

    bueno = rt.c.date >= a_fecha("2024-01-02")
    assert isinstance(bueno.right.value, datetime.date)

    # Lo que hacía antes, para que quede escrito qué se rompía:
    malo = rt.c.date >= "2024-01-02"
    assert isinstance(malo.right.value, str)


# ── Retención ─────────────────────────────────────────────────────────────────

def test_la_purga_borra_los_viejos_con_sus_hijas(db):
    """Cada corrida deja una fila por fecha × horizonte: sin retención la tabla
    crece para siempre."""
    from app.models import BacktestIcPoint, BacktestRun
    from app.services import backtest_service

    sid = _estrategia()
    viejo = _run_guardado(sid, dias_atras=400)
    nuevo = _run_guardado(sid, dias_atras=1)
    Session.remove()

    assert backtest_service.prune_old(180) == 1
    Session.remove()

    s = get_session()
    ids = {r.id for r in s.query(BacktestRun).all()}
    assert ids == {nuevo}
    assert s.query(BacktestIcPoint).filter(
        BacktestIcPoint.run_id == viejo).count() == 0


def test_la_purga_no_falla_si_no_hay_nada(db):
    from app.services import backtest_service

    assert backtest_service.prune_old(180) == 0
