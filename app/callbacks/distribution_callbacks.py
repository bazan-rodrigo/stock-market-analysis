import numpy as np
import pandas as pd
import plotly.graph_objects as go
from dash import Input, Output, callback, dcc, html, no_update
import dash_bootstrap_components as dbc

from app.database import get_session
from app.models.indicator_definition import IndicatorDefinition
from app.models.indicator_value import IndicatorValue

_BG = "#111827"


def _bin_distribution(series: pd.Series, bin_size: float):
    low  = np.floor(series.min() / bin_size) * bin_size
    high = np.ceil(series.max()  / bin_size) * bin_size
    if low == high:
        high = low + bin_size

    bins = np.arange(low, high + bin_size * 0.5, bin_size)

    def _fmt(v):
        return f"{v:.4g}"

    labels = [f"{_fmt(b)} – {_fmt(b + bin_size)}" for b in bins[:-1]]
    cut    = pd.cut(series, bins=bins, labels=labels, include_lowest=True)
    counts = cut.value_counts().reindex(labels).fillna(0)
    pct    = (counts / counts.sum() * 100).round(2)

    current_label = str(cut.iloc[-1]) if not pd.isna(cut.iloc[-1]) else None
    return current_label, pct


@callback(
    Output("dist-indicator-select", "options"),
    Output("dist-indicator-select", "value"),
    Input("analysis-asset-select",  "value"),
    Input("analysis-tabs",          "active_tab"),
)
def update_indicator_options(asset_id, active_tab):
    if active_tab != "tab-distribution" or not asset_id:
        return no_update, no_update

    s = get_session()
    rows = (
        s.query(
            IndicatorDefinition.id,
            IndicatorDefinition.name,
            IndicatorDefinition.category,
        )
        .join(IndicatorValue, IndicatorValue.indicator_id == IndicatorDefinition.id)
        .filter(
            IndicatorValue.asset_id == int(asset_id),
            IndicatorDefinition.type == "num",
            IndicatorDefinition.keep_history.is_(True),
            IndicatorValue.value_num.isnot(None),
        )
        .distinct()
        .order_by(IndicatorDefinition.category, IndicatorDefinition.name)
        .all()
    )

    options = [
        {"label": f"{r.name}  [{r.category}]", "value": r.id}
        for r in rows
    ]
    return options, (rows[0].id if rows else None)


@callback(
    Output("dist-graph", "figure"),
    Output("dist-stats", "children"),
    Input("analysis-asset-select", "value"),
    Input("analysis-tabs",         "active_tab"),
    Input("dist-indicator-select", "value"),
    Input("dist-bin-size",         "value"),
)
def load_distribution_chart(asset_id, active_tab, indicator_id, bin_size):
    if active_tab != "tab-distribution" or not asset_id or not indicator_id:
        return no_update, no_update

    bin_size = max(float(bin_size or 5), 0.001)

    s    = get_session()
    defn = s.get(IndicatorDefinition, int(indicator_id))

    rows = (
        s.query(IndicatorValue.value_num)
        .filter(
            IndicatorValue.asset_id     == int(asset_id),
            IndicatorValue.indicator_id == int(indicator_id),
            IndicatorValue.value_num.isnot(None),
        )
        .order_by(IndicatorValue.date)
        .all()
    )

    if not rows:
        empty = go.Figure()
        empty.update_layout(plot_bgcolor=_BG, paper_bgcolor=_BG)
        return empty, dbc.Alert("Sin datos históricos para este indicador.", color="warning")

    series      = pd.Series([r.value_num for r in rows])
    current_raw = series.iloc[-1]

    current_label, distribution = _bin_distribution(series, bin_size)

    x_title = defn.name + (f"  ({defn.scale})" if defn.scale else "")
    colors  = ["#38bdf8" if lbl == current_label else "#374151"
                for lbl in distribution.index]
    texts   = [f"Actual: {current_raw:.4g}" if lbl == current_label else ""
                for lbl in distribution.index]

    fig = go.Figure(go.Bar(
        x=list(distribution.index),
        y=list(distribution.values),
        marker_color=colors,
        text=texts,
        textposition="outside",
        textfont=dict(size=11, color="#38bdf8"),
        cliponaxis=False,
    ))
    fig.update_layout(
        plot_bgcolor=_BG, paper_bgcolor=_BG,
        font=dict(color="#dee2e6", size=11),
        margin=dict(l=50, r=20, t=20, b=110),
        xaxis=dict(
            title=dict(text=x_title, font=dict(size=11)),
            tickangle=-45,
            gridcolor="#1f2937",
            tickfont=dict(size=10),
        ),
        yaxis=dict(title="% del historial", ticksuffix="%", gridcolor="#1f2937"),
        showlegend=False,
        bargap=0.15,
    )

    percentile = float((series < current_raw).mean() * 100)

    stats = html.Div([
        html.Span("Valor actual: ",        className="text-muted"),
        html.Span(f"{current_raw:.4g}  ",  style={"fontWeight": "700", "color": "#38bdf8"}),
        html.Span("Percentil histórico: ", className="text-muted"),
        html.Span(f"{percentile:.0f}°  ",  style={"fontWeight": "700"}),
        html.Span(f"sobre {len(series)} observaciones", className="text-muted",
                  style={"fontSize": "0.75rem"}),
    ], style={"fontSize": "0.82rem"})

    return fig, stats
