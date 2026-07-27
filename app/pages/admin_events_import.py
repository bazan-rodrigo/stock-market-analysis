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
    text_col("nombre",  "Nombre",  width=240),
    text_col("status",  "Estado",  width=110),
    text_col("detail",  "Detalle", width=460),
]


def layout(**kwargs):
    from flask_login import current_user
    if not current_user.is_authenticated or not current_user.is_admin:
        return html.Div("Acceso denegado", className="text-danger mt-4")

    return html.Div([
        page_header("Importar eventos de mercado", "importar-eventos", className="mb-4"),
        dbc.Row([
            dbc.Col(dbc.Card(dbc.CardBody([
                html.H5("1. Descargar template"),
                html.P(
                    "El template incluye los eventos más relevantes para Global, "
                    "EEUU y Argentina precargados.",
                    className="small text-muted",
                ),
                dbc.Button("Descargar template", id="ev-import-btn-template",
                           color="secondary", size="sm"),
                dcc.Download(id="ev-import-download"),
            ])), md=4),
            dbc.Col(dbc.Card(dbc.CardBody([
                html.H5("2. Subir archivo"),
                dcc.Upload(
                    id="ev-import-upload",
                    children=dbc.Button("Seleccionar archivo .xlsx",
                                        color="primary", size="sm"),
                    accept=".xlsx",
                ),
                html.Div(id="ev-import-filename", className="text-muted mt-1 small"),
                dbc.Alert(id="ev-import-alert", is_open=False,
                          dismissable=True, className="mt-2"),
                dcc.Interval(id="ev-import-interval", interval=800, disabled=True, n_intervals=0),
                dbc.Progress(id="ev-import-progress", value=0, striped=True, animated=True,
                             label="", className="mt-2", style={"display": "none"}),
                dcc.Loading(
                    html.Div([
                        dbc.Button("Importar", id="ev-import-btn-run", color="success",
                                   size="sm", disabled=True, className="mt-2"),
                    ]),
                    type="circle", color=TEXT_BODY,
                ),
                dcc.Store(id="ev-import-file-store"),
            ])), md=8),
        ], className="mb-4"),
        dbc.Card(dbc.CardBody([
            html.Div([
                html.H5("Resultados", className="d-inline-block me-3"),
                dbc.Button("Limpiar resultados", id="ev-import-btn-clear",
                           color="link", size="sm"),
            ], className="d-flex align-items-center mb-3"),
            dag.AgGrid(
                id="ev-import-log-table",
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


dash.register_page(
    __name__,
    path="/admin/events/import",
    title="Importar eventos",
    layout=layout,
)
