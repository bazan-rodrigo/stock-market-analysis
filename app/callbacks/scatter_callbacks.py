import numpy as np
import plotly.graph_objects as go
from dash import Input, Output, callback, html
import dash_bootstrap_components as dbc

import app.services.scatter_service as svc

_BG = "#111827"


@callback(
    Output("scatter-asset1", "options"),
    Output("scatter-asset2", "options"),
    Input("scatter-asset1", "id"),
)
def load_options(_):
    opts = svc.get_all_assets_options()
    return opts, opts


@callback(
    Output("scatter-graph",  "figure"),
    Output("scatter-stats",  "children"),
    Input("scatter-asset1",      "value"),
    Input("scatter-asset2",      "value"),
    Input("scatter-show-events", "value"),
)
def render_scatter(asset1_id, asset2_id, show_events_opt):
    empty = _empty_fig()

    if not asset1_id or not asset2_id:
        return empty, ""

    if asset1_id == asset2_id:
        return empty, dbc.Alert("Seleccioná dos activos diferentes.",
                                color="warning", className="mt-2 py-1",
                                style={"fontSize": "0.82rem"})

    pairs = svc.get_paired_prices(asset1_id, asset2_id)
    if not pairs:
        return empty, dbc.Alert("Sin precios en común para ambos activos.",
                                color="warning", className="mt-2 py-1",
                                style={"fontSize": "0.82rem"})

    label1 = svc.get_asset_label(asset1_id)
    label2 = svc.get_asset_label(asset2_id)

    xs    = [p["p1"]   for p in pairs]
    ys    = [p["p2"]   for p in pairs]
    dates = [p["date"] for p in pairs]
    n     = len(pairs)

    hover = [
        f"<b>{dates[i]}</b><br>{label1.split(' — ')[0]}: {xs[i]:.6g}"
        f"<br>{label2.split(' — ')[0]}: {ys[i]:.6g}"
        for i in range(n)
    ]

    fig = go.Figure()

    fig.add_trace(go.Scatter(
        x=xs, y=ys,
        mode="markers",
        marker=dict(
            size=5,
            color=list(range(n)),
            colorscale="Plasma",
            opacity=0.75,
            showscale=True,
            colorbar=dict(
                title=dict(text="Tiempo", side="right", font=dict(size=10)),
                tickvals=[0, n - 1],
                ticktext=[dates[0], dates[-1]],
                tickfont=dict(size=9),
                thickness=12,
                len=0.6,
            ),
        ),
        hovertemplate="%{customdata}<extra></extra>",
        customdata=hover,
        showlegend=False,
    ))

    if "events" in (show_events_opt or []):
        events = svc.get_events_with_coords(asset1_id, asset2_id, pairs)
        for ev in events:
            fig.add_trace(go.Scatter(
                x=[ev["p1"]], y=[ev["p2"]],
                mode="markers+text",
                marker=dict(
                    size=14, color=ev["color"], symbol="star",
                    line=dict(color="#1f2937", width=1),
                ),
                text=[ev["name"]],
                textposition="top center",
                textfont=dict(color=ev["color"], size=8),
                hovertemplate=(
                    f"<b>{ev['name']}</b><br>"
                    f"{ev['start_date']} → {ev['end_date']}"
                    "<extra></extra>"
                ),
                showlegend=False,
            ))

    fig.update_layout(
        plot_bgcolor=_BG,
        paper_bgcolor=_BG,
        font=dict(color="#dee2e6", size=11),
        xaxis=dict(
            title=label1,
            gridcolor="#1f2937",
            zerolinecolor="#4b5563",
            tickfont=dict(size=10),
        ),
        yaxis=dict(
            title=label2,
            gridcolor="#1f2937",
            zerolinecolor="#4b5563",
            tickfont=dict(size=10),
        ),
        margin=dict(l=60, r=90, t=20, b=50),
        hovermode="closest",
    )

    corr = float(np.corrcoef(xs, ys)[0, 1]) if n > 2 else None
    stats = (
        f"N = {n} puntos  ·  {dates[0]} → {dates[-1]}"
        + (f"  ·  Correlación: {corr:.3f}" if corr is not None else "")
    )
    return fig, stats


def _empty_fig() -> go.Figure:
    fig = go.Figure()
    fig.update_layout(
        plot_bgcolor=_BG, paper_bgcolor=_BG,
        font=dict(color="#dee2e6"),
        xaxis=dict(gridcolor="#1f2937"),
        yaxis=dict(gridcolor="#1f2937"),
        margin=dict(l=60, r=20, t=20, b=50),
    )
    return fig
