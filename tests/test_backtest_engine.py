"""Tests del motor puro de backtest por deciles (backtest_engine.py).

Codifican la metodología: retorno forward con lag (sin look-ahead), cuantiles
por rango con empates estables, Spearman con ranks promediados, agregación
equal-weight por fecha.
"""
import pytest

from app.services.backtest_engine import (_avg_ranks, aggregate_cross_sections,
                                          date_cross_section,
                                          forward_returns_for_series,
                                          quantile_index, spearman_ic)


# ── forward_returns_for_series ────────────────────────────────────────────────

def test_forward_returns_lag_1():
    closes = [100.0, 110.0, 121.0, 133.1]
    fwd = forward_returns_for_series(closes, horizons=[1, 2], lag=1)
    # i=0: entra en closes[1]=110; h1 → 121/110−1; h2 → 133.1/110−1
    assert fwd[0][1] == pytest.approx(0.1)
    assert fwd[0][2] == pytest.approx(0.21)
    # i=1: entra en 121; h1 → 133.1/121−1; h2 se pasa del final → None
    assert fwd[1][1] == pytest.approx(0.1)
    assert fwd[1][2] is None
    # i=2: entra en 133.1; h1 fuera de serie → None
    assert fwd[2][1] is None
    # i=3: la entrada misma queda fuera de la serie
    assert fwd[3][1] is None and fwd[3][2] is None


def test_forward_returns_lag_0_mide_desde_la_misma_barra():
    closes = [100.0, 110.0]
    fwd = forward_returns_for_series(closes, horizons=[1], lag=0)
    assert fwd[0][1] == pytest.approx(0.1)
    assert fwd[1][1] is None


def test_forward_returns_entrada_invalida_da_none():
    fwd = forward_returns_for_series([100.0, 0.0, 110.0], horizons=[1], lag=1)
    assert fwd[0][1] is None  # entrada en close 0 → inválido


# ── ranks / Spearman ──────────────────────────────────────────────────────────

def test_avg_ranks_con_empates():
    assert _avg_ranks([10, 20, 20, 30]) == [1.0, 2.5, 2.5, 4.0]


def test_spearman_monotonia_perfecta():
    assert spearman_ic([1, 2, 3, 4], [0.01, 0.02, 0.03, 0.04]) == pytest.approx(1.0)
    assert spearman_ic([1, 2, 3, 4], [0.04, 0.03, 0.02, 0.01]) == pytest.approx(-1.0)


def test_spearman_degenerado_devuelve_none():
    assert spearman_ic([1, 2], [0.1, 0.2]) is None            # < 3 pares
    assert spearman_ic([5, 5, 5], [0.1, 0.2, 0.3]) is None    # varianza cero
    assert spearman_ic([1, 2, 3], [0.1, 0.1, 0.1]) is None


def test_spearman_con_empates_es_finito():
    ic = spearman_ic([1, 1, 2, 3], [0.01, 0.02, 0.03, 0.04])
    assert ic is not None and 0 < ic <= 1


# ── cuantiles ─────────────────────────────────────────────────────────────────

def test_quantile_index_reparte_por_rango():
    # 25 items en 10 cuantiles: el peor rank cae en 1, el mejor en 10
    assert quantile_index(0, 25, 10) == 1
    assert quantile_index(24, 25, 10) == 10
    # 10 en 10: biyección
    assert [quantile_index(r, 10, 10) for r in range(10)] == list(range(1, 11))


def test_date_cross_section_basica():
    pairs = [(1, 0.01), (2, 0.02), (3, 0.03), (4, 0.04)]
    cs = date_cross_section(pairs, n_quantiles=2, min_assets=2)
    assert cs["n"] == 4
    assert cs["q_means"][0] == pytest.approx(0.015)  # scores 1,2
    assert cs["q_means"][1] == pytest.approx(0.035)  # scores 3,4
    assert cs["spread"] == pytest.approx(0.02)
    assert cs["ic"] == pytest.approx(1.0)


def test_date_cross_section_pocos_activos_devuelve_none():
    assert date_cross_section([(1, 0.01)], n_quantiles=2, min_assets=2) is None
    # min_assets menor que n_quantiles no habilita fechas chicas
    assert date_cross_section([(1, 0.01), (2, 0.02)],
                              n_quantiles=3, min_assets=1) is None


# ── agregación ────────────────────────────────────────────────────────────────

def test_aggregate_equal_weight_por_fecha():
    s1 = date_cross_section([(1, 0.01), (2, 0.02), (3, 0.05), (4, 0.06)],
                            n_quantiles=2, min_assets=2)
    s2 = date_cross_section([(1, -0.01), (2, 0.00), (3, 0.01), (4, 0.02)],
                            n_quantiles=2, min_assets=2)
    agg = aggregate_cross_sections([s1, s2])
    assert agg["n_dates"] == 2
    assert agg["avg_assets"] == 4
    q1, q2 = agg["quantiles"]
    # medias diarias de q1: 0.015 y −0.005 → media 0.005, 50% positivas
    assert q1["mean_ret"] == pytest.approx(0.005)
    assert q1["pct_pos"] == pytest.approx(0.5)
    # q2: 0.055 y 0.015 → media 0.035, 100% positivas
    assert q2["mean_ret"] == pytest.approx(0.035)
    assert q2["pct_pos"] == pytest.approx(1.0)
    assert agg["spread_mean"] == pytest.approx((0.04 + 0.02) / 2)
    assert agg["ic_mean"] == pytest.approx(1.0)
    assert agg["ic_pct_pos"] == pytest.approx(1.0)


def test_aggregate_vacio_devuelve_none():
    assert aggregate_cross_sections([]) is None
