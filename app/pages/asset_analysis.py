import dash
import dash_bootstrap_components as dbc
from dash import dcc, html

_SMA_COLORS  = ["#ff9800", "#e91e63", "#4caf50"]
_EMA_COLORS  = ["#00bcd4", "#9c27b0", "#ffeb3b"]
_SMA_DEF     = [20, 50, 200]
_EMA_DEF     = [9,  21,  50]


def _strategy_help():
    """Referencia de los modos de salida/topes del simulador de trades
    (popover del botón '?'). La semántica real vive en trade_simulator.py."""
    def row(name, desc):
        return html.Tr([
            html.Td(name, style={"fontWeight": "bold", "whiteSpace": "nowrap",
                                 "padding": "2px 10px 2px 0",
                                 "verticalAlign": "top", "color": "#38bdf8"}),
            html.Td(desc, style={"padding": "2px 0"}),
        ])

    def title(text):
        return html.Div(text, className="fw-semibold mt-2 mb-1",
                        style={"color": "#dee2e6"})

    return html.Div([
        html.Div("El trade ENTRA cuando el score alcanza el umbral de "
                 "entrada. El modo de salida define cuándo se cierra; el "
                 "slider es su parámetro.", className="mb-1"),
        title("Modos de salida"),
        html.Table(html.Tbody([
            row("Umbral absoluto",
                "Sale cuando el score cae bajo un nivel fijo. Tiene sentido "
                "si tus señales cruzan el 0 (0 = la estrategia lo ve "
                "negativo)."),
            row("Entrada − Δ",
                "Sale cuando el score cae Δ puntos por debajo del score que "
                "tenía al entrar."),
            row("Máx score − Δ",
                "Sale cuando el score cae Δ puntos desde el MÁXIMO que tocó "
                "durante el trade (trailing sobre el score)."),
            row("Cruce media score",
                "Sale cuando el score cae bajo su propia media móvil de k "
                "ruedas (el impulso del score se dio vuelta)."),
            row("Horizonte fijo",
                "Sale a las N ruedas de la entrada, pase lo que pase. Mide "
                "el retorno posterior puro de la señal."),
            row("Percentil ranking",
                "Entrada Y salida por posición en el ranking del día (100 = "
                "mejor): entra al alcanzar el percentil de entrada, sale al "
                "caer bajo el de salida."),
        ])),
        title("Tope (opcional, uno a la vez)"),
        html.Div("Se evalúa además del modo — cierra el primero que se "
                 "cumpla: N ruedas (duración máxima), Stop loss % (caída "
                 "desde la entrada), Trailing stop % (caída desde el máximo "
                 "del precio), Take profit % (ganancia objetivo)."),
        title("Siempre activo"),
        html.Div("Si el activo deja de ser elegible para la estrategia (no "
                 "pasa el filtro), el trade se cierra — marcador «S filtro»."),
    ])


def _chk(id_, label, default_on=False, color=None):
    return dbc.Checklist(
        id=id_,
        options=[{"label": label, "value": 1}],
        value=[1] if default_on else [],
        input_class_name="btn-check",
        label_class_name="btn btn-outline-secondary btn-sm",
        label_checked_class_name="active",
        class_name="chart-ind-check",
        label_style={"fontSize": "0.75rem"},
    )


def _simple_slot(name, slot, color, default_period, dist_label_id=None):
    # El input de período (y la etiqueta de distancia) solo se muestran con el
    # slot activo — mismo patrón colapsable que Bollinger/RSI/MACD
    inner = [
        dbc.Input(
            id=f"chart-ind-{name}-{slot}-period",
            type="number", value=default_period, min=2, max=500, step=1,
            style={"width": "52px", "fontSize": "0.7rem", "padding": "1px 4px", "height": "22px"},
        ),
    ]
    if dist_label_id:
        inner.append(html.Span(
            id=dist_label_id,
            style={"fontSize": "0.68rem", "color": "#aaa"},
        ))
    return html.Div([
        _chk(f"chart-ind-{name}-{slot}-enabled", name.upper()),
        html.Div(inner, id=f"chart-ind-{name}-{slot}-params",
                 className="d-flex align-items-center gap-1",
                 style={"display": "none"}),
    ], className="d-flex align-items-center gap-1 ind-group",
       style={"--ind-color": color})


def _ind_toggle(label, name, params):
    param_inputs = []
    for pname, plabel, pdef, pmin, pmax, pstep in params:
        param_inputs += [
            html.Small(plabel, style={"color": "#aaa", "fontSize": "0.68rem", "whiteSpace": "nowrap"}),
            dbc.Input(
                id=f"chart-ind-{name}-1-{pname}",
                type="number", value=pdef, min=pmin, max=pmax, step=pstep,
                style={"width": "56px", "fontSize": "0.7rem", "padding": "1px 4px", "height": "24px"},
            ),
        ]
    return html.Div([
        _chk(f"chart-ind-{name}-1-enabled", label),
        html.Div(
            param_inputs,
            id=f"chart-ind-{name}-1-params",
            className="d-flex align-items-center gap-1",
            style={"display": "none"},
        ),
    ], className="d-flex align-items-center gap-1 ind-group")


def layout(**kwargs):
    from flask_login import current_user
    if not current_user.is_authenticated:
        return html.Div()

    chart_tab = dbc.Tab(label="Gráfico Técnico", tab_id="tab-chart", children=[
        # ── Barra única de controles: indicadores/overlays ────────────────
        # freq/tipo de gráfico/escala son opciones de visualización, no
        # indicadores — viven junto al selector de activo, ver layout() más
        # abajo (dbc.Row "Selector de activo compartido").
        html.Div([
            html.Div([_chk("chart-volume-enabled", "Vol", default_on=True)], className="ind-group"),
            _simple_slot("sma", 1, _SMA_COLORS[0], _SMA_DEF[0], dist_label_id="chart-sma-best-label"),
            _simple_slot("sma", 2, _SMA_COLORS[1], _SMA_DEF[1], dist_label_id="chart-sma-2-label"),
            _simple_slot("sma", 3, _SMA_COLORS[2], _SMA_DEF[2], dist_label_id="chart-sma-3-label"),
            _simple_slot("ema", 1, _EMA_COLORS[0], _EMA_DEF[0], dist_label_id="chart-ema-best-label"),
            _simple_slot("ema", 2, _EMA_COLORS[1], _EMA_DEF[1], dist_label_id="chart-ema-2-label"),
            _simple_slot("ema", 3, _EMA_COLORS[2], _EMA_DEF[2], dist_label_id="chart-ema-3-label"),
            _ind_toggle("Bollinger", "bollinger", [
                ("period", "Per",  20,  5, 100, 1),
                ("std_dev", "Dev", 2.0, 0.5, 4.0, 0.5),
            ]),
            _ind_toggle("RSI", "rsi", [("period", "Per", 14, 2, 100, 1)]),
            _ind_toggle("MACD", "macd", [
                ("fast",   "Rap",  12, 2, 100, 1),
                ("slow",   "Len",  26, 2, 200, 1),
                ("signal", "Señ",   9, 2,  50, 1),
            ]),
            _ind_toggle("Estocástico", "stochastic", [
                ("k_period", "%K",  14, 2, 100, 1),
                ("d_period", "%D",   3, 1,  20, 1),
            ]),
            _ind_toggle("ATR", "atr", [("period", "Per", 14, 2, 100, 1)]),
            html.Div([_chk("chart-ind-drawdown-1-enabled", "Drawdown %")], className="ind-group"),
            html.Div([_chk("chart-dd-enabled", "Drawdown Pisos")], className="ind-group"),
            html.Div([_chk("chart-events-enabled", "Eventos")], className="ind-group"),
            html.Div([
                _chk("chart-regime-enabled", "Régimen de Tendencia"),
                html.Span(id="chart-regime-label", style={"fontSize": "0.68rem", "color": "#aaa"}),
            ], className="d-flex align-items-center gap-1 ind-group"),
            html.Div([
                _chk("chart-vol-enabled", "Régimen de Volatilidad"),
                html.Span(id="chart-vol-label", style={"fontSize": "0.68rem", "color": "#aaa"}),
            ], className="d-flex align-items-center gap-1 ind-group"),
            html.Div([
                _chk("chart-sr-pivot-enabled", "Soportes / Resistencias"),
                html.Span(id="chart-sr-pivot-label", style={"fontSize": "0.68rem"}),
            ], className="d-flex align-items-center gap-1 ind-group"),
        ], className="d-flex flex-wrap align-items-center mb-1 mt-2 chart-toolbar"),

        # ── Stores ───────────────────────────────────────────────────────
        dcc.Store(id="chart-data"),
        dcc.Store(id="chart-render-dummy"),
        dcc.Store(id="chart-type-dummy"),
        dcc.Store(id="chart-freq-dummy"),
        dcc.Store(id="chart-scale-dummy"),
        dcc.Store(id="chart-ind-dummy"),
        dcc.Store(id="chart-volume-dummy"),
        dcc.Store(id="chart-events-dummy"),
        dcc.Store(id="chart-regime-dummy"),
        dcc.Store(id="chart-dd-dummy"),
        dcc.Store(id="chart-vol-dummy"),
        dcc.Store(id="chart-sr-pivot-dummy"),
        dcc.Store(id="chart-regime-data"),
        dcc.Store(id="chart-vol-data"),
        dcc.Store(id="chart-dd-data"),
        dcc.Store(id="chart-regime-data-dummy"),
        dcc.Store(id="chart-vol-data-dummy"),
        dcc.Store(id="chart-dd-data-dummy"),
        dcc.Store(id="chart-strategy-data"),
        dcc.Store(id="chart-strategy-dummy"),
        dcc.Store(id="chart-strategy-data-dummy"),
        dcc.Store(id="chart-strategy-drag-dummy"),

        # ── Gráfico ──────────────────────────────────────────────────────
        dcc.Loading(
            [
                html.Div(id="chart-load-output", style={"display": "none"}),
                html.Div(
                    id="lwc-container",
                    style={"backgroundColor": "#1e1e1e", "padding": "8px", "borderRadius": "4px"},
                ),
                # P&F clásico (Plotly): visible solo con chart-type = pnf_classic
                dcc.Graph(
                    id="pnf-graph",
                    config={"displayModeBar": False},
                    style={"display": "none"},
                ),
            ],
            type="circle",
            color="#dee2e6",
        ),
    ])

    fundamentals_tab = dbc.Tab(label="Fundamentales", tab_id="tab-fundamentals", children=[
        html.Div(style={"height": "12px"}),
        dbc.Alert(id="fund-alert", is_open=False, dismissable=True, className="mb-2"),
        dcc.Loading(
            html.Div(id="fund-content"),
            type="circle", color="#dee2e6",
        ),
    ])

    indicators_tab = dbc.Tab(
        label="Panel de Indicadores",
        tab_id="tab-indicators",
        children=[
            html.Div(style={"height": "12px"}),
            dcc.Loading(
                html.Div(id="indicators-panel-content"),
                type="circle", color="#dee2e6",
            ),
        ],
    )

    distribution_tab = dbc.Tab(
        label="Posicionamiento Histórico",
        tab_id="tab-distribution",
        children=[
            dbc.Row([
                dbc.Col(
                    dcc.Dropdown(
                        id="dist-indicator-select",
                        options=[],
                        placeholder="Seleccioná un indicador...",
                        searchable=True,
                        clearable=False,
                        style={"fontSize": "0.8rem", "minWidth": "280px"},
                    ),
                    width="auto",
                ),
                dbc.Col(
                    [
                        html.Small("Ancho de bin", style={"color": "#9ca3af", "whiteSpace": "nowrap"}),
                        dbc.Input(
                            id="dist-bin-size",
                            type="number", value=5, min=0, max=1000, step=1,
                            style={"width": "80px", "fontSize": "0.8rem"},
                        ),
                    ],
                    width="auto",
                    className="d-flex align-items-center gap-2",
                ),
            ], className="mb-2 mt-2 g-2 align-items-center"),
            html.Div(id="dist-stats", className="mb-2"),
            dcc.Loading(
                dcc.Graph(
                    id="dist-graph",
                    config={"displayModeBar": False},
                    style={"height": "450px"},
                ),
                type="circle", color="#dee2e6",
            ),
        ],
    )

    return html.Div([
        # ── Selector de activo + opciones de visualización del gráfico ─────
        # freq/tipo de gráfico/escala no son indicadores, son cómo se ve el
        # gráfico — viven acá, no en la barra de indicadores del tab.
        dbc.Row([
            dbc.Col(
                dcc.Dropdown(
                    id="analysis-asset-select",
                    options=[],
                    placeholder="Seleccioná un activo...",
                    searchable=True,
                    clearable=False,
                    style={"fontSize": "0.8rem"},
                ),
                style={"minWidth": "220px", "maxWidth": "380px"},
            ),
            dbc.Col(html.Div(dbc.RadioItems(
                id="chart-freq",
                options=[{"label": x, "value": x} for x in ["D", "W", "M"]],
                value="D",
                input_class_name="btn-check",
                label_class_name="btn btn-outline-secondary btn-sm",
                label_checked_class_name="active",
                class_name="btn-group btn-group-sm",
            ), className="ind-group"), width="auto"),
            dbc.Col(html.Div(dbc.RadioItems(
                id="chart-type",
                options=[{"label": "Velas",   "value": "candlestick"},
                         {"label": "Línea",   "value": "line"},
                         {"label": "P&F",     "value": "pnf"},
                         {"label": "P&F X/O", "value": "pnf_classic"}],
                value="candlestick",
                input_class_name="btn-check",
                label_class_name="btn btn-outline-secondary btn-sm",
                label_checked_class_name="active",
                class_name="btn-group btn-group-sm",
            ), className="ind-group"), width="auto"),
            dbc.Col(html.Div(dbc.RadioItems(
                id="chart-yscale",
                options=[{"label": "Arit", "value": "linear"},
                         {"label": "Log",  "value": "log"}],
                value="linear",
                input_class_name="btn-check",
                label_class_name="btn btn-outline-secondary btn-sm",
                label_checked_class_name="active",
                class_name="btn-group btn-group-sm",
            ), className="ind-group"), width="auto"),
        ], className="mb-1 g-2 align-items-center chart-toolbar"),

        # ── Estrategia: sección propia (más controles que las opciones de
        #    vista — dropdown de salida, tope y métricas necesitan su fila) ──
        dbc.Row([
            dbc.Col(html.Div([
                _chk("chart-strategy-enabled", "Estrategia"),
                html.Div([
                    dcc.Dropdown(
                        id="chart-strategy-sel",
                        options=[], placeholder="Estrategia...",
                        clearable=False,
                        style={"width": "200px", "fontSize": "0.72rem"},
                    ),
                    html.Small([html.Span("Entrada ≥ ", id="chart-strategy-entry-lbl"),
                                html.Span("20", id="chart-strategy-entry-val",
                                          style={"color": "#4ade80"})],
                               style={"color": "#aaa", "fontSize": "0.68rem",
                                      "whiteSpace": "nowrap"}),
                    html.Div(dcc.Slider(
                        id="chart-strategy-entry", min=-100, max=100, step=5, value=20,
                        marks=None,
                        tooltip={"placement": "bottom"},
                    ), style={"width": "130px"}),
                    html.Div(dcc.Dropdown(
                        id="chart-strategy-exit-mode",
                        options=[
                            {"label": "Salida: umbral absoluto",   "value": "absolute"},
                            {"label": "Salida: entrada − Δ",       "value": "delta_entry"},
                            {"label": "Salida: máx score − Δ",     "value": "trailing_score"},
                            {"label": "Salida: cruce media score", "value": "score_ma"},
                            {"label": "Salida: horizonte fijo",    "value": "horizon"},
                            {"label": "Salida: percentil ranking", "value": "percentile"},
                        ],
                        value="absolute", clearable=False,
                        style={"width": "168px", "fontSize": "0.72rem"},
                    ), id="chart-strategy-exit-mode-wrap"),
                    dbc.Tooltip(
                        "Sale cuando el score cae bajo un nivel fijo.",
                        id="chart-strategy-exit-mode-tip",
                        target="chart-strategy-exit-mode-wrap",
                        placement="bottom",
                        style={"maxWidth": "300px", "fontSize": "0.75rem",
                               "backgroundColor": "#1f2937", "color": "#dee2e6",
                               "border": "1px solid #374151"},
                    ),
                    html.Small([html.Span("Salida < ", id="chart-strategy-exit-lbl"),
                                html.Span("0", id="chart-strategy-exit-val",
                                          style={"color": "#ef5350"})],
                               style={"color": "#aaa", "fontSize": "0.68rem",
                                      "whiteSpace": "nowrap"}),
                    html.Div(dcc.Slider(
                        id="chart-strategy-exit", min=-100, max=100, step=5, value=0,
                        marks=None,
                        tooltip={"placement": "bottom"},
                    ), style={"width": "130px"}),
                    dcc.Dropdown(
                        id="chart-strategy-cap",
                        options=[
                            {"label": "Sin tope",        "value": "none"},
                            {"label": "Tope: N ruedas",  "value": "max_bars"},
                            {"label": "Stop loss %",     "value": "stop_loss"},
                            {"label": "Trailing stop %", "value": "trailing_stop"},
                            {"label": "Take profit %",   "value": "take_profit"},
                        ],
                        value="none", clearable=False,
                        style={"width": "128px", "fontSize": "0.72rem"},
                    ),
                    dcc.Input(
                        id="chart-strategy-cap-val", type="number", value=10,
                        style={"width": "58px", "fontSize": "0.72rem",
                               "display": "none"},
                    ),
                    dbc.Button("?", id="chart-strategy-help-btn",
                               color="secondary", outline=True, size="sm",
                               style={"fontSize": "0.7rem", "padding": "0 7px",
                                      "borderRadius": "50%", "lineHeight": "1.4"}),
                    dbc.Popover(
                        dbc.PopoverBody(_strategy_help(), style={
                            "fontSize": "0.75rem", "color": "#dee2e6",
                            "backgroundColor": "#1f2937",
                        }),
                        target="chart-strategy-help-btn", trigger="legacy",
                        placement="bottom",
                        style={"maxWidth": "480px",
                               "backgroundColor": "#1f2937",
                               "border": "1px solid #374151"},
                    ),
                    html.Span(id="chart-strategy-label",
                              style={"fontSize": "0.68rem", "color": "#aaa",
                                     "whiteSpace": "nowrap"}),
                ], id="chart-strategy-params",
                   className="d-flex align-items-center gap-1 flex-wrap",
                   style={"display": "none"}),
            ], className="d-flex align-items-center gap-1 ind-group"), width="auto"),
        ], className="mb-1 g-2 align-items-center chart-toolbar"),

        # ── Tabs ──────────────────────────────────────────────────────────
        dbc.Tabs(
            [chart_tab, fundamentals_tab, indicators_tab, distribution_tab],
            id="analysis-tabs",
            active_tab="tab-chart",
        ),
    ], style={"padding": "0 8px"})


dash.register_page(__name__, path="/activo", title="Análisis de Activo", layout=layout)
