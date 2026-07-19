import dash
import dash_bootstrap_components as dbc
from dash import dcc, html

_HELP = (
    "Mide si el ranking de la estrategia predice retornos: cada fecha parte "
    "los activos elegibles en cuantiles por score y mide el retorno posterior "
    "de cada cuantil a varios horizontes (en ruedas). La señal se ejecuta al "
    "cierre SIGUIENTE (sin look-ahead) y solo se scorea un activo en fechas "
    "donde cotizó (los scores arrastrados quedan afuera). Cada corrida queda "
    "guardada con su configuración para poder comparar."
)

_LBL = {"fontSize": "0.8rem"}
_IN = {"fontSize": "0.82rem"}


def layout(**kwargs):
    from flask_login import current_user
    if not current_user.is_authenticated:
        return html.Div()

    return html.Div([
        dcc.Interval(id="bt-interval", interval=1000, disabled=True),
        dcc.Interval(id="bt-rules-interval", interval=1000, disabled=True),
        dcc.Interval(id="bt-port-interval", interval=1000, disabled=True),
        dcc.Store(id="bt-cmp-reload", data=0),

        dbc.Row([
            dbc.Col(html.H4("Backtest de Estrategia", className="mb-0"),
                    width="auto"),
        ], className="mb-3 align-items-center"),

        dbc.Tabs([
          dbc.Tab(label="Señal — calidad del ranking", tab_id="bt-tab-senal",
                  children=html.Div([
        dbc.Alert(_HELP, color="info", className="mb-3 mt-3 small py-2"),

        # ── Configuración del run ─────────────────────────────────────────
        dbc.Card(dbc.CardBody([
            dbc.Row([
                dbc.Col([
                    dbc.Label("Estrategia", style=_LBL),
                    dcc.Dropdown(id="bt-strategy-sel",
                                 placeholder="Seleccionar estrategia...",
                                 style=_IN),
                ], md=3),
                dbc.Col([
                    dbc.Label("Horizontes (ruedas)", style=_LBL),
                    dcc.Dropdown(
                        id="bt-horizons", multi=True,
                        options=[{"label": f"{h}", "value": h}
                                 for h in (1, 5, 10, 20, 60, 120, 250)],
                        value=[1, 5, 20, 60], style=_IN),
                ], md=3),
                dbc.Col([
                    dbc.Label("Cuantiles", style=_LBL),
                    dbc.Input(id="bt-quantiles", type="number", value=10,
                              min=2, max=20, step=1, style=_IN),
                ], md=1),
                dbc.Col([
                    dbc.Label("Mín. activos", style=_LBL),
                    dbc.Input(id="bt-min-assets", type="number", value=20,
                              min=2, step=1, style=_IN),
                ], md=1),
                dbc.Col([
                    dbc.Label("Desde (opcional)", style=_LBL),
                    dcc.DatePickerSingle(id="bt-date-from", date=None,
                                         display_format="YYYY-MM-DD",
                                         clearable=True),
                ], md=2, className="d-flex flex-column"),
                dbc.Col([
                    dbc.Label(" ", style=_LBL),
                    dbc.Button("Ejecutar backtest", id="bt-btn-run",
                               color="primary", size="sm",
                               style={"display": "block"}),
                ], md=2, className="d-flex flex-column"),
            ], className="g-2"),

            dbc.Progress(id="bt-progress", value=0, striped=True,
                         animated=True, className="mt-2",
                         style={"display": "none", "height": "16px",
                                "fontSize": "0.72rem"}),
            dbc.Alert(id="bt-alert", is_open=False, dismissable=True,
                      className="mt-2 small py-1"),
        ]), className="mb-3",
            style={"backgroundColor": "#1f2937", "border": "1px solid #374151"}),

        # ── Runs guardados ────────────────────────────────────────────────
        dbc.Row([
            dbc.Col([
                dbc.Label("Corridas guardadas", style=_LBL),
                dcc.Dropdown(id="bt-run-sel", placeholder="Elegir corrida...",
                             style=_IN),
            ], md=6),
        ], className="mb-3 g-2"),

        # ── Resultados ────────────────────────────────────────────────────
        dcc.Loading(html.Div(id="bt-results"), type="circle", color="#dee2e6"),
                  ])),

          dbc.Tab(label="Reglas — rendimiento sobre el universo",
                  tab_id="bt-tab-reglas", children=html.Div([
        dbc.Alert(
            "Corre el simulador de trades con estas reglas sobre TODOS los "
            "activos de la estrategia y agrega: retorno por activo, salidas por "
            "motivo y ranking. Responde \"¿qué tan buenas son las reglas en "
            "promedio?\" (a diferencia del análisis por cuantiles de arriba).",
            color="info", className="mb-3 small py-2"),
        dbc.Card(dbc.CardBody([
            dbc.Row([
                dbc.Col([dbc.Label("Estrategia", style=_LBL),
                         dcc.Dropdown(id="bt-rules-strategy",
                                      placeholder="Seleccionar…", style=_IN)], md=3),
                dbc.Col([dbc.Label("Entrada Score ≥", style=_LBL),
                         dbc.Input(id="bt-rules-score", type="number", value=20,
                                   style=_IN)], md=2),
                dbc.Col([dbc.Label("Entrada Percentil ≥", style=_LBL),
                         dbc.Input(id="bt-rules-pct", type="number", style=_IN)], md=2),
                dbc.Col([dbc.Label("Salida Score <", style=_LBL),
                         dbc.Input(id="bt-rules-exit-score", type="number",
                                   style=_IN)], md=2),
            ], className="g-2 mb-2"),
            dbc.Row([
                dbc.Col([dbc.Label("SL %", style=_LBL),
                         dbc.Input(id="bt-rules-sl", type="number", value=10,
                                   style=_IN)], md=2),
                dbc.Col([dbc.Label("TP %", style=_LBL),
                         dbc.Input(id="bt-rules-tp", type="number", value=20,
                                   style=_IN)], md=2),
                dbc.Col([dbc.Label("Trailing %", style=_LBL),
                         dbc.Input(id="bt-rules-ts", type="number", value=15,
                                   style=_IN)], md=2),
                dbc.Col([dbc.Label("Máx ruedas", style=_LBL),
                         dbc.Input(id="bt-rules-maxbars", type="number", value=60,
                                   style=_IN)], md=2),
                dbc.Col([dbc.Label("Enfriamiento", style=_LBL),
                         dbc.Input(id="bt-rules-cooldown", type="number", value=5,
                                   style=_IN)], md=1),
                dbc.Col([dbc.Label("Rearm", style=_LBL),
                         dbc.Switch(id="bt-rules-rearm", value=True)], md=1,
                        className="d-flex flex-column"),
                dbc.Col([dbc.Label(" ", style=_LBL),
                         dbc.Button("Correr reglas", id="bt-rules-run",
                                    color="primary", size="sm",
                                    style={"display": "block"})], md=2,
                        className="d-flex flex-column"),
            ], className="g-2"),
            dbc.Progress(id="bt-rules-progress", value=0, striped=True,
                         animated=True, className="mt-2",
                         style={"display": "none", "height": "16px",
                                "fontSize": "0.72rem"}),
            dbc.Alert(id="bt-rules-alert", is_open=False, dismissable=True,
                      className="mt-2 small py-1"),
        ]), className="mb-3",
            style={"backgroundColor": "#1f2937", "border": "1px solid #374151"}),

        dcc.Loading(html.Div(id="bt-rules-results"), type="circle",
                    color="#dee2e6"),
                  ])),

          dbc.Tab(label="Cartera — simulación top-N", tab_id="bt-tab-cartera",
                  children=html.Div([
        dbc.Alert(
            "Simula una cartera que mantiene el top-N por score. Dos sub-modos "
            "superpuestos: RANKING PURO (rota sólo por score) y GATED (además "
            "respeta las reglas de entrada/salida) — la distancia entre las "
            "curvas es cuánto aportan los stops. Se compara contra el EW del "
            "universo. Nota: con rebalanceo > 1 rueda, las salidas se aplican "
            "recién en el próximo rebalanceo; usá rebalanceo = 1 para stops "
            "inmediatos.", color="info", className="mb-3 small py-2"),
        dbc.Card(dbc.CardBody([
            dbc.Row([
                dbc.Col([dbc.Label("Estrategia", style=_LBL),
                         dcc.Dropdown(id="bt-port-strategy",
                                      placeholder="Seleccionar…", style=_IN)], md=3),
                dbc.Col([dbc.Label("Top-N", style=_LBL),
                         dbc.Input(id="bt-port-topn", type="number", value=20,
                                   min=1, style=_IN)], md=2),
                dbc.Col([dbc.Label("Rebalanceo (ruedas)", style=_LBL),
                         dbc.Input(id="bt-port-rebal", type="number", value=5,
                                   min=1, style=_IN)], md=2),
                dbc.Col([dbc.Label("Costos (bps/lado)", style=_LBL),
                         dbc.Input(id="bt-port-cost", type="number", value=10,
                                   min=0, style=_IN)], md=2),
            ], className="g-2 mb-2"),
            dbc.Row([
                dbc.Col([dbc.Label("Entrada Score ≥", style=_LBL),
                         dbc.Input(id="bt-port-score", type="number", value=20,
                                   style=_IN)], md=2),
                dbc.Col([dbc.Label("Percentil ≥", style=_LBL),
                         dbc.Input(id="bt-port-pct", type="number", style=_IN)], md=1),
                dbc.Col([dbc.Label("Salida Score <", style=_LBL),
                         dbc.Input(id="bt-port-exit-score", type="number",
                                   style=_IN)], md=2),
                dbc.Col([dbc.Label("SL %", style=_LBL),
                         dbc.Input(id="bt-port-sl", type="number", value=10,
                                   style=_IN)], md=1),
                dbc.Col([dbc.Label("TP %", style=_LBL),
                         dbc.Input(id="bt-port-tp", type="number", value=20,
                                   style=_IN)], md=1),
                dbc.Col([dbc.Label("Trail %", style=_LBL),
                         dbc.Input(id="bt-port-ts", type="number", value=15,
                                   style=_IN)], md=1),
                dbc.Col([dbc.Label("Máx r.", style=_LBL),
                         dbc.Input(id="bt-port-maxbars", type="number", value=60,
                                   style=_IN)], md=1),
                dbc.Col([dbc.Label("Enfr.", style=_LBL),
                         dbc.Input(id="bt-port-cooldown", type="number", value=5,
                                   style=_IN)], md=1),
                dbc.Col([dbc.Label("Rearm", style=_LBL),
                         dbc.Switch(id="bt-port-rearm", value=True)], md=1,
                        className="d-flex flex-column"),
                dbc.Col([dbc.Label(" ", style=_LBL),
                         dbc.Button("Correr", id="bt-port-run", color="primary",
                                    size="sm", style={"display": "block"})], md=1,
                        className="d-flex flex-column"),
            ], className="g-2"),
            dbc.Progress(id="bt-port-progress", value=0, striped=True,
                         animated=True, className="mt-2",
                         style={"display": "none", "height": "16px",
                                "fontSize": "0.72rem"}),
            dbc.Alert(id="bt-port-alert", is_open=False, dismissable=True,
                      className="mt-2 small py-1"),
            dbc.Button("💾 Guardar corrida", id="bt-port-save",
                       color="secondary", outline=True, size="sm",
                       className="mt-1 me-1",
                       title="Guarda esta corrida para compararla en el tab "
                             "Comparar"),
            dbc.Button("↗ Promover a seguimiento", id="bt-port-promote",
                       color="secondary", outline=True, size="sm",
                       className="mt-1",
                       title="Crea una cartera teórica en /carteras que sigue el "
                             "top-N de esta estrategia"),
            dbc.Alert(id="bt-port-promote-alert", is_open=False, dismissable=True,
                      className="mt-2 small py-1"),
        ]), className="mb-3",
            style={"backgroundColor": "#1f2937", "border": "1px solid #374151"}),

        dcc.Loading(html.Div(id="bt-port-results"), type="circle",
                    color="#dee2e6"),
                  ])),

          dbc.Tab(label="Comparar", tab_id="bt-tab-comparar",
                  children=html.Div([
        dbc.Alert("Compará corridas de Cartera guardadas: superpone sus curvas "
                  "de equity (sub-modo gated, indexadas a 100) y muestra los KPIs "
                  "lado a lado. Guardá corridas con «Guardar corrida» en el tab "
                  "Cartera.", color="info", className="mb-3 mt-3 small py-2"),
        dbc.Row([dbc.Col([
            dbc.Label("Corridas guardadas", style=_LBL),
            dcc.Dropdown(id="bt-cmp-runs", multi=True,
                         placeholder="Elegí corridas para comparar…",
                         style=_IN)], md=8)], className="mb-2"),
        dcc.Loading(html.Div(id="bt-cmp-results"), type="circle",
                    color="#dee2e6"),
                  ])),
        ], className="mb-3"),

    ], style={"padding": "0 8px"})


dash.register_page(__name__, path="/backtest",
                   title="Backtest de Estrategia", layout=layout)
