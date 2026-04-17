import dash
import dash_bootstrap_components as dbc
from dash import html

_TABLES_INFO = [
    ("prices",            "Historia de precios"),
    ("price_update_log",  "Logs de actualización de precios"),
    ("screener_snapshot", "Snapshots del screener"),
    ("market_event",      "Eventos de mercado"),
    ("import_log",        "Logs de importación"),
    ("catalog_aliases",   "Aliases del catálogo"),
    ("assets",            "Activos"),
    ("industries",        "Industrias"),
    ("markets",           "Mercados"),
    ("instrument_types",  "Tipos de instrumento"),
    ("sectors",           "Sectores"),
    ("countries",         "Países"),
    ("currencies",        "Monedas"),
    ("price_sources",     "Fuentes de precios"),
]


def layout(**kwargs):
    from flask_login import current_user
    if not current_user.is_authenticated or not current_user.is_admin:
        return html.Div("Acceso denegado", className="text-danger mt-4")

    rows = [
        html.Tr([html.Td(table), html.Td(label)])
        for table, label in _TABLES_INFO
    ]

    return html.Div([
        html.H3("Limpieza de datos", className="mb-3"),
        dbc.Alert([
            html.H5("⚠ Esta operación es irreversible", className="alert-heading"),
            html.P(
                "Se eliminarán permanentemente todos los datos operativos. "
                "Los usuarios no serán afectados.",
                className="mb-0",
            ),
        ], color="danger", className="mb-4"),

        html.H6("Tablas que se limpiarán:", className="mb-2"),
        dbc.Table(
            [html.Tbody(rows)],
            bordered=True, size="sm", className="mb-4 w-auto",
        ),

        dbc.Button(
            "Limpiar datos",
            id="cleanup-btn-open",
            color="danger",
            size="lg",
        ),

        dbc.Alert(id="cleanup-alert", is_open=False, dismissable=True, className="mt-3"),

        dbc.Modal([
            dbc.ModalHeader(dbc.ModalTitle("⚠ Confirmar limpieza")),
            dbc.ModalBody([
                html.P("Se eliminarán permanentemente:"),
                html.Ul([html.Li(label) for _, label in _TABLES_INFO]),
                html.P("Los usuarios se conservan.", className="fw-bold mt-2"),
                html.Hr(),
                dbc.Checkbox(
                    id="cleanup-check",
                    label="Entiendo que esta acción es irreversible y no tiene vuelta atrás.",
                    value=False,
                ),
            ]),
            dbc.ModalFooter([
                dbc.Button(
                    "Sí, limpiar todo",
                    id="cleanup-btn-confirm",
                    color="danger",
                    disabled=True,
                ),
                dbc.Button("Cancelar", id="cleanup-btn-cancel", color="secondary", className="ms-2"),
            ]),
        ], id="cleanup-modal", is_open=False),
    ])


dash.register_page(__name__, path="/admin/cleanup", title="Limpieza de datos", layout=layout)
