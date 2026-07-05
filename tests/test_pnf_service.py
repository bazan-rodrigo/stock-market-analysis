"""pnf_service: algoritmo de columnas Punto y Figura y tamaño de caja."""
from types import SimpleNamespace

import pandas as pd
import pytest

from app.services.pnf_service import compute_box_size, compute_pnf_columns


def _df(closes, spread=0.5, dates=None):
    dates = dates or [f"d{i:02d}" for i in range(len(closes))]
    return pd.DataFrame({
        "date":  dates,
        "high":  [c + spread for c in closes],
        "low":   [c - spread for c in closes],
        "close": closes,
    })


def _cfg(**kw):
    base = dict(box_method="fixed", box_pct=1.0, box_atr_period=14,
                box_fixed=1.0, reversal=3, source="close")
    base.update(kw)
    return SimpleNamespace(**base)


# ── compute_pnf_columns ───────────────────────────────────────────────────────

def test_subida_reversion_y_rebote():
    closes = [100, 102, 104, 106, 108, 110, 108, 106, 104, 106, 108, 110, 112]
    cols = compute_pnf_columns(_df(closes), box=1.0, reversal=3, source="close")
    assert [c["type"] for c in cols] == ["X", "O", "X"]
    # la O abre una caja debajo del techo de la X; la X nueva, una arriba del piso
    assert cols[0]["top"] == 110 and cols[1]["top"] == 109
    assert cols[1]["bot"] == 104 and cols[2]["bot"] == 105
    assert cols[2]["top"] == 112

def test_arranque_bajista():
    cols = compute_pnf_columns(_df([100, 98, 95, 92]), box=1.0, reversal=3)
    assert cols and cols[0]["type"] == "O"
    assert cols[0]["bot"] == 92

def test_mercado_plano_sin_columnas():
    cols = compute_pnf_columns(_df([100, 100.2, 100.4, 100.1]), box=1.0, reversal=3)
    assert len(cols) <= 1

def test_movimiento_menor_a_reversion_no_revierte():
    # sube a 110 y baja solo 2 cajas (reversion=3): sigue una sola columna X
    closes = [100, 105, 110, 108.5]
    cols = compute_pnf_columns(_df(closes), box=1.0, reversal=3)
    assert [c["type"] for c in cols] == ["X"]

def test_fuente_hl_usa_extremos():
    df = pd.DataFrame({
        "date":  ["d0", "d1", "d2", "d3"],
        "high":  [100.9, 105.9, 106.9, 103.0],
        "low":   [99.1, 100.0, 101.0, 101.5],
        "close": [100, 105, 106, 102],
    })
    cols = compute_pnf_columns(df, box=1.0, reversal=3, source="hl")
    assert cols[0]["type"] == "X"
    assert cols[0]["top"] == 106       # high 106.9 → caja 106 (no el close 106→106)

def test_caja_invalida_y_df_vacio():
    assert compute_pnf_columns(_df([100, 110]), box=0, reversal=3) == []
    assert compute_pnf_columns(_df([]), box=1.0, reversal=3) == []

def test_fechas_de_columna():
    closes = [100, 105, 110, 104]   # X hasta d02, O abre en d03
    cols = compute_pnf_columns(_df(closes), box=1.0, reversal=3)
    assert cols[0]["end"] == "d02"
    assert cols[1]["start"] == "d03"


# ── compute_box_size ──────────────────────────────────────────────────────────

def test_box_fijo():
    assert compute_box_size(_df([100, 101]), _cfg(box_method="fixed", box_fixed=2.5)) == 2.5

def test_box_porcentaje_del_ultimo_cierre():
    box = compute_box_size(_df([100, 200]), _cfg(box_method="percent", box_pct=1.0))
    assert box == pytest.approx(2.0)   # 1% de 200

def test_box_atr_con_rango_constante():
    # TR constante = 2*spread = 2.0 → el ATR converge exactamente a 2.0
    closes = [100 + 0.0 for _ in range(60)]
    box = compute_box_size(_df(closes, spread=1.0), _cfg(box_method="atr", box_atr_period=14))
    assert box == pytest.approx(2.0)

def test_box_atr_sin_datos_suficientes_cae_al_1pct():
    box = compute_box_size(_df([100, 100, 100]), _cfg(box_method="atr", box_atr_period=14))
    assert box == pytest.approx(1.0)   # 1% del último cierre

def test_box_nunca_cero_ni_negativo():
    box = compute_box_size(_df([100, 100]), _cfg(box_method="fixed", box_fixed=0))
    assert box == pytest.approx(1.0)   # fallback 1% del cierre


# ── build_pnf_figure (requiere plotly) ────────────────────────────────────────

def test_figura_basica():
    pytest.importorskip("plotly")
    from app.services.pnf_service import build_pnf_figure
    closes = [100, 102, 104, 106, 108, 110, 106, 104, 102]
    fig = build_pnf_figure(_df(closes, dates=[f"2026-01-{i+1:02d}" for i in range(9)]),
                           cfg=_cfg())
    kinds = sorted(tr.name for tr in fig.data)
    assert kinds == ["O", "X"]

def test_figura_sin_datos():
    pytest.importorskip("plotly")
    from app.services.pnf_service import build_pnf_figure
    fig = build_pnf_figure(_df([100]), cfg=_cfg())
    assert not fig.data          # solo la anotación de "sin datos"
