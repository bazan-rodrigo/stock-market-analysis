import dash
import dash_bootstrap_components as dbc
from dash import html

from app.components.abm import make_abm_layout

_COLUMNS = [
    {"name": "Nombre", "id": "name"},
    {"name": "Código ISO", "id": "iso_code"},
]

_FORM = [
    dbc.Row([
        dbc.Col([dbc.Label("Nombre"), dbc.Input(id="currencies-f-name", placeholder="Dólar Estadounidense")]),
        dbc.Col([dbc.Label("Código ISO"), dbc.Input(id="currencies-f-iso_code", placeholder="USD", maxlength=10)]),
    ]),
]


def layout(**kwargs):
    from flask_login import current_user
    if not current_user.is_authenticated or not current_user.is_admin:
        return html.Div("Acceso denegado", className="text-danger mt-4")
    return make_abm_layout("currencies", "Monedas", _COLUMNS, _FORM)


dash.register_page(__name__, path="/admin/currencies", title="Monedas", layout=layout)
