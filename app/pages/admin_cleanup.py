import dash
import dash_bootstrap_components as dbc
from dash import dcc, html

from app.components.help import help_link

# El alcance de la limpieza vive en app/services/cleanup_service.py — única
# fuente de verdad, compartida con scripts/clean_data.py. No duplicar la lista
# acá: fue exactamente así como la pantalla quedó desactualizada.
from app.services.cleanup_service import PRESERVED_INFO, TABLES_INFO


def layout(**kwargs):
    from flask_login import current_user
    if not current_user.is_authenticated or not current_user.is_admin:
        return html.Div("Acceso denegado", className="text-danger mt-4")

    rows = [
        html.Tr([
            html.Td(html.Code(table), className="text-nowrap"),
            html.Td(label),
        ])
        for table, label in TABLES_INFO
    ]

    # ── Columna izquierda: uso de espacio ─────────────────────────────────
    col_espacio = [
        html.H4("Uso de espacio en disco", className="mb-2"),
        dbc.Button("Actualizar", id="dbsize-refresh", color="secondary",
                   outline=True, size="sm", className="mb-3"),
        dcc.Loading(html.Div(id="dbsize-content"), type="default"),
    ]

    # ── Columna derecha: recuperar espacio (arriba) + borrado (abajo) ──────
    col_acciones = [
        html.H4("Recuperar espacio (VACUUM)", className="mb-2"),
        dbc.Alert(
            [
                html.P(
                    "Compacta las tablas del pipeline (indicadores, señales, "
                    "estrategias, precios…) y devuelve al disco el espacio de "
                    "las tuplas muertas que dejan los recálculos (bloat). "
                    "NO borra datos.",
                    className="mb-1"),
                html.P(
                    "Toma un lock exclusivo por tabla mientras dura — conviene "
                    "correrlo en un momento tranquilo (sin corridas del pipeline).",
                    className="mb-0 text-muted small"),
            ],
            color="info", className="mb-3"),
        dbc.Button("Recuperar espacio", id="vacuum-btn", color="primary"),
        dcc.Interval(id="vacuum-interval", interval=800, disabled=True, n_intervals=0),
        dbc.Progress(id="vacuum-progress", value=100, striped=True, animated=True,
                     label="Compactando...", className="mt-3", style={"display": "none"}),
        dbc.Alert(id="vacuum-alert", is_open=False, dismissable=True, className="mt-3"),

        html.Hr(className="my-4"),
        html.H4("Borrado de datos operativos", className="mb-2"),
        dbc.Alert([
            html.H5("⚠ Esta operación es irreversible", className="alert-heading"),
            html.P(
                "Se eliminarán los datos derivados del pipeline (indicadores, "
                "señales, estrategias, fundamentales) y las corridas guardadas "
                "de backtest y cartera.",
                className="mb-1"),
            html.P(
                "Todo lo derivado se regenera con los botones «Recalcular "
                "completo» del Centro de Datos. Las corridas guardadas NO se "
                "recalculan: hay que volver a correrlas.",
                className="mb-0 small"),
        ], color="danger", className="mb-4"),

        html.H6("Qué se borra:", className="mb-2"),
        dbc.Table(
            [html.Tbody(rows)],
            bordered=True, size="sm", className="mb-3 w-auto",
        ),

        html.H6("Qué se conserva:", className="mb-2"),
        html.Ul([html.Li(x) for x in PRESERVED_INFO],
                className="mb-4 small text-muted"),

        dbc.Button(
            "Limpiar datos",
            id="cleanup-btn-open",
            color="danger",
            size="lg",
        ),
        dcc.Interval(id="cleanup-interval", interval=600, disabled=True, n_intervals=0),
        dbc.Progress(id="cleanup-progress", value=100, striped=True, animated=True,
                     label="Procesando...", className="mt-3", style={"display": "none"}),
        dbc.Alert(id="cleanup-alert", is_open=False, dismissable=True, className="mt-3"),
    ]

    return html.Div([
        html.H3(["Limpieza de datos ", help_link("limpieza-de-datos")], className="mb-3"),

        dbc.Row([
            dbc.Col(col_espacio, md=6),
            dbc.Col(col_acciones, md=6),
        ], className="g-4"),

        dbc.Modal([
            dbc.ModalHeader(dbc.ModalTitle("⚠ Confirmar limpieza")),
            dbc.ModalBody([
                html.P("Se eliminarán permanentemente:"),
                html.Ul([html.Li(label) for _, label in TABLES_INFO]),
                html.P(
                    "Se conservan activos, precios, catálogos, definiciones, "
                    "carteras y usuarios.",
                    className="fw-bold mt-2"),
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
