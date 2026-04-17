import dash
import dash_bootstrap_components as dbc
from dash import dash_table, dcc, html
from app.components.table_styles import FILTER, HEADER, DATA, CELL

_LOG_COLUMNS = [
    {"name": "Ticker", "id": "ticker"},
    {"name": "Estado", "id": "status"},
    {"name": "Detalle", "id": "detail"},
    {"name": "Fecha", "id": "attempted_at"},
]


def layout(**kwargs):
    from flask_login import current_user
    if not current_user.is_authenticated or not current_user.is_admin:
        return html.Div("Acceso denegado", className="text-danger mt-4")

    return html.Div([
        html.H3("Importar activos desde Excel", className="mb-4"),
        dbc.Row([
            dbc.Col(dbc.Card(dbc.CardBody([
                html.H5("1. Descargar template"),
                html.P("Descargá el archivo Excel con las columnas necesarias, completalo y subilo.", className="small text-muted"),
                dbc.Button("Descargar template", id="import-btn-template", color="secondary", size="sm"),
                dcc.Download(id="import-download-template"),
            ])), md=4),
            dbc.Col(dbc.Card(dbc.CardBody([
                html.H5("2. Subir archivo"),
                dcc.Upload(
                    id="import-upload",
                    children=dbc.Button("Seleccionar archivo .xlsx", color="primary", size="sm"),
                    accept=".xlsx",
                ),
                html.Div(id="import-filename", className="text-muted mt-1 small"),
                dbc.Alert(id="import-alert", is_open=False, dismissable=True, className="mt-2"),
                dcc.Interval(id="import-interval", interval=800, disabled=True, n_intervals=0),
                dbc.Progress(id="import-progress", value=0, striped=True, animated=True,
                             label="", className="mt-2", style={"display": "none"}),
                dcc.Loading(
                    html.Div([
                        dbc.Button("Importar", id="import-btn-run", color="success", size="sm",
                                   disabled=True, className="mt-2"),
                        html.Span(id="import-running-msg", className="ms-2 text-muted small"),
                    ], className="d-flex align-items-center"),
                    type="circle", color="#dee2e6",
                ),
                dcc.Store(id="import-file-store"),
            ])), md=8),
        ], className="mb-4"),
        dbc.Card(dbc.CardBody([
            html.Div([
                html.H5("Resultados", className="d-inline-block me-3"),
                dbc.Button("Limpiar resultados", id="import-btn-clear", color="link", size="sm"),
            ], className="d-flex align-items-center mb-3"),
            dash_table.DataTable(
                id="import-log-table",
                columns=_LOG_COLUMNS,
                data=[],
                style_table={"overflowX": "auto"},
                style_header=HEADER,
                style_data=DATA,
                style_cell=CELL,
                style_filter=FILTER,
                style_data_conditional=[
                    {"if": {"filter_query": "{status} = imported"}, "color": "#4caf50"},
                    {"if": {"filter_query": "{status} = error"}, "color": "#ef5350"},
                    {"if": {"filter_query": "{status} = skipped"}, "color": "#ff9800"},
                ],
                filter_action="native",
                page_size=30,
                sort_action="native",
            ),
        ])),
    ])


dash.register_page(__name__, path="/assets/import", title="Importar activos", layout=layout)
