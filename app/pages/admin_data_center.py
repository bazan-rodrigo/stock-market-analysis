import dash
import dash_bootstrap_components as dbc
from dash import dcc, html

_CARD = {"backgroundColor": "#1f2937", "border": "1px solid #374151", "borderRadius": "8px"}
_OPS  = [
    ("prices",   "Actualizar Precios",
     "Descarga precios desde las fuentes externas (Yahoo Finance, etc.) para todos los activos activos."),
    ("fund",     "Actualizar Fundamentales",
     "Descarga datos trimestrales (balances, ingresos) para activos con fuente de fundamentales configurada."),
    ("snap",     "Recomputar Snapshots",
     "Recalcula todos los ratios (P/E, P/B, márgenes, ROIC...) a partir de datos ya almacenados. Sin fetch externo."),
    ("synth",    "Recalcular Sintéticos",
     "Recalcula los precios de todos los activos sintéticos a partir de los componentes."),
]


def _op_card(op_id, title, description):
    return dbc.Col(
        dbc.Card([
            dbc.CardHeader(html.Strong(title, style={"fontSize": "0.9rem"}), style={"backgroundColor": "#111827"}),
            dbc.CardBody([
                html.P(description, className="text-muted mb-3", style={"fontSize": "0.78rem"}),
                dbc.Progress(
                    id=f"dc-progress-{op_id}",
                    value=0, striped=True, animated=True,
                    style={"height": "6px", "display": "none"},
                    className="mb-2",
                ),
                html.Div(id=f"dc-msg-{op_id}",
                         className="text-muted mb-2",
                         style={"fontSize": "0.75rem", "minHeight": "18px"}),
                dbc.Button("Ejecutar", id=f"dc-btn-{op_id}",
                           size="sm", color="primary", outline=True),
                dcc.Interval(id=f"dc-interval-{op_id}", interval=800, disabled=True),
            ]),
        ], style=_CARD),
        md=6, className="mb-3",
    )


def layout(**kwargs):
    from flask_login import current_user
    if not current_user.is_authenticated or not current_user.is_admin:
        return html.Div()

    return html.Div([
        html.H4("Centro de Datos", className="mb-1"),
        html.P("Estado de los datos y operaciones de actualización.",
               className="text-muted mb-4", style={"fontSize": "0.8rem"}),

        # ── Estado actual ──────────────────────────────────────────────
        dbc.Row([
            dbc.Col(html.Div(id="dc-status-prices"), md=3, className="mb-3"),
            dbc.Col(html.Div(id="dc-status-fund"),   md=3, className="mb-3"),
            dbc.Col(html.Div(id="dc-status-snap"),   md=3, className="mb-3"),
            dbc.Col(html.Div(id="dc-status-synth"),  md=3, className="mb-3"),
        ]),

        html.Hr(style={"borderColor": "#374151", "marginBottom": "1.5rem"}),

        # ── Operaciones ────────────────────────────────────────────────
        dbc.Row([_op_card(op_id, title, desc) for op_id, title, desc in _OPS]),

        # Trigger de carga de estado
        dcc.Interval(id="dc-status-interval", interval=30_000, n_intervals=0),
    ], style={"padding": "0 8px"})


dash.register_page(__name__, path="/admin/data-center",
                   title="Centro de Datos", layout=layout)
