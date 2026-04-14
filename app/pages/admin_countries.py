import dash
import dash_bootstrap_components as dbc
from dash import html

from app.components.abm import make_abm_layout

_COLUMNS = [
    {"name": "ID", "id": "id"},
    {"name": "Nombre", "id": "name"},
    {"name": "Código ISO", "id": "iso_code"},
]

_FORM = [
    dbc.Row([
        dbc.Col([dbc.Label("Nombre"), dbc.Input(id="countries-f-name", placeholder="Argentina")]),
        dbc.Col([dbc.Label("Código ISO (2-3 letras)"), dbc.Input(id="countries-f-iso_code", placeholder="AR", maxlength=3)]),
    ]),
]


def layout(**kwargs):
    from flask_login import current_user
    if not current_user.is_authenticated or not current_user.is_admin:
        return html.Div("Acceso denegado", className="text-danger mt-4")
    return make_abm_layout("countries", "Países", _COLUMNS, _FORM)


dash.register_page(__name__, path="/admin/countries", title="Países", layout=layout)
