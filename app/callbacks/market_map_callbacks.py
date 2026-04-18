from dash import Input, Output, callback
import dash_bootstrap_components as dbc
from dash import html

import app.services.screener_service as scr_svc
from app.pages.market_map import _build_table


@callback(
    Output("market-map-content", "children"),
    Input("market-map-tabs", "active_tab"),
)
def render_map(active_tab):
    if not active_tab:
        return html.Div()

    data = scr_svc.get_market_map_data()
    dim_data = data.get(active_tab, {})

    if not dim_data:
        return html.P("Sin datos para esta dimensión.", className="text-muted mt-3")

    return dbc.Row([
        dbc.Col(_build_table(dim_data), md=8, lg=6),
    ])
