import dash
import dash_ag_grid as dag
import dash_bootstrap_components as dbc
from dash import dcc, html

from app.components.grids import (
    DEFAULT_COL_DEF, THEME_CLASS, grid_options, multi_selection,
    status_col, status_conditions, text_col,
)
from app.components.help import page_header

_LOG_COLUMNS = [
    text_col("ticker",      "Ticker", width=110, pinned="left"),
    text_col("asset_name",  "Nombre", width=200),
    text_col("last_attempt_at", "Último intento", width=150),
    status_col("result",    "Resultado"),
    text_col("error_detail", "Detalle error", width=260),
    text_col("last_indicator_at", "Último indicador", width=150),
    status_col("indicator_result", "Resultado indicador", width=140),
    text_col("indicator_error_detail", "Detalle error indicador", width=260),
]


def layout(**kwargs):
    from flask_login import current_user
    if not current_user.is_authenticated or not current_user.is_admin:
        return html.Div("Acceso denegado", className="text-danger mt-4")

    return html.Div([
        html.Div([
            page_header("Actualización de precios", "actualizacion-de-precios", className="d-inline-block me-3"),
            dbc.Button("Limpiar log", id="prices-btn-clear-log", color="link", size="sm"),
        ], className="d-flex align-items-center mb-2"),
        html.Div([
            dbc.Button("Actualizar seleccionados", id="prices-btn-one", color="secondary", size="sm", disabled=True, className="me-2"),
            dbc.Button("Recalcular seleccionados (completo)", id="prices-btn-indicators",
                       color="secondary", size="sm", disabled=True, className="me-2"),
            dbc.Button("Reintentar fallidos", id="prices-btn-retry", color="warning", size="sm", className="me-2"),
            dbc.Button("Redescargar completo (seleccionados)", id="prices-btn-redownload-selected",
                       color="danger", size="sm", outline=True, disabled=True, className="me-2"),
        ], className="mb-3"),
        dbc.Alert(id="prices-alert", is_open=False, dismissable=True),
        dcc.Interval(id="prices-interval", interval=800, disabled=True, n_intervals=0),
        dbc.Progress(id="prices-progress", value=0, striped=True, animated=True,
                     label="", className="mb-3", style={"display": "none"}),
        dag.AgGrid(
            id="prices-log-table",
            columnDefs=_LOG_COLUMNS,
            rowData=[],
            className=THEME_CLASS,
            style={"height": "calc(100vh - 330px)", "width": "100%"},
            defaultColDef=DEFAULT_COL_DEF,
            # El resultado tiñe la fila entera (no solo su celda): de un vistazo
            # se ve qué activos fallaron sin leer columna por columna.
            getRowStyle={"styleConditions": status_conditions("result")},
            dashGridOptions=grid_options(rowSelection=multi_selection()),
        ),
        dbc.Modal([
            dbc.ModalHeader(dbc.ModalTitle("Confirmar operación")),
            dbc.ModalBody(
                "Esta acción borrará toda la historia de precios de los activos "
                "seleccionados, la redescargará desde Yahoo Finance y recalculará "
                "sus indicadores y ratios fundamentales por completo. ¿Confirmás?"
            ),
            dbc.ModalFooter([
                dbc.Button("Sí, borrar y redescargar", id="prices-btn-redownload-selected-confirm", color="danger"),
                dbc.Button("Cancelar", id="prices-btn-redownload-selected-cancel", color="secondary", className="ms-2"),
            ]),
        ], id="prices-redownload-selected-modal", is_open=False),
    ])


dash.register_page(__name__, path="/prices", title="Actualización de precios", layout=layout)
