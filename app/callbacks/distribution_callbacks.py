import sqlalchemy as sa
import numpy as np
import pandas as pd
import plotly.graph_objects as go
from dash import Input, Output, callback, html, no_update
import dash_bootstrap_components as dbc

from app.database import get_session
from app.models.indicator_definition import IndicatorDefinition
from app.models.indicator_store import get_ind_table

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
    # Indicadores numéricos con historia
    defs = (
        s.query(IndicatorDefinition)
        .filter(
            IndicatorDefinition.type == "num",
            IndicatorDefinition.keep_history.is_(True),
        )
        .order_by(IndicatorDefinition.category, IndicatorDefinition.name)
        .all()
    )

    # Solo los que tienen datos para este activo
    options = []
    first_code = None
    for defn in defs:
        try:
            t = get_ind_table(defn.code)
        except Exception:
            continue
        has_data = s.execute(
            sa.select(sa.func.count()).select_from(
                sa.select(t.c.date).where(
                    (t.c.asset_id == int(asset_id)) & t.c.value.isnot(None)
                ).limit(1).subquery()
            )
        ).scalar()
        if has_data:
            options.append({"label": f"{defn.name}  [{defn.category}]", "value": defn.code})
            if first_code is None:
                first_code = defn.code

    return options, first_code


@callback(
    Output("dist-graph", "figure"),
    Output("dist-stats", "children"),
    Input("analysis-asset-select", "value"),
    Input("analysis-tabs",         "active_tab"),
    Input("dist-indicator-select", "value"),
    Input("dist-bin-size",         "value"),
)
def load_distribution_chart(asset_id, active_tab, indicator_code, bin_size):
    if active_tab != "tab-distribution" or not asset_id or not indicator_code:
        return no_update, no_update

    bin_size = max(float(bin_size or 5), 0.001)

    s    = get_session()
    defn = s.query(IndicatorDefinition).filter(
        IndicatorDefinition.code == indicator_code
    ).first()
    if defn is None:
        return no_update, no_update

    try:
        t = get_ind_table(indicator_code)
    except Exception:
        empty = go.Figure()
        empty.update_layout(plot_bgcolor=_BG, paper_bgcolor=_BG)
        return empty, dbc.Alert("Tabla de indicador no disponible.", color="warning")

    rows = s.execute(
        sa.select(t.c.value)
        .where((t.c.asset_id == int(asset_id)) & t.c.value.isnot(None))
        .order_by(t.c.date)
    ).fetchall()

    if not rows:
        empty = go.Figure()
        empty.update_layout(plot_bgcolor=_BG, paper_bgcolor=_BG)
        return empty, dbc.Alert("Sin datos históricos para este indicador.", color="warning")

    series      = pd.Series([r[0] for r in rows])
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
