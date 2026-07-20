"""
Componentes de vista reutilizables para cartera (backtest nivel C y módulo de
Carteras).

Figuras Plotly y tiles construidos a partir de las métricas de
`portfolio_metrics`. Los consumen tanto `/backtest` (simulación de cartera) como
`/carteras`, para que la capa visual se defina una sola vez. Tema oscuro alineado
al resto de la app (se hará theme-aware en la fase de pulido).

Nada de esto toca la BD: recibe series/métricas ya calculadas y devuelve objetos
Plotly/Dash.
"""

import dash_bootstrap_components as dbc
import plotly.graph_objects as go
from dash import html

from app.services import portfolio_metrics as pm

# Tema (alineado con backtest_callbacks; centralizar en la fase de pulido).
_BG = "#111827"
_GRID = "#1f2937"
_FG = "#dee2e6"
_MUTED = "#9aa5b5"
_UP = "#4ade80"     # ganancia
_DOWN = "#f87171"   # pérdida
# Paleta de series (estrategia con reglas, ranking puro, benchmark, índice, …).
SERIES = ["#38bdf8", "#a78bfa", "#8a93a3", "#fbbf24", "#4ade80", "#fb923c"]

_MESES = ["Ene", "Feb", "Mar", "Abr", "May", "Jun",
          "Jul", "Ago", "Sep", "Oct", "Nov", "Dic"]


# ── Formateo (None → "—") ─────────────────────────────────────────────────────

def fmt_pct(x, dp=1, signed=False):
    if x is None:
        return "—"
    return f"{x * 100:{'+' if signed else ''}.{dp}f}%"


def fmt_ratio(x, dp=2):
    return "—" if x is None else f"{x:.{dp}f}"


def fmt_mult(x, dp=2):
    """Retorno total como múltiplo: 2.41 → '×2.41'."""
    return "—" if x is None else f"×{1 + x:.{dp}f}"


# ── Layout base ───────────────────────────────────────────────────────────────

def _layout(fig, title=None, ytitle=None, ysuffix="", height=340):
    fig.update_layout(
        plot_bgcolor=_BG, paper_bgcolor=_BG,
        font=dict(color=_FG, size=11),
        margin=dict(l=52, r=20, t=40 if title else 16, b=36),
        xaxis=dict(gridcolor=_GRID, zeroline=False),
        yaxis=dict(title=ytitle, gridcolor=_GRID, ticksuffix=ysuffix,
                   zeroline=False),
        legend=dict(orientation="h", y=1.12, font=dict(size=10)),
        height=height,
    )
    if title:
        fig.update_layout(title=dict(text=title, font=dict(size=13, color=_FG)))
    return fig


def graph_config():
    """Config estándar de dcc.Graph (barra de modo apagada, como en /backtest)."""
    return {"displayModeBar": False}


# ── Figuras ───────────────────────────────────────────────────────────────────

def equity_figure(series, x=None, title=None, log=False):
    """Curva de equity multi-serie.

    `series`: lista de dicts {name, values, color?, dash?, width?}. `x` opcional
    (fechas o índices). `log`: escala logarítmica en Y.
    """
    fig = go.Figure()
    for i, s in enumerate(series):
        vals = s["values"]
        xs = s.get("x")                      # x por-serie (opcional)
        if xs is None:
            xs = x if x is not None else list(range(len(vals)))
        fig.add_trace(go.Scatter(
            x=xs, y=vals, name=s["name"], mode="lines",
            line=dict(color=s.get("color") or SERIES[i % len(SERIES)],
                      width=s.get("width", 2),
                      dash="dash" if s.get("dash") else "solid"),
        ))
    fig = _layout(fig, title, "Equity")
    if log:
        fig.update_yaxes(type="log")
    return fig


def drawdown_figure(equity, x=None, title=None):
    """Serie underwater (drawdown en %), área bajo cero."""
    dd = [v * 100 for v in pm.drawdown_series(equity)]
    xs = x if x is not None else list(range(len(dd)))
    fig = go.Figure(go.Scatter(
        x=xs, y=dd, mode="lines", name="Drawdown",
        line=dict(color=_DOWN, width=1.5),
        fill="tozeroy", fillcolor="rgba(248,113,113,0.15)"))
    return _layout(fig, title, "Drawdown", "%", height=200)


def distribution_figure(rets, bins=21, title=None):
    """Histograma de retornos de trades (en %)."""
    fig = go.Figure(go.Histogram(
        x=[r * 100 for r in rets if r is not None], nbinsx=bins,
        marker_color=SERIES[0]))
    return _layout(fig, title, "# trades", "", height=260)


# Etiquetas de los motivos de salida del simulador (trade_simulator._close_trade).
# El gráfico mostraba las claves crudas en inglés y con guiones bajos
# ("stop_loss", "absolute") en medio de una interfaz en español; "absolute" era
# especialmente opaco porque no dice que corresponde a la salida por Score <.
EXIT_REASON_LABELS = {
    "filter":         "Dejó de ser elegible",
    "max_bars":       "Máximo de ruedas",
    "stop_loss":      "Stop loss (SL%)",
    "trailing_stop":  "Trailing stop (TS%)",
    "take_profit":    "Take profit (TP%)",
    "absolute":       "Score bajo el nivel",
    "absolute_above": "Score sobre el nivel",
    "delta_entry":    "Score cayó Δ desde la entrada",
    "trailing_score": "Score cayó Δ desde el máximo",
    "score_ma":       "Score bajo su media",
    "percentile":     "Percentil bajo el umbral",
}


def exit_reason_label(reason):
    """Etiqueta legible de un motivo de salida; si es desconocido, la clave."""
    return EXIT_REASON_LABELS.get(reason, reason)


def exit_reason_figure(breakdown, title=None):
    """Barras horizontales: cantidad de cierres por motivo de salida."""
    reasons = list(breakdown.keys())
    counts = [breakdown[r]["count"] for r in reasons]
    fig = go.Figure(go.Bar(x=counts, y=[exit_reason_label(r) for r in reasons],
                           orientation="h", marker_color=SERIES[1]))
    return _layout(fig, title, None, height=max(160, 34 * len(reasons) + 60))


def monthly_heatmap_figure(matrix, title=None):
    """Heatmap de retornos mensuales (verde gana / rojo pierde, gris = 0)."""
    years = sorted(matrix.keys())
    z = [[matrix[y].get(m) * 100 if matrix[y].get(m) is not None else None
          for m in range(1, 13)] for y in years]
    fig = go.Figure(go.Heatmap(
        z=z, x=_MESES, y=[str(y) for y in years], zmid=0,
        colorscale=[[0.0, _DOWN], [0.5, _GRID], [1.0, _UP]],
        showscale=False, xgap=2, ygap=2))
    return _layout(fig, title, None, height=max(160, 40 * len(years) + 60))


# ── Tiles de KPI ──────────────────────────────────────────────────────────────

def kpi_tiles(items):
    """Fila de tarjetas KPI.

    `items`: lista de dicts {label, value, delta?, good?}. `good` True/False pinta
    el valor de verde/rojo; None lo deja neutro.
    """
    cols = []
    for it in items:
        good = it.get("good")
        color = _UP if good is True else _DOWN if good is False else _FG
        cols.append(dbc.Col(dbc.Card(dbc.CardBody([
            html.Div(it["label"], style={"fontSize": "11px", "color": _MUTED}),
            html.Div(it["value"], style={
                "fontSize": "23px", "fontWeight": "600", "color": color,
                "fontFamily": "monospace", "lineHeight": "1.1"}),
            html.Div(it.get("delta", ""), style={
                "fontSize": "11px", "color": _MUTED}),
        ]), style={"backgroundColor": _GRID,
                   "border": "1px solid #2c3543"}),
            xs=6, lg=3, className="mb-2"))
    return dbc.Row(cols, className="g-2")
