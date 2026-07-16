"""Tests del optimizador de parámetros del simulador (grid search).

Codifican la metodología: grilla solo sobre condiciones activas, poda de
combos incoherentes, objetivo = retorno total compuesto en train con mínimo
de trades, validación out-of-sample en test.
"""
import pytest

from app.services.trade_optimizer import (build_axes, build_combos,
                                          describe_spec, optimize,
                                          perf_metrics)

_SC20 = [{"type": "score", "th": 20}]


# ── perf_metrics ──────────────────────────────────────────────────────────────

def test_perf_metrics_compuesto():
    trades = [
        {"exit_idx": 1, "ret": 0.10},
        {"exit_idx": 3, "ret": -0.05},
        {"exit_idx": None, "ret": 0.50},  # abierto: no cuenta
    ]
    m = perf_metrics(trades)
    assert m["n"] == 2
    assert m["win"] == pytest.approx(0.5)
    assert m["avg"] == pytest.approx(0.025)
    assert m["total"] == pytest.approx(1.10 * 0.95 - 1)


def test_perf_metrics_vacio():
    assert perf_metrics([]) == {"n": 0, "win": None, "avg": None, "total": None}


# ── grilla ────────────────────────────────────────────────────────────────────

def test_ejes_solo_de_condiciones_activas():
    spec = {"entries": _SC20,
            "score_exits": [{"type": "trailing_score", "x": 20}],
            "caps": [{"type": "stop_loss", "pct": 10}],
            "rearm": True, "cooldown": 0}
    axes = build_axes(spec)
    assert [a[0] for a in axes] == [
        ("entries", "score", "th"),
        ("score_exits", "trailing_score", "x"),
        ("caps", "stop_loss", "pct"),
    ]  # rearm no es eje; cooldown=0 (apagado) tampoco


def test_cooldown_activo_es_un_eje():
    spec = {"entries": _SC20, "cooldown": 5}
    assert ("cooldown", None, None) in [a[0] for a in build_axes(spec)]


def test_sin_condiciones_falla():
    with pytest.raises(ValueError, match="Ninguna condición"):
        build_combos({"entries": []})


def test_demasiadas_combinaciones_falla():
    spec = {"entries": _SC20}
    with pytest.raises(ValueError, match="superan el máximo"):
        build_combos(spec, max_combos=3)


def test_poda_de_incoherentes():
    # Abs< >= entrada Sc entra y sale en la barra siguiente → se descarta
    spec = {"entries": _SC20,
            "score_exits": [{"type": "absolute", "x": 0}]}
    combos = build_combos(spec)
    for c in combos:
        assert c["score_exits"][0]["x"] < c["entries"][0]["th"]


def test_los_combos_no_comparten_estado_con_la_spec_original():
    spec = {"entries": [{"type": "score", "th": 20}]}
    combos = build_combos(spec)
    combos[0]["entries"][0]["th"] = 999
    assert spec["entries"][0]["th"] == 20


# ── optimize ──────────────────────────────────────────────────────────────────

def test_optimize_maximiza_cobertura_en_serie_alcista():
    """Serie que sube 1% por rueda con score constante: el retorno compuesto
    es 1.01^(ruedas cubiertas por trades CERRADOS). En train (280 barras),
    Ruedas=20 cubre 13×20=260; 60→4×60=240; 120→2×120=240; 250→250. El
    tope corto gana por cobertura de la cola — determinístico."""
    n = 400
    closes = [100.0 * (1.01 ** i) for i in range(n)]
    scores = [100.0] * n
    spec = {"entries": [{"type": "score", "th": 20}],
            "score_exits": None,
            "caps": [{"type": "max_bars", "n": 60}]}
    out = optimize(closes, scores, None, spec, min_trades=1, top_n=5)
    assert out["results"], "sin resultados"
    best = out["results"][0]
    assert best["spec"]["caps"][0]["n"] == 20
    assert best["train"]["total"] == pytest.approx(1.01 ** 260 - 1, rel=1e-9)
    assert best["train"]["win"] == 1.0
    assert best["test"]["n"] > 0  # la validación siempre viene calculada


def test_optimize_min_trades_filtra():
    n = 400
    closes = [100.0 * (1.01 ** i) for i in range(n)]
    scores = [100.0] * n
    spec = {"entries": [{"type": "score", "th": 20}],
            "caps": [{"type": "max_bars", "n": 60}]}
    # con min_trades alto, los topes largos (pocos trades) quedan afuera
    out = optimize(closes, scores, None, spec, min_trades=4, top_n=10)
    for r in out["results"]:
        assert r["train"]["n"] >= 4
        assert r["spec"]["caps"][0]["n"] < 250


def test_optimize_historia_corta_falla():
    with pytest.raises(ValueError, match="insuficiente"):
        optimize([100.0] * 40, [50.0] * 40, None,
                 {"entries": _SC20})


def test_describe_spec():
    spec = {"entries": [{"type": "score", "th": 30}],
            "score_exits": [{"type": "trailing_score", "x": 20}],
            "caps": [{"type": "stop_loss", "pct": 10}],
            "rearm": True, "cooldown": 5}
    assert describe_spec(spec) == "Score≥30 · Máx−Δ20 · SL% 10 · Cruce · Enfr.5"


# ── spec_from_controls (el TERCER espejo del armado de spec) ──────────────────
# El orden posicional de vals ES el contrato: debe coincidir con
# _SIM_CONTROL_IDS (chart_callbacks) y con window._lwc.buildSpec (JS).

def _vals(**overrides):
    """27 valores de controles, todos apagados; overrides por nombre."""
    base = {
        "ent_sc_on": [], "ent_sc": 20, "ent_pct_on": [], "ent_pct": 90,
        "xs_abs_on": [], "xs_abs": 0, "xs_absup_on": [], "xs_absup": 90,
        "xs_dent_on": [], "xs_dent": 20, "xs_dmax_on": [], "xs_dmax": 20,
        "xs_mak_on": [], "xs_mak": 10, "xs_pct_on": [], "xs_pct": 70,
        "cap_bars_on": [], "cap_bars": 60, "cap_sl_on": [], "cap_sl": 10,
        "cap_ts_on": [], "cap_ts": 15, "cap_tp_on": [], "cap_tp": 20,
        "rearm_on": [], "cool_on": [], "cool": 5,
    }
    base.update(overrides)
    return tuple(base.values())


def test_spec_from_controls_todo_apagado():
    from app.services.trade_optimizer import spec_from_controls
    spec = spec_from_controls(_vals())
    assert spec == {"entries": [], "score_exits": [], "caps": [],
                    "rearm": False, "cooldown": 0}


def test_spec_from_controls_armado_completo():
    from app.services.trade_optimizer import spec_from_controls
    spec = spec_from_controls(_vals(
        ent_sc_on=[1], ent_pct_on=[1], xs_abs_on=[1], xs_absup_on=[1],
        xs_dent_on=[1], xs_dmax_on=[1], xs_mak_on=[1], xs_pct_on=[1],
        cap_bars_on=[1], cap_sl_on=[1], cap_ts_on=[1], cap_tp_on=[1],
        rearm_on=[1], cool_on=[1]))
    assert spec["entries"] == [{"type": "score", "th": 20},
                               {"type": "pct", "th": 90}]
    assert [x["type"] for x in spec["score_exits"]] == [
        "absolute", "absolute_above", "delta_entry", "trailing_score",
        "score_ma", "percentile"]
    assert [c["type"] for c in spec["caps"]] == [
        "max_bars", "stop_loss", "trailing_stop", "take_profit"]
    assert spec["rearm"] is True and spec["cooldown"] == 5


def test_spec_from_controls_valores_invalidos_y_redondeos():
    from app.services.trade_optimizer import spec_from_controls
    # input vacío/None → la condición tildada se ignora (sin crash)
    spec = spec_from_controls(_vals(ent_sc_on=[1], ent_sc="",
                                    xs_mak_on=[1], xs_mak="1.7",
                                    cap_bars_on=[1], cap_bars=None,
                                    cool_on=[1], cool="-3"))
    assert spec["entries"] == []
    assert spec["score_exits"] == [{"type": "score_ma", "k": 2}]  # piso 2
    assert spec["caps"] == []
    assert spec["cooldown"] == 0  # piso 0


# ── load_series: gate sobre la BD (sqlite stub) ───────────────────────────────

_LS_TABLES = ("strategy", "prices", "assets")


@pytest.fixture()
def ls_db():
    import sqlalchemy as sa

    from app.database import Base, engine, get_session
    import app.models  # noqa: F401 — registra los modelos
    from app.models import signal_store

    Base.metadata.create_all(engine)
    signal_store.ensure_strat_table(1)
    with engine.begin() as conn:
        for t in _LS_TABLES + ("strat_res_1",):
            conn.execute(sa.text(f"DELETE FROM {t}"))
    yield
    with engine.begin() as conn:
        for t in _LS_TABLES + ("strat_res_1",):
            conn.execute(sa.text(f"DELETE FROM {t}"))
    get_session().rollback()


def test_load_series_gate_y_alineacion(ls_db):
    from datetime import date

    from app.database import get_session
    from app.models import Asset, Price, Strategy, signal_store
    from app.services.trade_optimizer import load_series

    s = get_session()
    s.add(Asset(id=1, ticker="T1", name="T1", price_source_id=1))
    s.add(Strategy(id=1, name="S", is_public=True))
    d1, d2, d3, d4 = (date(2026, 1, 5), date(2026, 1, 6),
                      date(2026, 1, 7), date(2026, 1, 8))
    # precios: d1, d2, d4 (d3 no cotizó); d2 sin score; score en d3
    # (arrastrado por as-of, SIN precio propio) debe quedar AFUERA (gate)
    s.add(Price(asset_id=1, date=d1, close=100.0))
    s.add(Price(asset_id=1, date=d2, close=101.0))
    s.add(Price(asset_id=1, date=d4, close=103.0))
    rt = signal_store.get_strat_table(1)
    s.execute(rt.insert(), [
        {"asset_id": 1, "date": d1, "score": 50.0, "pct": 80.0},
        {"asset_id": 1, "date": d3, "score": 60.0, "pct": 90.0},
        {"asset_id": 1, "date": d4, "score": 70.0, "pct": None},
    ])
    s.commit()

    closes, scores, pcts = load_series(1, 1)
    assert closes == [100.0, 101.0, 103.0]   # solo barras propias
    assert scores == [50.0, None, 70.0]      # d2 sin score; d3 gateado
    assert pcts == [80.0, None, None]        # pct NULL → None
