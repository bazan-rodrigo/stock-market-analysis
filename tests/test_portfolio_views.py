"""Tests de los componentes de vista de cartera (portfolio_views.py).

Verifican formateo (None → '—') y que las figuras Plotly y los tiles se
construyen con la estructura esperada (nº de trazas / columnas). No renderizan.
"""
import dash_bootstrap_components as dbc
import plotly.graph_objects as go

from app.components.portfolio_views import (distribution_figure,
                                            drawdown_figure, equity_figure,
                                            exit_reason_figure, fmt_mult,
                                            fmt_pct, fmt_ratio, kpi_tiles,
                                            monthly_heatmap_figure)


def test_formatters():
    assert fmt_pct(0.123) == "12.3%"
    assert fmt_pct(0.05, signed=True) == "+5.0%"
    assert fmt_pct(None) == "—"
    assert fmt_ratio(1.324) == "1.32"
    assert fmt_ratio(None) == "—"
    assert fmt_mult(1.41) == "×2.41"
    assert fmt_mult(None) == "—"


def test_equity_figure_traces():
    fig = equity_figure([
        {"name": "Con reglas", "values": [100, 110, 121]},
        {"name": "EW", "values": [100, 104, 107], "dash": True},
    ])
    assert isinstance(fig, go.Figure)
    assert len(fig.data) == 2
    assert fig.data[0].name == "Con reglas"


def test_drawdown_figure():
    fig = drawdown_figure([100.0, 120.0, 90.0, 150.0])
    assert isinstance(fig, go.Figure)
    assert len(fig.data) == 1
    # el drawdown más profundo (−25%) aparece en la serie
    assert min(fig.data[0].y) == -25.0


def test_distribution_and_exit_reason():
    assert isinstance(distribution_figure([0.1, -0.05, 0.2]), go.Figure)
    br = {"take_profit": {"count": 2, "mean_ret": 0.15, "total_ret": 0.3},
          "stop_loss": {"count": 1, "mean_ret": -0.05, "total_ret": -0.05}}
    fig = exit_reason_figure(br)
    assert isinstance(fig, go.Figure)
    assert list(fig.data[0].x) == [2, 1]


def test_monthly_heatmap_figure():
    fig = monthly_heatmap_figure({2020: {2: 0.21, 3: 0.10}})
    assert isinstance(fig, go.Figure)
    assert list(fig.data[0].y) == ["2020"]


def test_kpi_tiles_structure():
    row = kpi_tiles([
        {"label": "CAGR", "value": "18.4%", "good": True},
        {"label": "Máx DD", "value": "−22.6%", "good": False},
    ])
    assert isinstance(row, dbc.Row)
    assert len(row.children) == 2
