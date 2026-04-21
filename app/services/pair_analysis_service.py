import numpy as np
import pandas as pd
from datetime import date as _date

import plotly.graph_objects as go
from plotly.subplots import make_subplots

_DARK = dict(
    paper_bgcolor="#1e2126",
    plot_bgcolor="#1e2126",
    font=dict(color="#dee2e6"),
)
_AXIS = dict(gridcolor="#2d3038", linecolor="#495057", zerolinecolor="#2d3038")
_C1 = "#60a5fa"
_C2 = "#34d399"
_TREND = "#fbbf24"
_LAST = "#f87171"


def get_pair_data(
    asset_id_1: int,
    asset_id_2: int,
    from_date: _date = None,
    to_date: _date = None,
):
    """Devuelve (label1, label2, df1, df2, merged, error).

    df1/df2: DatetimeIndex → columna 'close' (precios individuales filtrados).
    merged:  inner-join con columnas 'close_1' y 'close_2' (fechas comunes).
    error:   str con mensaje o None si todo OK.
    """
    from app.database import get_session
    from app.models import Asset, Price

    s = get_session()

    def _load(aid):
        a = s.get(Asset, aid)
        if not a:
            return None, None, None
        label = f"{a.ticker}" + (f" — {a.name}" if a.name else "")
        q = (
            s.query(Price)
            .filter(Price.asset_id == aid, Price.close.isnot(None))
        )
        if from_date:
            q = q.filter(Price.date >= from_date)
        if to_date:
            q = q.filter(Price.date <= to_date)
        rows = q.order_by(Price.date).all()
        if not rows:
            return label, a.ticker, None
        df = pd.DataFrame({"date": [r.date for r in rows], "close": [r.close for r in rows]})
        df["date"] = pd.to_datetime(df["date"])
        df.set_index("date", inplace=True)
        return label, a.ticker, df

    label1, ticker1, df1 = _load(asset_id_1)
    label2, ticker2, df2 = _load(asset_id_2)

    if label1 is None:
        return "Activo 1", "Activo 2", None, None, None, f"Activo {asset_id_1} no encontrado"
    if df1 is None:
        return label1, label2 or "Activo 2", None, None, None, f"{ticker1}: sin datos en el período"
    if label2 is None:
        return label1, "Activo 2", None, None, None, f"Activo {asset_id_2} no encontrado"
    if df2 is None:
        return label1, label2, None, None, None, f"{ticker2}: sin datos en el período"

    merged = df1.join(df2, how="inner", lsuffix="_1", rsuffix="_2")
    if merged.empty:
        return label1, label2, df1, df2, None, "Sin fechas comunes entre ambos activos en el período seleccionado"

    return label1, label2, df1, df2, merged, None


def build_comparison_fig(df1: pd.DataFrame, df2: pd.DataFrame,
                         label1: str, label2: str, log_scale: bool = False) -> go.Figure:
    """Dos activos en el mismo gráfico con doble eje Y."""
    fig = make_subplots(specs=[[{"secondary_y": True}]])

    fig.add_trace(
        go.Scatter(x=df1.index, y=df1["close"], name=label1, mode="lines",
                   line=dict(color=_C1, width=1.5)),
        secondary_y=False,
    )
    fig.add_trace(
        go.Scatter(x=df2.index, y=df2["close"], name=label2, mode="lines",
                   line=dict(color=_C2, width=1.5)),
        secondary_y=True,
    )

    axis_type = "log" if log_scale else "linear"
    fig.update_yaxes(type=axis_type, secondary_y=False,
                     title_text=label1, **_AXIS,
                     title_font=dict(color=_C1), tickfont=dict(color=_C1))
    fig.update_yaxes(type=axis_type, secondary_y=True,
                     title_text=label2, **_AXIS,
                     title_font=dict(color=_C2), tickfont=dict(color=_C2))
    fig.update_xaxes(**_AXIS)
    fig.update_layout(
        **_DARK,
        hovermode="x unified",
        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1),
        margin=dict(l=60, r=60, t=30, b=40),
    )
    return fig


def build_ratio_fig(merged: pd.DataFrame, label1: str, label2: str,
                    log_scale: bool = False) -> go.Figure:
    """Ratio (activo1 / activo2) en el tiempo con regresión lineal."""
    ratio = merged["close_1"] / merged["close_2"]

    x_idx = np.arange(len(ratio))
    coeffs = np.polyfit(x_idx, ratio.values, 1)
    trend = np.polyval(coeffs, x_idx)

    fig = go.Figure()
    fig.add_trace(go.Scatter(
        x=merged.index, y=ratio,
        name="Ratio", mode="lines",
        line=dict(color=_C1, width=1.5),
    ))
    fig.add_trace(go.Scatter(
        x=merged.index, y=trend,
        name="Regresión lineal", mode="lines",
        line=dict(color=_TREND, width=1.5, dash="dot"),
    ))

    fig.update_xaxes(**_AXIS)
    fig.update_yaxes(
        type="log" if log_scale else "linear",
        title_text=f"{label1} / {label2}",
        **_AXIS,
    )
    fig.update_layout(
        **_DARK,
        hovermode="x unified",
        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1),
        margin=dict(l=60, r=60, t=30, b=40),
    )
    return fig


def build_scatter_fig(merged: pd.DataFrame, label1: str, label2: str) -> go.Figure:
    """Dispersión precio1 vs precio2 con trendline OLS y punto más reciente destacado."""
    x = merged["close_2"].values
    y = merged["close_1"].values
    dates = merged.index.strftime("%Y-%m-%d").tolist()

    coeffs = np.polyfit(x, y, 1)
    x_line = np.linspace(x.min(), x.max(), 300)
    y_line = np.polyval(coeffs, x_line)

    fig = go.Figure()
    fig.add_trace(go.Scatter(
        x=x, y=y,
        mode="markers",
        name="Histórico",
        text=dates,
        hovertemplate="%{text}<br>" + label2 + ": %{x:.2f}<br>" + label1 + ": %{y:.2f}<extra></extra>",
        marker=dict(size=3, color=_C1, opacity=0.6),
    ))
    fig.add_trace(go.Scatter(
        x=x_line, y=y_line,
        mode="lines",
        name="Tendencia (OLS)",
        line=dict(color=_TREND, width=1.5, dash="dot"),
        hoverinfo="skip",
    ))
    fig.add_trace(go.Scatter(
        x=[x[-1]], y=[y[-1]],
        mode="markers",
        name="Último",
        text=[dates[-1]],
        hovertemplate="%{text}<br>" + label2 + ": %{x:.2f}<br>" + label1 + ": %{y:.2f}<extra></extra>",
        marker=dict(size=10, color=_LAST, symbol="circle"),
    ))

    fig.update_xaxes(title_text=label2, **_AXIS)
    fig.update_yaxes(title_text=label1, **_AXIS)
    fig.update_layout(
        **_DARK,
        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1),
        margin=dict(l=60, r=60, t=30, b=40),
    )
    return fig
