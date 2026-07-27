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
    text_col("ticker",          "Ticker", width=110, pinned="left"),
    text_col("name",            "Nombre", width=200),
    text_col("last_attempt_at", "Último intento", width=150),
    status_col("result",        "Resultado"),
    text_col("error_detail",    "Detalle error", width=260),
    text_col("last_indicator_at", "Último indicador", width=150),
    status_col("indicator_result", "Resultado indicador", width=140),
    text_col("indicator_error_detail", "Detalle error indicador", width=260),
]


def layout(**kwargs):
    from flask_login import current_user
    if not current_user.is_authenticated or not current_user.is_admin:
        return html.Div("Acceso denegado", className="text-danger mt-4")

    return html.Div([
        dcc.Interval(id="fund-upd-interval", interval=800, disabled=True, n_intervals=0),

        html.Div([
            page_header("Actualización de Fundamentales", "actualizacion-de-fundamentales", className="d-inline-block me-3"),
            dbc.Button("Limpiar log", id="fund-upd-btn-clear",
                       color="link", size="sm"),
        ], className="d-flex align-items-center mb-2"),

        html.Div([
            dbc.Button("Actualizar seleccionados", id="fund-upd-btn-one",
                       color="secondary", size="sm", disabled=True, className="me-2"),
            dbc.Button("Reintentar fallidos", id="fund-upd-btn-retry",
                       color="warning", size="sm", className="me-2"),
            dbc.Button("Redescargar completo (seleccionados)", id="fund-upd-btn-redownload-selected",
                       color="danger", size="sm", outline=True, disabled=True),
        ], className="mb-3"),

        dbc.Alert(id="fund-upd-alert", is_open=False, dismissable=True),

        dbc.Progress(id="fund-upd-progress", value=0, striped=True, animated=True,
                     label="", className="mb-3", style={"display": "none"}),

        dag.AgGrid(
            id="fund-upd-table",
            columnDefs=_LOG_COLUMNS,
            rowData=[],
            className=THEME_CLASS,
            style={"height": "calc(100vh - 330px)", "width": "100%"},
            defaultColDef=DEFAULT_COL_DEF,
            getRowStyle={"styleConditions": status_conditions(
                "result", dim_placeholder=True)},
            dashGridOptions=grid_options(rowSelection=multi_selection()),
        ),

        dbc.Modal([
            dbc.ModalHeader(dbc.ModalTitle("Confirmar operación")),
            dbc.ModalBody(
                "Esta acción borrará el historial trimestral de los activos "
                "seleccionados, lo redescargará desde la fuente y recalculará "
                "sus ratios fundamentales por completo. ¿Confirmás?"
            ),
            dbc.ModalFooter([
                dbc.Button("Sí, borrar y redescargar", id="fund-upd-btn-redownload-selected-confirm", color="danger"),
                dbc.Button("Cancelar", id="fund-upd-btn-redownload-selected-cancel", color="secondary", className="ms-2"),
            ]),
        ], id="fund-upd-redownload-selected-modal", is_open=False),
    ])


dash.register_page(
    __name__,
    path="/admin/fundamental-update",
    title="Actualización de Fundamentales",
    layout=layout,
)
