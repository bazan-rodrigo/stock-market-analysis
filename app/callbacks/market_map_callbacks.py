import logging
from datetime import date

from dash import Input, Output, callback, dcc, html
import dash_bootstrap_components as dbc

import app.services.technical_service as scr_svc
from app.pages.market_map import _build_table, _build_quadrant_figure

logger = logging.getLogger(__name__)


def _map_error(msg):
    return dbc.Alert(f"Error al cargar el mapa: {msg}", color="danger",
                     className="mt-3", style={"fontSize": "0.85rem"})


@callback(
    Output("market-map-store", "data"),
    Input("market-map-date", "date"),
)
def compute_map(date_str):
    """Calcula los scores de grupo AL VUELO para la fecha elegida (todas las
    dimensiones de una) y los deja en el Store. Corre solo al cambiar la fecha;
    el cambio de pestaña lo sirve render_map sin recalcular."""
    try:
        target = date.fromisoformat(date_str) if date_str else None
        return {"data": scr_svc.get_market_map_data(target)}
    except Exception as exc:
        logger.exception("market_map: fallo el cálculo al vuelo")
        return {"error": str(exc)}


@callback(
    Output("market-map-content", "children"),
    Input("market-map-store", "data"),
    Input("market-map-tabs", "active_tab"),
)
def render_map(store, active_tab):
    if not store:
        return html.Div()               # aún computando (primer render)
    if store.get("error"):
        return _map_error(store["error"])

    dim_data = (store.get("data") or {}).get(active_tab, {}) if active_tab else {}
    if not dim_data:
        return html.P("Sin datos para esta dimensión.", className="text-muted mt-3",
                      style={"fontSize": "0.82rem"})

    return dbc.Row([
        dbc.Col(_build_table(dim_data), md=5),
        dbc.Col(
            dcc.Graph(
                figure=_build_quadrant_figure(dim_data),
                style={"height": "460px"},
                config={"displayModeBar": False},
            ),
            md=7,
        ),
    ], className="g-3")
