import dash
import dash_bootstrap_components as dbc
from dash import dcc, html


def layout(**kwargs):
    from flask_login import current_user
    if not current_user.is_authenticated or not current_user.is_admin:
        return html.Div("Acceso denegado", className="text-danger mt-4")

    from app.services.technical_service import _DELTA_TAIL_MODE
    indicator_options = [{"label": c, "value": c} for c in sorted(_DELTA_TAIL_MODE)]

    _PRE_STYLE = {
        "maxHeight": "420px", "overflowY": "auto", "overflowX": "auto",
        "backgroundColor": "#111827", "color": "#e5e7eb",
        "padding": "0.75rem", "borderRadius": "4px", "fontSize": "0.78rem",
        "whiteSpace": "pre-wrap",
    }
    _SUMMARY_STYLE = {
        **_PRE_STYLE, "maxHeight": "180px",
        "backgroundColor": "#1f2937", "fontWeight": "500",
    }

    def _result_tab(label, tab_id, summary_id, detail_id):
        return dbc.Tab(
            html.Div([
                html.Pre(id=summary_id, style=_SUMMARY_STYLE, children=""),
                html.Pre(id=detail_id,  style=_PRE_STYLE,     children=""),
            ], className="mt-2"),
            label=label, tab_id=tab_id,
        )

    return html.Div([
        html.H3("Verificación de Datos", className="mb-3"),

        # ── Suite de tests (pytest) ─────────────────────────────────────────
        dbc.Card([
            dbc.CardHeader("Suite de tests (pytest)"),
            dbc.CardBody([
                html.P(
                    "Corre la suite de lógica pura (tests/) — fórmulas, "
                    "decisión rápido/lento del delta, paridad de vectorización. "
                    "No toca la base de datos.",
                    className="text-muted small mb-2",
                ),
                dbc.Button("Correr tests", id="verify-pytest-btn",
                           color="primary", size="sm", className="mb-2"),
                dcc.Interval(id="verify-pytest-interval", interval=1000,
                             disabled=True, n_intervals=0),
                html.Div(
                    dbc.Spinner(size="sm", color="primary", type="border"),
                    id="verify-pytest-spinner",
                    style={"display": "none"},
                ),
                dbc.Alert(id="verify-pytest-alert", is_open=False, dismissable=True),
                html.Pre(id="verify-pytest-output", style=_PRE_STYLE, children=""),
            ]),
        ], className="mb-4"),

        # ── Verificación de datos reales ────────────────────────────────────
        dbc.Card([
            dbc.CardHeader("Verificación de datos reales (delta vs. recálculo)"),
            dbc.CardBody([
                html.P(
                    "Recalcula desde cero (en memoria, sin escribir nada) los "
                    "indicadores o ratios de una muestra de activos y los "
                    "compara contra lo guardado en ind_{código} — incluye "
                    "chequeos de cordura (RSI fuera de [0,100], categorías "
                    "desconocidas, valores absurdos). Solo lectura — seguro "
                    "de correr contra producción.",
                    className="text-muted small mb-3",
                ),
                dbc.Row([
                    dbc.Col([
                        dbc.Label("Dominio", size="sm"),
                        dbc.RadioItems(
                            id="verify-domain",
                            options=[
                                {"label": "Indicadores técnicos", "value": "indicators"},
                                {"label": "Ratios fundamentales", "value": "fundamentals"},
                            ],
                            value="indicators", inline=True,
                        ),
                    ], width=12, className="mb-2"),
                ]),
                dbc.Row([
                    dbc.Col([
                        dbc.Label("Códigos (vacío = todos)", size="sm"),
                        dcc.Dropdown(id="verify-codes", options=indicator_options,
                                    multi=True, placeholder="Todos los códigos"),
                    ], width=5),
                    dbc.Col([
                        dbc.Label("Muestra (activos al azar)", size="sm"),
                        dbc.Input(id="verify-sample", type="number", value=30,
                                  min=1, max=2000, size="sm"),
                    ], width=3),
                    dbc.Col([
                        dbc.Label("Tickers puntuales (opcional, ignora la muestra)", size="sm"),
                        dbc.Input(id="verify-tickers", type="text", size="sm",
                                  placeholder="AAPL,GGAL.BA"),
                    ], width=4),
                ], className="mb-3 gy-2"),
                dbc.Button("Verificar", id="verify-run-btn",
                           color="primary", size="sm", className="mb-2"),
                dcc.Interval(id="verify-run-interval", interval=1000,
                             disabled=True, n_intervals=0),
                dbc.Progress(id="verify-run-progress", value=0, striped=True,
                           animated=True, label="", className="mb-2",
                           style={"display": "none"}),
                dbc.Alert(id="verify-run-alert", is_open=False, dismissable=True),
                dbc.Tabs([
                    _result_tab("Discrepancias de cálculo", "calc",
                               "verify-run-summary-calc", "verify-run-detail-calc"),
                    _result_tab("Datos de origen", "sanity",
                               "verify-run-summary-sanity", "verify-run-detail-sanity"),
                ], active_tab="calc"),
            ]),
        ]),
    ])


dash.register_page(
    __name__,
    path="/admin/verify",
    title="Verificación de Datos",
    layout=layout,
)
