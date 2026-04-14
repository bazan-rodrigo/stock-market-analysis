import dash
import dash_bootstrap_components as dbc
from dash import html

from app.components.abm import make_abm_layout

_COLUMNS = [
    {"name": "Nombre", "id": "name"},
    {"name": "Sector", "id": "sector_name"},
]

_FORM = [
    dbc.Row([
        dbc.Col([dbc.Label("Nombre"), dbc.Input(id="industries-f-name", placeholder="Consumer Electronics")]),
        dbc.Col([dbc.Label("Sector"), dbc.Select(id="industries-f-sector_id", options=[])]),
    ]),
]


def layout(**kwargs):
    from flask_login import current_user
    if not current_user.is_authenticated or not current_user.is_admin:
        return html.Div("Acceso denegado", className="text-danger mt-4")
    return make_abm_layout("industries", "Industrias", _COLUMNS, _FORM)


dash.register_page(__name__, path="/admin/industries", title="Industrias", layout=layout)
