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
