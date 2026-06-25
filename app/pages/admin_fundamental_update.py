import dash
import dash_bootstrap_components as dbc
from dash import dash_table, html

from app.components.table_styles import CELL, DATA, FILTER, HEADER, SELECTED_ROW

_LOG_COLUMNS = [
    {"name": "Ticker",        "id": "ticker"},
    {"name": "Nombre",        "id": "name"},
    {"name": "Último intento","id": "last_attempt_at"},
    {"name": "Resultado",     "id": "result"},
    {"name": "Detalle error", "id": "error_detail"},
]


def layout(**kwargs):
    from flask_login import current_user
    if not current_user.is_authenticated or not current_user.is_admin:
        return html.Div("Acceso denegado", className="text-danger mt-4")

    return html.Div([
        html.Div([
            html.H3("Actualización de Fundamentales", className="d-inline-block me-3"),
            dbc.Button("Actualizar todos", id="fund-upd-btn-all",
                       color="primary", size="sm", className="me-2"),
            dbc.Button("Reintentar fallidos", id="fund-upd-btn-retry",
                       color="warning", size="sm", className="me-2"),
            dbc.Button("Limpiar log", id="fund-upd-btn-clear",
                       color="link", size="sm"),
        ], className="d-flex align-items-center mb-3"),

        dbc.Alert(id="fund-upd-alert", is_open=False, dismissable=True),

        html.Div(id="fund-upd-progress-area"),

        dash_table.DataTable(
            id="fund-upd-table",
            columns=_LOG_COLUMNS,
            data=[],
            row_selectable="single",
            selected_rows=[],
            style_table={"overflowX": "auto"},
            style_header=HEADER,
            style_data=DATA,
            style_cell=CELL,
            style_filter=FILTER,
            style_data_conditional=SELECTED_ROW + [
                {"if": {"filter_query": '{result} = "Éxito"'}, "color": "#4caf50"},
                {"if": {"filter_query": '{result} = "Error"'}, "color": "#ef5350"},
                {"if": {"filter_query": '{result} = "—"'},    "color": "#6b7280"},
            ],
            page_size=30,
            sort_action="native",
            filter_action="native",
        ),

        html.Div([
            dbc.Button("Actualizar seleccionado", id="fund-upd-btn-one",
                       color="secondary", size="sm", disabled=True),
        ], className="mt-2"),
    ])


dash.register_page(
    __name__,
    path="/admin/fundamental-update",
    title="Actualización de Fundamentales",
    layout=layout,
)
