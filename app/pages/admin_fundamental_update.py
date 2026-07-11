import dash
import dash_bootstrap_components as dbc
from dash import dash_table, dcc, html

from app.components.table_styles import CELL, DATA, FILTER, HEADER, SELECTED_ROW

_LOG_COLUMNS = [
    {"name": "Ticker",         "id": "ticker"},
    {"name": "Nombre",         "id": "name"},
    {"name": "Último intento", "id": "last_attempt_at"},
    {"name": "Resultado",      "id": "result"},
    {"name": "Detalle error",  "id": "error_detail"},
    {"name": "Último indicador",        "id": "last_indicator_at"},
    {"name": "Resultado indicador",     "id": "indicator_result"},
    {"name": "Detalle error indicador", "id": "indicator_error_detail"},
]


def layout(**kwargs):
    from flask_login import current_user
    if not current_user.is_authenticated or not current_user.is_admin:
        return html.Div("Acceso denegado", className="text-danger mt-4")

    return html.Div([
        dcc.Interval(id="fund-upd-interval", interval=800, disabled=True, n_intervals=0),

        html.Div([
            html.H3("Actualización de Fundamentales", className="d-inline-block me-3"),
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

        dash_table.DataTable(
            id="fund-upd-table",
            columns=_LOG_COLUMNS,
            data=[],
            row_selectable="multi",
            selected_rows=[],
            style_table={"overflowX": "auto"},
            style_header=HEADER,
            style_data=DATA,
            style_cell=CELL,
            style_filter=FILTER,
            style_data_conditional=SELECTED_ROW + [
                {"if": {"filter_query": '{result} = "Éxito"'}, "color": "#4caf50"},
                {"if": {"filter_query": '{result} = "Error"'}, "color": "#ef5350"},
                {"if": {"filter_query": '{result} = "—"'},     "color": "#6b7280"},
                {"if": {"filter_query": '{indicator_result} = "Éxito"', "column_id": "indicator_result"},
                 "color": "#4caf50"},
                {"if": {"filter_query": '{indicator_result} = "Error"', "column_id": "indicator_result"},
                 "color": "#ef5350"},
            ],
            page_size=30,
            sort_action="native",
            filter_action="native",
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
