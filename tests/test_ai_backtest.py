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
    tablas = ("backtest_ic_point", "backtest_quantile_stat", "backtest_run",
              "strategy")
    with engine.begin() as conn:
        for t in tablas:
            conn.execute(sa.text(f"DELETE FROM {t}"))
    yield
    with engine.begin() as conn:
        for t in tablas:
            conn.execute(sa.text(f"DELETE FROM {t}"))
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
    assert out["ic"]["5"]["ic_medio"] == 0.3


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
