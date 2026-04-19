import dash
import dash_bootstrap_components as dbc
from dash import html

from app.components.abm import make_abm_layout

_COLUMNS = [
    {"name": "Nombre", "id": "name"},
    {"name": "Descripción", "id": "description"},
]

_FORM = [
    dbc.Row([
        dbc.Col([dbc.Label("Nombre"), dbc.Input(id="price_sources-f-name", placeholder="Yahoo Finance")]),
    ], className="mb-3"),
    dbc.Row([
        dbc.Col([
            dbc.Label("Descripción"),
            dbc.Textarea(id="price_sources-f-description", placeholder="Descripción de la fuente", rows=3),
        ]),
    ]),
]


def layout(**kwargs):
    from flask_login import current_user
    if not current_user.is_authenticated or not current_user.is_admin:
        return html.Div("Acceso denegado", className="text-danger mt-4")
    return make_abm_layout("price_sources", "Fuentes de Precios", _COLUMNS, _FORM)


dash.register_page(__name__, path="/admin/price-sources", title="Fuentes de precios", layout=layout)
