import dash
import dash_bootstrap_components as dbc
from dash import dash_table, dcc, html

from app.components.table_styles import FILTER, HEADER, DATA, CELL, SELECTED_ROW

_HISTORY_COLUMNS = [
    {"name": "Fecha",     "id": "date"},
    {"name": "Apertura",  "id": "open",   "type": "numeric", "format": {"specifier": ".2f"}},
    {"name": "Máx",       "id": "high",   "type": "numeric", "format": {"specifier": ".2f"}},
    {"name": "Mín",       "id": "low",    "type": "numeric", "format": {"specifier": ".2f"}},
    {"name": "Cierre",    "id": "close",  "type": "numeric", "format": {"specifier": ".2f"}},
    {"name": "Volumen",   "id": "volume", "type": "numeric"},
]

_LATEST_COLUMNS = [
    {"name": "Ticker",  "id": "ticker"},
    {"name": "Nombre",  "id": "name"},
    {"name": "Fecha",   "id": "date"},
    {"name": "Cierre",  "id": "close",  "type": "numeric", "format": {"specifier": ".2f"}},
    {"name": "Volumen", "id": "volume", "type": "numeric"},
]

_DT_COMMON = dict(
    style_table={"overflowX": "auto"},
    style_header=HEADER,
    style_data=DATA,
    style_cell=CELL,
    style_filter=FILTER,
    style_data_conditional=SELECTED_ROW,
    sort_action="native",
    filter_action="native",
    page_size=50,
)


def layout(**kwargs):
    from flask_login import current_user
    if not current_user.is_authenticated:
        return html.Div()

    return html.Div([
        html.H3("Visualizador de precios", className="mb-3"),

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
                dbc.Col([
                    dbc.Label("\u00a0"),
                    dbc.Button("Consultar", id="pv-btn-query", color="primary", className="d-block"),
                ], md=2),
            ], className="mb-3"),
        ]),

        dbc.Alert(id="pv-alert", is_open=False, dismissable=True, color="warning"),

        html.Div(id="pv-result-info", className="text-muted mb-1"),

        # ── Tabla historia ───────────────────────────────────────────────
        html.Div(id="pv-history-table-container", children=[
            dash_table.DataTable(
                id="pv-history-table",
                columns=_HISTORY_COLUMNS,
                data=[],
                **_DT_COMMON,
            ),
        ]),

        # ── Tabla último precio ──────────────────────────────────────────
        html.Div(id="pv-latest-table-container", style={"display": "none"}, children=[
            dash_table.DataTable(
                id="pv-latest-table",
                columns=_LATEST_COLUMNS,
                data=[],
                **_DT_COMMON,
            ),
        ]),
    ])


dash.register_page(__name__, path="/price-viewer", title="Precios", layout=layout)
