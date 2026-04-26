import dash
import dash_bootstrap_components as dbc
from dash import dcc, html

_HELP = (
    "Genera automáticamente activos sintéticos para cada activo en la moneda configurada, "
    "dividiendo su precio por el del activo divisor elegido (CCL, MEP, Blue, etc.). "
    "El resultado representa el precio del activo valorizado en la moneda del divisor. "
    "Los sintéticos se crean con fuente 'Calculado' y se actualizan al recalcular sintéticos."
)


def layout(**kwargs):
    from flask_login import current_user
    if not current_user.is_authenticated or not current_user.is_admin:
        return html.Div("Acceso denegado", className="text-danger mt-4")

    return html.Div([
        dcc.Interval(id="ars-interval", interval=1000, disabled=True),
        dcc.Store(id="ars-pending-remove-id"),

        dbc.Modal([
            dbc.ModalHeader(dbc.ModalTitle("Confirmar eliminación"), close_button=False),
            dbc.ModalBody(id="ars-remove-confirm-body"),
            dbc.ModalFooter(
                dcc.Loading(
                    html.Div([
                        dbc.Button("Cancelar", id="ars-btn-cancel-remove",
                                   color="secondary", size="sm", className="me-2"),
                        dbc.Button("Eliminar", id="ars-btn-confirm-remove",
                                   color="danger", size="sm"),
                    ]),
                    type="circle", color="#dc3545",
                )
            ),
        ], id="ars-remove-modal", is_open=False, centered=True),

        html.H4("Activos en Divisa — Sintéticos Automáticos", className="mb-2"),
        dbc.Alert(_HELP, color="info", className="mb-3 small py-2"),

        # ── Configuración de divisores ────────────────────────────────────────
        dbc.Card(dbc.CardBody([
            html.H6("Divisores configurados", className="mb-2 fw-semibold"),
            html.Small(
                "Por cada par (moneda, divisor) el sistema crea un sintético "
                "por cada activo en esa moneda: TICKER_BASE / TICKER_DIVISOR.",
                className="text-muted d-block mb-3",
                style={"fontSize": "0.78rem"},
            ),

            dbc.Row([
                dbc.Col(
                    dcc.Dropdown(
                        id="ars-currency-select",
                        placeholder="Moneda fuente...",
                        style={"fontSize": "0.85rem"},
                    ),
                    md=3,
                ),
                dbc.Col(
                    dcc.Dropdown(
                        id="ars-divisor-select",
                        placeholder="Activo divisor...",
                        style={"fontSize": "0.85rem"},
                    ),
                    md=6,
                ),
                dbc.Col(
                    dbc.Button("+ Agregar", id="ars-btn-add",
                               color="primary", size="sm", className="w-100"),
                    md=2,
                ),
            ], className="mb-3 g-2 align-items-center"),

            dbc.Alert(id="ars-add-alert", is_open=False, dismissable=True,
                      className="mb-2 small py-1"),

            dcc.Loading(
                html.Div(id="ars-divisors-table"),
                type="circle", color="#6c757d",
            ),
        ]), className="mb-3"),

        # ── Sincronización ────────────────────────────────────────────────────
        dbc.Card(dbc.CardBody([
            html.H6("Sincronizar sintéticos", className="mb-2 fw-semibold"),

            html.Div(id="ars-stats", className="mb-3 small text-muted"),

            dbc.Button("Sincronizar ahora", id="ars-btn-sync",
                       color="success", size="sm"),
            dbc.Tooltip(
                "Crea los sintéticos faltantes y calcula sus precios. "
                "Los que ya existen no se modifican.",
                target="ars-btn-sync", placement="right",
                style={"maxWidth": "260px", "fontSize": "0.78rem",
                       "backgroundColor": "#1f2937", "color": "#dee2e6",
                       "border": "1px solid #374151"},
            ),

            dbc.Progress(id="ars-progress", value=0, striped=True, animated=True,
                         style={"display": "none", "height": "16px", "fontSize": "0.72rem"},
                         className="mt-2"),

            dbc.Alert(id="ars-sync-alert", is_open=False, dismissable=True,
                      className="mt-2 small"),
        ])),

    ], style={"padding": "0 8px"})


dash.register_page(__name__, path="/admin/ars-conversion",
                   title="Activos en Divisa", layout=layout)
