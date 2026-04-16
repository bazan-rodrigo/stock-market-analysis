import dash
import dash_bootstrap_components as dbc
from dash import dcc, html

from app.components.abm import make_abm_layout

_SCOPE_OPTIONS = [
    {"label": "Global (todos los activos)", "value": "global"},
    {"label": "País",                        "value": "country"},
    {"label": "Activo específico",           "value": "asset"},
]

_COLOR_OPTIONS = [
    {"label": "Naranja",  "value": "#ff9800"},
    {"label": "Rojo",     "value": "#ef5350"},
    {"label": "Azul",     "value": "#2196f3"},
    {"label": "Verde",    "value": "#4caf50"},
    {"label": "Violeta",  "value": "#9c27b0"},
    {"label": "Amarillo", "value": "#ffeb3b"},
    {"label": "Cian",     "value": "#00bcd4"},
]

_COLUMNS = [
    {"name": "Nombre",  "id": "name"},
    {"name": "Inicio",  "id": "start_date"},
    {"name": "Fin",     "id": "end_date"},
    {"name": "Alcance", "id": "scope_label"},
    {"name": "Ref.",    "id": "ref_label"},
    {"name": "Color",   "id": "color"},
]

_FORM = [
    dbc.Row([
        dbc.Col([
            dbc.Label("Nombre"),
            dbc.Input(id="events-f-name", placeholder="Ej: Crisis financiera 2008"),
        ]),
    ], className="mb-2"),
    dbc.Row([
        dbc.Col([
            dbc.Label("Fecha inicio"),
            dbc.Input(id="events-f-start_date", type="date"),
        ]),
        dbc.Col([
            dbc.Label("Fecha fin"),
            dbc.Input(id="events-f-end_date", type="date"),
        ]),
    ], className="mb-2"),
    dbc.Row([
        dbc.Col([
            dbc.Label("Alcance"),
            dcc.Dropdown(
                id="events-f-scope",
                options=_SCOPE_OPTIONS,
                value="global",
                clearable=False,
            ),
        ]),
        dbc.Col([
            dbc.Label("Color de zona"),
            dcc.Dropdown(
                id="events-f-color",
                options=_COLOR_OPTIONS,
                value="#ff9800",
                clearable=False,
            ),
        ]),
    ], className="mb-2"),
    # País (visible solo cuando scope=country)
    html.Div(id="events-row-country", children=[
        dbc.Row([
            dbc.Col([
                dbc.Label("País"),
                dcc.Dropdown(id="events-f-country_id", placeholder="Seleccioná un país...", searchable=True),
            ]),
        ], className="mb-2"),
    ], style={"display": "none"}),
    # Activo (visible solo cuando scope=asset)
    html.Div(id="events-row-asset", children=[
        dbc.Row([
            dbc.Col([
                dbc.Label("Activo"),
                dcc.Dropdown(id="events-f-asset_id", placeholder="Seleccioná un activo...", searchable=True),
            ]),
        ], className="mb-2"),
    ], style={"display": "none"}),
]


def layout(**kwargs):
    from flask_login import current_user
    if not current_user.is_authenticated or not current_user.is_admin:
        return html.Div("Acceso denegado", className="text-danger mt-4")
    return make_abm_layout("events", "Eventos de mercado", _COLUMNS, _FORM)


dash.register_page(__name__, path="/admin/events", title="Eventos de mercado", layout=layout)
