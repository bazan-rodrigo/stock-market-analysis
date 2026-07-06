"""sr_service: detección de pivots y clustering de niveles de soporte/resistencia."""
from types import SimpleNamespace

import pandas as pd
import pytest

from app.services.sr_service import _cluster_levels, _compute_pivots, compute_sr_from_df


def _cfg(**kw):
    base = dict(lookback_days=252, pivot_window=2, cluster_pct=0.5, min_touches=2)
    base.update(kw)
    return SimpleNamespace(**base)


# ── _cluster_levels ───────────────────────────────────────────────────────────

def test_cluster_vacio_devuelve_vacio():
    assert _cluster_levels([], 0.5, 2) == []


def test_cluster_agrupa_precios_cercanos():
    # 100 y 100.3 difieren 0.3% (<= 0.5%) → mismo grupo; 200 queda solo
    result = _cluster_levels([100.0, 100.3, 200.0], cluster_pct=0.5, min_touches=2)
    assert result == [{"price": pytest.approx(100.15), "touches": 2}]


def test_cluster_descarta_grupos_bajo_min_touches():
    # cada precio queda en su propio grupo (muy separados) → touches=1 < 2
    assert _cluster_levels([100.0, 200.0, 300.0], cluster_pct=0.5, min_touches=2) == []


def test_cluster_un_solo_touch_alcanza_si_min_touches_es_1():
    result = _cluster_levels([100.0, 200.0], cluster_pct=0.5, min_touches=1)
    assert result == [{"price": 100.0, "touches": 1}, {"price": 200.0, "touches": 1}]


def test_cluster_referencia_es_el_primer_precio_del_grupo_no_el_ultimo():
    # 100 -> 100.4 (0.4% <= 0.5%): mismo grupo. Pero el próximo se compara
    # contra 100 (el primero del grupo), no contra 100.4 (el último agregado):
    # 100.8 vs 100 → 0.8% > 0.5% → grupo nuevo, aunque esté a 0.4% de 100.4.
    result = _cluster_levels([100.0, 100.4, 100.8], cluster_pct=0.5, min_touches=1)
    assert result == [
        {"price": pytest.approx(100.2), "touches": 2},
        {"price": 100.8, "touches": 1},
    ]


def test_cluster_precio_cero_no_agrupa_por_guarda_de_division():
    # ref=0 → la guarda "ref > 0" evita la división por cero: cada 0.0 abre
    # su propio grupo en lugar de agruparse entre sí
    result = _cluster_levels([0.0, 0.0, 0.0], cluster_pct=0.5, min_touches=2)
    assert result == []   # 3 grupos de 1 cada uno, ninguno llega a min_touches


# ── _compute_pivots ───────────────────────────────────────────────────────────

def _ohlc(highs, lows):
    return pd.DataFrame({"high": highs, "low": lows})


def test_compute_pivots_detecta_maximo_y_minimo_local():
    # pico en el índice 2 (10), valle en el índice 2 (1), window=1
    highs = [5, 7, 10, 7, 5]
    lows  = [3, 2, 1, 2, 3]
    resist, support = _compute_pivots(_ohlc(highs, lows), window=1,
                                      cluster_pct=0.5, min_touches=1)
    assert resist  == [{"price": 10.0, "touches": 1}]
    assert support == [{"price": 1.0, "touches": 1}]


def test_compute_pivots_serie_monotona_no_detecta_pivots():
    highs = [1, 2, 3, 4, 5]
    lows  = [1, 2, 3, 4, 5]
    resist, support = _compute_pivots(_ohlc(highs, lows), window=1,
                                      cluster_pct=0.5, min_touches=1)
    assert resist == [] and support == []


def test_compute_pivots_muy_corta_para_la_ventana_no_falla():
    # n - window <= window → rango vacío, sin IndexError
    highs = [5, 7, 5]
    lows  = [3, 2, 3]
    resist, support = _compute_pivots(_ohlc(highs, lows), window=2,
                                      cluster_pct=0.5, min_touches=1)
    assert resist == [] and support == []


def test_compute_pivots_meseta_registra_un_candidato_por_bar_del_empate():
    # highs empatados en el tope (7,7) dentro de la ventana: ambos bars
    # cumplen "highs[i] == max(ventana)" → 2 candidatos, mismo precio
    highs = [5, 7, 7, 5]
    lows  = [1, 1, 1, 1]
    resist, _ = _compute_pivots(_ohlc(highs, lows), window=1,
                                cluster_pct=0.5, min_touches=2)
    assert resist == [{"price": 7.0, "touches": 2}]


# ── compute_sr_from_df ────────────────────────────────────────────────────────

def _price_df(closes, highs=None, lows=None, start="2025-01-01"):
    dates = pd.date_range(start, periods=len(closes), freq="D")
    return pd.DataFrame({
        "date":  dates,
        "close": closes,
        "high":  highs or [c + 1 for c in closes],
        "low":   lows or [c - 1 for c in closes],
    })


def test_compute_sr_df_corto_devuelve_none():
    df = _price_df([100, 101, 102])   # < pivot_window*2 + 2
    assert compute_sr_from_df(df, cfg=_cfg(pivot_window=5)) is None


def test_compute_sr_calcula_distancia_al_pivot_mas_cercano():
    # doble zigzag: 2 picos en 110 (idx2, idx10) y 2 valles en 90 (idx6, idx14),
    # cierre final en 100 → un pivot de cada lado con 2 touches cada uno
    closes = [100, 105, 110, 105, 100, 95, 90, 95,
              100, 105, 110, 105, 100, 95, 90, 95, 100]
    df = _price_df(closes)
    result = compute_sr_from_df(df, cfg=_cfg(pivot_window=1, min_touches=2))
    assert result["pivot_resist_pct"] == 11.0    # (111-100)/100*100 (high = close+1)
    assert result["pivot_support_pct"] == -11.0  # (89-100)/100*100  (low  = close-1)
    assert result["sr_pivots"]["nearest_resist_pct"] == result["pivot_resist_pct"]
    assert result["sr_pivots"]["nearest_support_pct"] == result["pivot_support_pct"]


def test_compute_sr_sin_pivots_devuelve_porcentajes_none():
    # serie monótona: sin extremos locales → sin niveles → % en None
    closes = list(range(100, 120))
    df = _price_df(closes)
    result = compute_sr_from_df(df, cfg=_cfg(pivot_window=2, min_touches=1))
    assert result == {
        "pivot_resist_pct": None,
        "pivot_support_pct": None,
        "sr_pivots": {
            "resist": [], "support": [],
            "nearest_resist_pct": None, "nearest_support_pct": None,
        },
    }
