import dash
import dash_bootstrap_components as dbc
from dash import html

from app.components.abm import make_abm_layout

_COLUMNS = [
    {"name": "ID", "id": "id"},
    {"name": "Nombre", "id": "name"},
    {"name": "Moneda por defecto", "id": "currency_name"},
]

_FORM = [
    dbc.Row([
        dbc.Col([dbc.Label("Nombre"), dbc.Input(id="instrument_types-f-name", placeholder="Acción")]),
        dbc.Col([dbc.Label("Moneda de cotización por defecto"), dbc.Select(id="instrument_types-f-default_currency_id", options=[])]),
    ]),
]


def layout(**kwargs):
    from flask_login import current_user
    if not current_user.is_authenticated or not current_user.is_admin:
        return html.Div("Acceso denegado", className="text-danger mt-4")
    return make_abm_layout("instrument_types", "Tipos de Instrumento", _COLUMNS, _FORM)


dash.register_page(__name__, path="/admin/instrument-types", title="Tipos de instrumento", layout=layout)
