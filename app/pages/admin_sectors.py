import dash
import dash_bootstrap_components as dbc
from dash import html

from app.components.abm import make_abm_layout

_COLUMNS = [
    {"name": "Nombre", "id": "name"},
]

_FORM = [
    dbc.Row([
        dbc.Col([dbc.Label("Nombre"), dbc.Input(id="sectors-f-name", placeholder="Technology")]),
    ]),
]


def layout(**kwargs):
    from flask_login import current_user
    if not current_user.is_authenticated or not current_user.is_admin:
        return html.Div("Acceso denegado", className="text-danger mt-4")
    return make_abm_layout("sectors", "Sectores", _COLUMNS, _FORM)


dash.register_page(__name__, path="/admin/sectors", title="Sectores", layout=layout)
