from dash import Input, Output, callback, dcc, html
import dash_bootstrap_components as dbc

import app.services.screener_service as scr_svc
from app.pages.market_map import _build_table, _build_quadrant_figure


@callback(
    Output("market-map-quad-controls", "style"),
    Input("market-map-tabs", "active_tab"),
)
def toggle_quad_controls(active_tab):
    if active_tab == "cuadrantes":
        return {"display": "block"}
    return {"display": "none"}


@callback(
    Output("market-map-content", "children"),
    Input("market-map-tabs", "active_tab"),
    Input("market-map-quad-dim", "value"),
)
def render_map(active_tab, quad_dim):
    if not active_tab:
        return html.Div()

    data = scr_svc.get_market_map_data()

    if active_tab == "cuadrantes":
        dim_key = quad_dim or "sector"
        dim_data = data.get(dim_key, {})
        if not dim_data:
            return html.P("Sin datos.", className="text-muted mt-3")
        return dcc.Graph(
            figure=_build_quadrant_figure(dim_data),
            style={"height": "520px"},
            config={"displayModeBar": False},
        )

    dim_data = data.get(active_tab, {})
    if not dim_data:
        return html.P("Sin datos para esta dimensión.", className="text-muted mt-3")

    return dbc.Row([
        dbc.Col(_build_table(dim_data), md=8, lg=6),
    ])
