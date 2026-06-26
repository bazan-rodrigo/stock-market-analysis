import dash
import dash_bootstrap_components as dbc
from dash import dcc, html

_CARD = {"backgroundColor": "#1f2937", "border": "1px solid #374151", "borderRadius": "8px"}

_OPS = [
    ("prices", "Actualizar Precios",
     "Descarga precios desde fuentes externas para todos los activos activos. "
     "Incluye el recálculo de snapshots fundamentales al finalizar."),
    ("fund", "Actualizar Fundamentales",
     "Descarga datos trimestrales (balances, ingresos) para activos con fuente de fundamentales configurada."),
    ("snap", "Recomputar Snapshots Fundamentales",
     "Recalcula P/E, P/B, márgenes, ROIC y otros ratios a partir de datos ya almacenados. Sin fetch externo."),
    ("indicators", "Recomputar Indicadores",
     "Recalcula medias móviles, RSI, régimen de tendencia, señales y estrategias para todos los activos. "
     "Útil tras cambios de configuración."),
    ("synth", "Recalcular Sintéticos",
     "Recalcula los precios de todos los activos sintéticos a partir de sus componentes."),
]


def _op_card(op_id, title, description):
    return dbc.Col(
        dbc.Card([
            dbc.CardHeader(
                html.Strong(title, style={"fontSize": "0.88rem"}),
                style={"backgroundColor": "#111827", "padding": "8px 14px"},
            ),
            dbc.CardBody([
                html.P(description, className="text-muted mb-3",
                       style={"fontSize": "0.76rem", "lineHeight": "1.4"}),
                html.Div(id=f"dc-status-{op_id}",
                         className="mb-3",
                         style={"fontSize": "0.74rem", "color": "#6b7280",
                                "borderTop": "1px solid #374151", "paddingTop": "10px"}),
                dbc.Progress(
                    id=f"dc-progress-{op_id}",
                    value=0, striped=True, animated=True,
                    style={"height": "5px", "display": "none"},
                    className="mb-2",
                ),
                html.Div(id=f"dc-msg-{op_id}",
                         style={"fontSize": "0.74rem", "minHeight": "16px",
                                "color": "#9ca3af", "marginBottom": "10px"}),
                dbc.Button("Ejecutar", id=f"dc-btn-{op_id}",
                           size="sm", color="primary", outline=True),
                dcc.Interval(id=f"dc-interval-{op_id}", interval=600, disabled=True),
            ], style={"padding": "12px 14px"}),
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

        dbc.Row([_op_card(op_id, title, desc) for op_id, title, desc in _OPS]),

        dcc.Interval(id="dc-status-interval", interval=30_000, n_intervals=0),
    ], style={"padding": "0 8px"})


dash.register_page(__name__, path="/admin/data-center",
                   title="Centro de Datos", layout=layout)
