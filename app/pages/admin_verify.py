import dash
import dash_bootstrap_components as dbc
from dash import dcc, html

from app.components.help import help_link


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
    def _result_tab(label, tab_id, tree_id):
        return dbc.Tab(
            html.Div([
                html.Div([
                    dbc.Button("Expandir todo", id=f"verify-tree-expand-{tab_id}",
                               size="sm", color="link", className="p-0 me-3"),
                    dbc.Button("Colapsar todo", id=f"verify-tree-collapse-{tab_id}",
                               size="sm", color="link", className="p-0"),
                ], className="mb-2"),
                html.Div(id=tree_id, children=[]),
            ], className="mt-2"),
            label=label, tab_id=tab_id, id=f"verify-tab-{tab_id}",
        )

    return html.Div([
        html.H3(["Verificación de Datos ", help_link("verificacion-de-datos")], className="mb-3"),

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
                    "indicadores o ratios y los compara contra lo guardado en "
                    "ind_{código} — incluye chequeos de cordura (RSI fuera de "
                    "[0,100], categorías desconocidas, valores absurdos). Solo "
                    "lectura sobre precios/trimestrales — seguro de correr "
                    "contra producción. \"Todos los activos\" y \"Solo los ya "
                    "marcados\" además actualizan asset_verification_flag (⚠️ "
                    "en los selectores de Análisis de Activo, RRG, Evolución, "
                    "Pares y Retornos) — un activo se reescribe ahí (o se "
                    "limpia, si ya no tiene hallazgos) solo cuando se lo "
                    "vuelve a verificar; el job semanal (ver /admin/scheduler) "
                    "corre \"Todos los activos\" automáticamente.",
                    className="text-muted small mb-3",
                ),
                html.Div(id="verify-flags-last-run", className="text-muted small mb-3"),
                dbc.Row([
                    dbc.Col([
                        dbc.Label("Alcance", size="sm"),
                        dbc.RadioItems(
                            id="verify-scope",
                            options=[
                                {"label": "Muestra al azar", "value": "sample"},
                                {"label": "Tickers puntuales", "value": "tickers"},
                                {"label": "Todos los activos", "value": "all"},
                                {"label": "Solo los ya marcados", "value": "marked"},
                            ],
                            value="sample", inline=True,
                        ),
                    ], width=12, className="mb-2"),
                ]),
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
                        html.Small(
                            "Se ignora con alcance \"Todos los activos\"/\"Solo los ya "
                            "marcados\" — esos siempre chequean indicadores + "
                            "fundamentales completos.",
                            id="verify-domain-note", className="text-muted d-none",
                        ),
                    ], width=12, className="mb-2"),
                ]),
                dbc.Row([
                    dbc.Col([
                        dbc.Label("Códigos (vacío = todos)", size="sm"),
                        dcc.Dropdown(id="verify-codes", options=indicator_options,
                                    multi=True, placeholder="Todos los códigos"),
                    ], width=5, id="verify-codes-col"),
                    dbc.Col([
                        dbc.Label("Muestra (activos al azar)", size="sm"),
                        dbc.Input(id="verify-sample", type="number", value=30,
                                  min=1, max=2000, size="sm"),
                    ], width=3, id="verify-sample-col"),
                    dbc.Col([
                        dbc.Label("Tickers puntuales", size="sm"),
                        dbc.Input(id="verify-tickers", type="text", size="sm",
                                  placeholder="AAPL,GGAL.BA"),
                    ], width=4, id="verify-tickers-col"),
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
                    _result_tab("Discrepancias de cálculo", "calc", "verify-tree-calc"),
                    _result_tab("Datos de origen", "sanity", "verify-tree-sanity"),
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
