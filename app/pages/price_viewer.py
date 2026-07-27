import dash
import dash_ag_grid as dag
import dash_bootstrap_components as dbc
from dash import dcc, html

from app.components.grids import (
    DEFAULT_COL_DEF, THEME_CLASS, grid_options, to_column_defs,
)
from app.components.help import page_header

_HISTORY_COLUMNS = [
    {"name": "Fecha",     "id": "date"},
    {"name": "Apertura",  "id": "open",   "type": "numericColumn", "width": 110},
    {"name": "Máx",       "id": "high",   "type": "numericColumn", "width": 110},
    {"name": "Mín",       "id": "low",    "type": "numericColumn", "width": 110},
    {"name": "Cierre",    "id": "close",  "type": "numericColumn", "width": 110},
    {"name": "Volumen",   "id": "volume", "type": "numericColumn", "width": 130},
]

_LATEST_COLUMNS = [
    {"name": "Ticker",    "id": "ticker"},
    {"name": "Nombre",    "id": "name"},
    {"name": "Fecha",     "id": "date"},
    {"name": "Apertura",  "id": "open",             "type": "numericColumn", "width": 110},
    {"name": "Máx",       "id": "high",             "type": "numericColumn", "width": 110},
    {"name": "Mín",       "id": "low",              "type": "numericColumn", "width": 110},
    {"name": "Cierre",    "id": "close",            "type": "numericColumn", "width": 110},
    {"name": "Volumen",   "id": "volume",           "type": "numericColumn", "width": 130},
    {"name": "Moneda",    "id": "currency"},
    {"name": "Tipo",      "id": "instrument_type"},
    {"name": "País",      "id": "country"},
    {"name": "Mercado",   "id": "market"},
    {"name": "Fuente",    "id": "price_source"},
]

_GRID_COMMON = dict(
    className=THEME_CLASS,
    style={"height": "calc(100vh - 300px)", "width": "100%"},
    defaultColDef=DEFAULT_COL_DEF,
    dashGridOptions=grid_options(),
)


def layout(**kwargs):
    from flask_login import current_user
    if not current_user.is_authenticated:
        return html.Div()

    return html.Div([
        page_header("Visualizador de precios", "visualizador-de-precios", className="mb-3"),

        dbc.RadioItems(
            id="pv-mode",
            options=[
                {"label": "Último precio de todos los instrumentos", "value": "latest"},
                {"label": "Historia de un instrumento", "value": "history"},
            ],
            value="latest",
            inline=True,
            className="mb-3",
        ),

        # ── Controles modo historia ──────────────────────────────────────
        html.Div(id="pv-history-controls", style={"display": "none"}, children=[
            dbc.Row([
                dbc.Col([
                    dbc.Label("Instrumento"),
                    dcc.Dropdown(id="pv-asset-select", placeholder="Seleccioná un activo..."),
                ], md=4),
            ], className="mb-3"),
        ]),

        dbc.Alert(id="pv-alert", is_open=False, dismissable=True, color="warning"),

        html.Div(id="pv-result-info", className="text-muted mb-1"),

        # ── Tabla historia ───────────────────────────────────────────────
        html.Div(id="pv-history-table-container", children=[
            dag.AgGrid(
                id="pv-history-table",
                columnDefs=to_column_defs(_HISTORY_COLUMNS),
                rowData=[],
                **_GRID_COMMON,
            ),
        ]),

        # ── Tabla último precio ──────────────────────────────────────────
        html.Div(id="pv-latest-table-container", style={"display": "none"}, children=[
            dag.AgGrid(
                id="pv-latest-table",
                columnDefs=to_column_defs(_LATEST_COLUMNS),
                rowData=[],
                **_GRID_COMMON,
            ),
        ]),
    ])


dash.register_page(__name__, path="/price-viewer", title="Precios", layout=layout)
