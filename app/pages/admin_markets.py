import dash
import dash_bootstrap_components as dbc
from dash import dcc, html

from app.components.abm import make_abm_layout

_COLUMNS = [
    {"name": "Nombre", "id": "name"},
    {"name": "País", "id": "country_name"},
]

_FORM = [
    dbc.Row([
        dbc.Col([dbc.Label("Nombre"), dbc.Input(id="markets-f-name", placeholder="NYSE")]),
        dbc.Col([dbc.Label("País"), dbc.Select(id="markets-f-country_id", options=[])]),
    ], className="mb-3"),
    dbc.Row([
        dbc.Col([
            dbc.Label("Benchmark"),
            dcc.Dropdown(id="markets-f-benchmark_id", placeholder="Sin benchmark (opcional)",
                         clearable=True, style={"fontSize": "0.9rem"}),
        ]),
    ]),
]


def layout(**kwargs):
    from flask_login import current_user
    if not current_user.is_authenticated or not current_user.is_admin:
        return html.Div("Acceso denegado", className="text-danger mt-4")
    return make_abm_layout("markets", "Mercados / Bolsas", _COLUMNS, _FORM)


dash.register_page(__name__, path="/admin/markets", title="Mercados", layout=layout)
