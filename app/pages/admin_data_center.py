import dash
import dash_bootstrap_components as dbc
from dash import dcc, html

_CARD = {"backgroundColor": "#1f2937", "border": "1px solid #374151", "borderRadius": "8px"}
_HEADER = {"backgroundColor": "#111827", "padding": "8px 14px"}
_BODY   = {"padding": "12px 14px"}

_TXT_SM  = {"fontSize": "0.76rem", "lineHeight": "1.4"}
_TXT_XS  = {"fontSize": "0.72rem", "color": "#6b7280"}
_TXT_MSG = {"fontSize": "0.74rem", "minHeight": "16px", "color": "#9ca3af", "marginBottom": "10px"}


# ── Sección de operación (cuerpo de una card standalone) ───────────────────────

def _op_section(op_id, description, *, has_new_only=False,
                has_redownload=False, redownload_label="Redescargar completo",
                redownload_body=(
                    "Esta acción borrará toda la historia de todos los activos "
                    "y la redescargará completa desde la fuente. El proceso puede demorar varios minutos. "
                    "¿Confirmás?"
                ),
                has_reconcile=False, reconcile_label="Recalcular caché",
                has_days=False, log_href=None):
    buttons = [
        dbc.Button("Ejecutar", id=f"dc-btn-{op_id}",
                   size="sm", color="primary", outline=True, className="me-2"),
    ]
    if has_reconcile:
        buttons.append(
            dbc.Button(reconcile_label, id=f"dc-btn-reconcile-{op_id}",
                       size="sm", color="secondary", outline=True, className="me-2"),
        )
    if has_redownload:
        buttons.append(
            dbc.Button(redownload_label, id=f"dc-btn-redownload-{op_id}",
                       size="sm", color="danger", outline=True, className="me-2"),
        )
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
    if has_days:
        extra.append(html.Div([
            dbc.Row([
                dbc.Col([
                    html.Span("Horizonte (días): ",
                              style={"fontSize": "0.74rem", "color": "#9ca3af"}),
                    dbc.Input(id=f"dc-days-{op_id}", type="number", value=None,
                              placeholder="todo", min=1, step=1, size="sm",
                              style={"width": "80px", "display": "inline-block",
                                     "fontSize": "0.76rem", "marginLeft": "6px"}),
                ], width="auto", className="d-flex align-items-center"),
                dbc.Col([
                    dcc.Dropdown(
                        id=f"dc-scope-{op_id}",
                        placeholder="Todo (señales y estrategias)",
                        clearable=True,
                        style={"fontSize": "0.76rem", "minWidth": "260px"},
                    ),
                ], className="d-flex align-items-center"),
                dbc.Col([
                    dbc.Switch(
                        id=f"dc-with-signals-{op_id}",
                        label="Incluir señales", value=True,
                        style={"fontSize": "0.74rem", "color": "#9ca3af"}),
                ], width="auto", className="d-flex align-items-center"),
            ], className="g-2 mb-1 align-items-center"),
            html.Small("El horizonte y el alcance aplican a los dos botones "
                       "(Ejecutar y Recalcular completo). Vacío = toda la "
                       "historia (en Recalcular completo puede tardar mucho). "
                       "«Incluir señales» solo aplica con alcance de "
                       "ESTRATEGIA: apagado, las señales no se re-evalúan "
                       "(se leen las guardadas) y solo se reconstruye el "
                       "resultado de la estrategia — mucho más rápido; "
                       "dejalo prendido si cambiaste señales o indicadores.",
                       className="text-muted d-block mb-2",
                       style={"fontSize": "0.7rem"}),
        ]))

    redownload_modal = []
    if has_redownload:
        redownload_modal = [dbc.Modal([
            dbc.ModalHeader(dbc.ModalTitle("Confirmar operación")),
            # El id permite reescribir el texto según alcance/switch al
            # abrirlo (hoy solo la tarjeta de señales lo usa)
            dbc.ModalBody(redownload_body, id=f"dc-redownload-body-{op_id}"),
            dbc.ModalFooter([
                dbc.Button(f"Sí, {redownload_label.lower()}", id=f"dc-btn-redownload-{op_id}-confirm", color="danger"),
                dbc.Button("Cancelar", id=f"dc-btn-redownload-{op_id}-cancel", color="secondary", className="ms-2"),
            ]),
        ], id=f"dc-redownload-modal-{op_id}", is_open=False)]

    return html.Div([
        html.P(description, className="text-muted mb-2", style=_TXT_SM),
        html.Div(id=f"dc-status-{op_id}", className="mb-2",
                 style={**_TXT_XS, "borderTop": "1px solid #374151", "paddingTop": "8px"}),
        dbc.Progress(id=f"dc-progress-{op_id}", value=0, striped=True, animated=True,
                     style={"height": "4px", "display": "none"}, className="mb-1"),
        html.Div(id=f"dc-msg-{op_id}", style=_TXT_MSG),
        *extra,
        html.Div(buttons, className="d-flex"),
        dcc.Interval(id=f"dc-interval-{op_id}", interval=2000, disabled=True),
        *redownload_modal,
    ])


# ── Card standalone ───────────────────────────────────────────────────────────

def _solo_card(op_id, title, description, *, has_new_only=False,
               has_redownload=False, redownload_label="Redescargar completo",
               redownload_body=None, has_reconcile=False,
               reconcile_label="Recalcular caché", has_days=False,
               log_href=None):
    kwargs = dict(redownload_label=redownload_label)
    if redownload_body is not None:
        kwargs["redownload_body"] = redownload_body
    return dbc.Col(
        dbc.Card([
            dbc.CardHeader(html.Strong(title, style={"fontSize": "0.88rem"}), style=_HEADER),
            dbc.CardBody(
                _op_section(op_id, description,
                            has_new_only=has_new_only,
                            has_redownload=has_redownload,
                            has_reconcile=has_reconcile, reconcile_label=reconcile_label,
                            has_days=has_days, log_href=log_href, **kwargs),
                style=_BODY,
            ),
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
                has_new_only=True, has_redownload=True, log_href="/prices",
            ),
            _solo_card(
                "fund", "Actualizar Fundamentales",
                "Descarga datos trimestrales (balances, ingresos) para activos con fuente "
                "de fundamentales configurada. Incluye el recálculo de ratios al finalizar.",
                has_new_only=True, has_redownload=True, log_href="/admin/fundamental-update",
            ),
        ]),

        # Fila 2 — Recálculos técnicos y fundamentales
        dbc.Row([
            _solo_card(
                "indicators", "Indicadores Técnicos",
                "'Ejecutar' recalcula los indicadores para la última fecha de cada activo "
                "y de paso completa fechas históricas que tengan precio pero no indicador (backfill delta). "
                "'Recalcular caché' reconstruye desde cero todo el caché interno que acelera ese backfill "
                "(min/max/cantidad de filas por activo, más el benchmark/checksum usado en el último cálculo), "
                "sin recalcular ningún indicador — útil si el caché quedó mal por una edición manual desde "
                "la consola SQL. "
                "'Recalcular completo' borra y rehace toda la historia desde el primer precio.",
                has_redownload=True, redownload_label="Recalcular completo",
                redownload_body=(
                    "Esta acción borrará todo el historial de indicadores técnicos "
                    "y lo recalculará completo desde el primer precio disponible. "
                    "El proceso puede demorar varios minutos. ¿Confirmás?"
                ),
                has_reconcile=True,
            ),
            _solo_card(
                "snap", "Indicadores Fundamentales",
                "'Ejecutar' recalcula P/E, P/B, márgenes, ROIC y otros ratios para hoy "
                "y de paso completa fechas históricas sin ratio calculado (backfill delta). "
                "'Recalcular completo' borra y rehace todo el historial de ratios desde cero.",
                has_redownload=True, redownload_label="Recalcular completo",
                redownload_body=(
                    "Esta acción borrará todo el historial de ratios fundamentales "
                    "y lo recalculará completo desde los trimestres almacenados. "
                    "El proceso puede demorar varios minutos. ¿Confirmás?"
                ),
            ),
        ]),

        # Fila 3 — Sintéticos + Señales/Estrategias
        dbc.Row([
            _solo_card(
                "synth", "Recalcular Sintéticos",
                "Recalcula los precios de todos los activos sintéticos a partir de sus componentes. "
                "'Ejecutar' calcula solo el delta (rápido, mantiene el historial). "
                "'Recalcular completo' borra y rehace toda la historia desde cero.",
                has_redownload=True, redownload_label="Recalcular completo",
                redownload_body=(
                    "Esta acción borrará toda la historia de precios de los activos sintéticos "
                    "y la recalculará completa a partir de sus componentes. "
                    "El proceso puede demorar varios minutos. ¿Confirmás?"
                ),
            ),
            _solo_card(
                "signals", "Señales y Estrategias",
                "Corre el pipeline (scores de grupo → señales → estrategias) por fecha, "
                "dentro del horizonte elegido. 'Ejecutar' calcula solo las fechas con precios "
                "que no tienen señales (llena huecos si el scheduler estuvo apagado) y "
                "recalcula siempre la última. 'Recalcular completo' reescribe todas las "
                "fechas del horizonte — usar tras cambiar la definición de una señal o "
                "estrategia. Requiere indicadores ya calculados; las señales sobre "
                "indicadores sin historia solo puntúan en la fecha vigente.",
                has_redownload=True, redownload_label="Recalcular completo",
                # Texto de arranque nomás: al abrir el modal, un callback lo
                # reescribe según alcance + «Incluir señales» + horizonte
                # (ver update_signals_confirm_body)
                redownload_body=(
                    "Esta acción borra y reconstruye lo abarcado por el alcance "
                    "y el horizonte elegidos. ¿Confirmás?"
                ),
                has_days=True,
            ),
        ]),

        # max_intervals=0: el status se consulta una vez al abrir la pantalla
        # (y al iniciar/terminar operaciones, vía dc-interval-*), no por reloj.
        dcc.Interval(id="dc-status-interval", interval=30_000, n_intervals=0,
                     max_intervals=0),
    ], style={"padding": "0 8px"})


dash.register_page(__name__, path="/admin/data-center",
                   title="Centro de Datos", layout=layout)
