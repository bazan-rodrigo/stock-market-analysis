import dash
import dash_bootstrap_components as dbc
from dash import dcc, html

_CARD = {"backgroundColor": "#1f2937", "border": "1px solid #374151", "borderRadius": "8px"}

_OPS = [
    ("prices", "Actualizar Precios",
     "Descarga precios desde fuentes externas para todos los activos activos. "
     "Incluye automáticamente el recálculo de indicadores técnicos (RSI, medias, señales) "
     "y de ratios fundamentales (P/E, P/B, ROIC) para cada activo al finalizar.",
     "/prices", True),
    ("fund", "Actualizar Fundamentales",
     "Descarga datos trimestrales (balances, ingresos) para activos con fuente de fundamentales configurada. "
     "Incluye automáticamente el recálculo de ratios fundamentales (P/E, P/B, ROIC, márgenes) al finalizar.",
     "/admin/fundamental-update", True),
    ("indicators", "Recomputar Indicadores",
     "Recalcula medias móviles, RSI, régimen de tendencia, señales y estrategias sin descargar precios nuevos. "
     "Usar cuando se modifica la configuración de una señal o estrategia y se quiere aplicar sobre datos ya almacenados.",
     None, False),
    ("snap", "Recomputar Snapshots Fundamentales",
     "Recalcula P/E, P/B, márgenes, ROIC y otros ratios sin descargar datos nuevos de la fuente. "
     "Usar cuando se agrega o modifica una métrica y se quiere aplicar sobre los trimestres ya almacenados.",
     None, False),
    ("synth", "Recalcular Sintéticos",
     "Recalcula los precios de todos los activos sintéticos a partir de sus componentes.",
     None, False),
    ("fund_backfill", "Backfill de Fundamentales",
     "Rellena el historial de indicadores fundamentales. "
     "P/E, P/B y P/S se guardan diariamente (cambian con el precio). "
     "Márgenes, ROIC y crecimientos se guardan una vez por trimestre. "
     "Activá 'Recalcular todo' para pisar datos existentes.",
     None, False, True),
    ("backfill", "Backfill de Indicadores",
     "Rellena el historial de indicadores técnicos para fechas que tienen precio pero no tienen "
     "indicadores calculados. Detección delta automática: solo procesa lo que falta. "
     "Activá 'Recalcular todo' para pisar datos existentes — útil si cambiaste parámetros "
     "de configuración o corregiste precios históricos.",
     None, False, True),
]


def _op_card(op_id, title, description, log_href=None, has_new_only=False, has_force=False):
    buttons = [
        dbc.Button("Ejecutar", id=f"dc-btn-{op_id}",
                   size="sm", color="primary", outline=True, className="me-2"),
    ]
    if log_href:
        buttons.append(
            dbc.Button("Ver logs", href=log_href, external_link=False,
                       size="sm", color="secondary", outline=True),
        )

    extra_switch = []
    if has_new_only:
        extra_switch = [
            dbc.Switch(
                id=f"dc-new-only-{op_id}",
                label="Solo activos nuevos",
                value=False,
                style={"fontSize": "0.74rem", "color": "#9ca3af", "marginBottom": "8px"},
            )
        ]
    elif has_force:
        extra_switch = [
            dbc.Switch(
                id=f"dc-force-{op_id}",
                label="Recalcular todo (pisar datos existentes)",
                value=False,
                style={"fontSize": "0.74rem", "color": "#f59e0b", "marginBottom": "8px"},
            )
        ]

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
                *extra_switch,
                html.Div(buttons, className="d-flex"),
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

        dbc.Row([_op_card(*op, *((False,) * (6 - len(op)))) for op in _OPS]),

        dcc.Interval(id="dc-status-interval", interval=30_000, n_intervals=0),
    ], style={"padding": "0 8px"})


dash.register_page(__name__, path="/admin/data-center",
                   title="Centro de Datos", layout=layout)
