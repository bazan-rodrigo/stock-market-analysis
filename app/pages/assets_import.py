import dash
import dash_ag_grid as dag
import dash_bootstrap_components as dbc
from dash import dcc, html

from app.components.grids import (
    DEFAULT_COL_DEF, THEME_CLASS, grid_options, import_status_conditions, text_col,
)
from app.components.help import page_header
from app.components.ui_constants import TEXT_BODY

_LOG_COLUMNS = [
    text_col("ticker",       "Ticker",  width=120),
    text_col("status",       "Estado",  width=110),
    text_col("detail",       "Detalle", width=420),
    text_col("attempted_at", "Fecha",   width=160),
]


def layout(**kwargs):
    from flask_login import current_user
    if not current_user.is_authenticated or not current_user.is_admin:
        return html.Div("Acceso denegado", className="text-danger mt-4")

    return html.Div([
        page_header("Importar activos desde Excel", "importar-activos", className="mb-4"),
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
                    type="circle", color=TEXT_BODY,
                ),
                dcc.Store(id="import-file-store"),
            ])), md=8),
        ], className="mb-4"),
        dbc.Card(dbc.CardBody([
            html.Div([
                html.H5("Resultados", className="d-inline-block me-3"),
                dbc.Button("Limpiar resultados", id="import-btn-clear", color="link", size="sm"),
            ], className="d-flex align-items-center mb-3"),
            dag.AgGrid(
                id="import-log-table",
                columnDefs=_LOG_COLUMNS,
                rowData=[],
                className=THEME_CLASS,
                style={"height": "460px", "width": "100%"},
                defaultColDef=DEFAULT_COL_DEF,
                getRowStyle={"styleConditions": import_status_conditions()},
                dashGridOptions=grid_options(),
            ),
        ])),
    ])


# OJO: no registrar páginas bajo /assets/... — esa ruta la reserva Dash para
# los archivos estáticos (assets/), y una carga directa de la URL (o un F5)
# devuelve 404 del server aunque la navegación client-side funcione
dash.register_page(__name__, path="/assets-import", title="Importar activos", layout=layout)
