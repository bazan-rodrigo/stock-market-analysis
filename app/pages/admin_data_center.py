import dash
import dash_bootstrap_components as dbc
from dash import dcc, html

_CARD = {"backgroundColor": "#1f2937", "border": "1px solid #374151", "borderRadius": "8px"}
_HEADER = {"backgroundColor": "#111827", "padding": "8px 14px"}
_BODY   = {"padding": "12px 14px"}

_TXT_SM  = {"fontSize": "0.76rem", "lineHeight": "1.4"}
_TXT_XS  = {"fontSize": "0.72rem", "color": "#6b7280"}
_TXT_MSG = {"fontSize": "0.74rem", "minHeight": "16px", "color": "#9ca3af", "marginBottom": "10px"}


# ── Sección de operación (sin card propio, va dentro de un card combinado) ────

def _op_section(op_id, title, description, *, has_new_only=False, has_force=False,
                log_href=None, badge=None):
    buttons = [
        dbc.Button("Ejecutar", id=f"dc-btn-{op_id}",
                   size="sm", color="primary", outline=True, className="me-2"),
    ]
    if log_href:
        buttons.append(
            dbc.Button("Ver logs", href=log_href, external_link=False,
                       size="sm", color="secondary", outline=True),
        )

    extra = []
    if has_new_only:
        extra = [dbc.Switch(id=f"dc-new-only-{op_id}", label="Solo activos nuevos",
                            value=False,
                            style={"fontSize": "0.74rem", "color": "#9ca3af", "marginBottom": "8px"})]
    elif has_force:
        extra = [dbc.Switch(id=f"dc-force-{op_id}",
                            label="Recalcular todo (borra y rehace desde el primer precio)",
                            value=False,
                            style={"fontSize": "0.74rem", "color": "#f59e0b", "marginBottom": "8px"})]

    header_children = [html.Strong(title, style={"fontSize": "0.82rem", "color": "#d1d5db"})]
    if badge:
        header_children.append(
            dbc.Badge(badge, color="secondary", className="ms-2",
                      style={"fontSize": "0.65rem", "verticalAlign": "middle"})
        )

    return html.Div([
        html.Div(header_children, className="mb-1"),
        html.P(description, className="text-muted mb-2", style=_TXT_SM),
        html.Div(id=f"dc-status-{op_id}", className="mb-2",
                 style={**_TXT_XS, "borderTop": "1px solid #374151", "paddingTop": "8px"}),
        dbc.Progress(id=f"dc-progress-{op_id}", value=0, striped=True, animated=True,
                     style={"height": "4px", "display": "none"}, className="mb-1"),
        html.Div(id=f"dc-msg-{op_id}", style=_TXT_MSG),
        *extra,
        html.Div(buttons, className="d-flex"),
        dcc.Interval(id=f"dc-interval-{op_id}", interval=600, disabled=True),
    ])


# ── Card standalone ───────────────────────────────────────────────────────────

def _solo_card(op_id, title, description, *, has_new_only=False, has_force=False, log_href=None):
    return dbc.Col(
        dbc.Card([
            dbc.CardHeader(html.Strong(title, style={"fontSize": "0.88rem"}), style=_HEADER),
            dbc.CardBody(
                _op_section(op_id, "", description,
                            has_new_only=has_new_only, has_force=has_force, log_href=log_href),
                style=_BODY,
            ),
        ], style=_CARD),
        md=6, className="mb-3",
    )


# ── Card combinado: agrupa dos operaciones relacionadas ───────────────────────

def _combined_card(card_title, sections: list[dict]):
    children = []
    for i, sec in enumerate(sections):
        if i > 0:
            children.append(html.Hr(style={"borderColor": "#2d3748", "margin": "14px 0"}))
        children.append(_op_section(**sec))

    return dbc.Col(
        dbc.Card([
            dbc.CardHeader(html.Strong(card_title, style={"fontSize": "0.88rem"}), style=_HEADER),
            dbc.CardBody(children, style=_BODY),
        ], style=_CARD),
        md=6, className="mb-3",
    )


# ── Layout ────────────────────────────────────────────────────────────────────

def layout(**kwargs):
    from flask_login import current_user
    if not current_user.is_authenticated or not current_user.is_admin:
        return html.Div()

    return html.Div([
        html.H4("Centro de Datos", className="mb-1"),
        html.P("Estado de los datos y operaciones de actualización.",
               className="text-muted mb-4", style={"fontSize": "0.8rem"}),

        # Fila 1 — Actualizaciones desde fuentes externas
        dbc.Row([
            _solo_card(
                "prices", "Actualizar Precios",
                "Descarga precios desde fuentes externas para todos los activos activos. "
                "Incluye automáticamente el recálculo de indicadores técnicos y de ratios "
                "fundamentales al finalizar.",
                has_new_only=True, log_href="/prices",
            ),
            _solo_card(
                "fund", "Actualizar Fundamentales",
                "Descarga datos trimestrales (balances, ingresos) para activos con fuente "
                "de fundamentales configurada. Incluye el recálculo de ratios al finalizar.",
                has_new_only=True, log_href="/admin/fundamental-update",
            ),
        ]),

        # Fila 2 — Recálculos técnicos y fundamentales
        dbc.Row([
            _combined_card("Indicadores Técnicos", [
                {
                    "op_id": "indicators",
                    "title": "Recomputar",
                    "description": (
                        "Recalcula los indicadores para la última fecha disponible de cada activo. "
                        "Útil al cambiar parámetros de configuración y querer ver el efecto en los valores actuales."
                    ),
                },
                {
                    "op_id": "backfill",
                    "title": "Backfill",
                    "badge": "delta — solo fechas sin indicador",
                    "description": (
                        "Rellena fechas históricas que tienen precio pero no tienen indicador calculado. "
                        "Útil al agregar activos nuevos, cargar precios históricos, o incorporar un indicador nuevo. "
                        "Activar 'Recalcular todo' para borrar la historia completa y rehacer desde el primer precio."
                    ),
                    "has_force": True,
                },
            ]),

            _combined_card("Fundamentales", [
                {
                    "op_id": "snap",
                    "title": "Recomputar Snapshots",
                    "description": (
                        "Recalcula P/E, P/B, márgenes, ROIC y otros ratios desde los trimestres ya almacenados, "
                        "para la fecha de hoy. Útil al agregar o modificar una métrica de ratio."
                    ),
                },
                {
                    "op_id": "fund_backfill",
                    "title": "Backfill",
                    "badge": "delta — solo fechas sin indicador",
                    "description": (
                        "Rellena el historial de ratios fundamentales. "
                        "P/E, P/B y P/S se calculan por día hábil (varían con el precio). "
                        "Márgenes, ROIC y crecimientos se calculan una vez por trimestre. "
                        "Activar 'Recalcular todo' para borrar y rehacer toda la historia."
                    ),
                    "has_force": True,
                },
            ]),
        ]),

        # Fila 3 — Sintéticos
        dbc.Row([
            _solo_card(
                "synth", "Recalcular Sintéticos",
                "Recalcula los precios de todos los activos sintéticos a partir de sus componentes.",
            ),
        ]),

        dcc.Interval(id="dc-status-interval", interval=30_000, n_intervals=0),
    ], style={"padding": "0 8px"})


dash.register_page(__name__, path="/admin/data-center",
                   title="Centro de Datos", layout=layout)
