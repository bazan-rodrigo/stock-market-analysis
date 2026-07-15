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
        html.Div(["Tres grupos de condiciones, todas combinables con el "
                  "mismo control (tilde + valor). Regla clave: las de ",
                  html.B("Entrada"), " se exigen TODAS a la vez (Y); las de ",
                  html.B("Salida"), " disparan con la PRIMERA que se cumpla "
                  "(O). Precedencia de salidas en la misma barra: filtro → "
                  "precio/tiempo → score."],
                 className="mb-1"),
        title("Entrada (deben cumplirse TODAS las activas)"),
        html.Table(html.Tbody([
            row("Sc ≥", "Score de la estrategia sobre el umbral."),
            row("Pct ≥", "Percentil del activo en el ranking del día sobre "
                "el umbral (100 = mejor). Sc+Pct juntas: \"score alto Y "
                "entre los mejores\"."),
            row("Cruce", "Freno de re-entrada: tras una salida, la condición "
                "de entrada debe dejar de cumplirse antes de poder "
                "re-entrar (evita el whipsaw)."),
            row("Enfr.", "Freno de re-entrada: espera N ruedas después de "
                "cada salida."),
        ])),
        title("Salida por score (dispara la primera que se cumpla)"),
        html.Table(html.Tbody([
            row("Abs <", "El score cae bajo un nivel fijo. Tiene sentido si "
                "tus señales cruzan el 0 (0 = la estrategia lo ve negativo)."),
            row("Ent−Δ", "El score cae Δ puntos por debajo del score que "
                "tenía al entrar (stop loss del score)."),
            row("Máx−Δ", "El score cae Δ puntos desde el MÁXIMO del trade "
                "(trailing stop del score)."),
            row("Media k", "El score cae bajo su media móvil de k ruedas "
                "(el impulso se dio vuelta)."),
            row("Pct <", "El activo cae bajo ese percentil del ranking del "
                "día. Clásico de rotación: entra Pct ≥ 90, sale Pct < 70."),
        ])),
        title("Salida por precio/tiempo (dispara la primera que se cumpla)"),
        html.Div("Ruedas (duración máxima), SL% (stop loss desde la "
                 "entrada), TS% (trailing stop desde el máximo del precio), "
                 "TP% (take profit). Miran el PRECIO real del trade — "
                 "cubren el caso \"score alto pero precio en caída\"."),
        title("Siempre activo"),
        html.Div("Si el activo deja de ser elegible para la estrategia (no "
                 "pasa el filtro), el trade se cierra — marcador «S filtro». "
                 "Sin ninguna salida activa, mantiene mientras sea elegible "
                 "(buy & hold del filtro)."),
        title("¿Cuál uso?"),
        html.Div(["Para MEDIR la señal: ", html.B("solo Sc ≥ + Ruedas"),
                 " (retorno posterior puro, como el backtest). Para simular "
                 "operatoria: Pct ≥ en la entrada con Pct < en la salida, o "
                 "Máx−Δ, más SL% como red. Para aislar el efecto de una "
                 "condición: activá una sola y compará corridas."]),
    ])


def _cap_control(key, label, default, tip, id_base="chart-strategy-cap",
                 min_=1, default_on=False):
    """Control checkbox+valor del simulador — el componente ÚNICO de las tres
    secciones (entrada / salida por score / salida por precio-tiempo). El
    valor solo se ve con el control activo (toggle_sim_inputs); default_on
    también muestra el input de arranque (el callback tiene
    prevent_initial_call)."""
    input_style = {"width": "58px", "fontSize": "0.72rem",
                   "padding": "1px 4px", "height": "22px"}
    if not default_on:
        input_style["display"] = "none"
    return html.Div([
        _chk(f"{id_base}-{key}-on", label, default_on=default_on),
        dbc.Input(
            id=f"{id_base}-{key}", type="number", value=default,
            min=min_, step=1, style=input_style,
        ),
        dbc.Tooltip(tip, target=f"{id_base}-{key}-wrap",
                    placement="bottom",
                    style={"fontSize": "0.75rem", "maxWidth": "260px",
                           "backgroundColor": "#1f2937", "color": "#dee2e6",
                           "border": "1px solid #374151"}),
    ], id=f"{id_base}-{key}-wrap",
       className="d-flex align-items-center gap-1")


def _sim_group(title, children):
    """Grupo rotulado del panel de simulación (Entrada / Salida por score /
    Salida por precio-tiempo), con separador visual a la izquierda."""
    return html.Div(
        [html.Span(f"{title}:",
                   style={"fontSize": "0.72rem", "color": "#6c757d",
                          "fontWeight": "600", "whiteSpace": "nowrap"})]
        + children,
        className="d-flex align-items-center gap-1 flex-wrap",
        style={"borderLeft": "1px solid #374151", "paddingLeft": "8px"},
    )


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

        # ── Simulación de estrategias: sección propia. Tres grupos rotulados
        #    con el mismo componente (checkbox + valor): Entrada (AND),
        #    Salida por score (OR) y Salida por precio/tiempo (OR). El
        #    resultado va SIEMPRE en su propia línea debajo. ──
        dbc.Row([
            dbc.Col(html.Div([
                html.Div([
                    _chk("chart-strategy-enabled", "Simulación de estrategias"),
                    html.Div([
                        dcc.Dropdown(
                            id="chart-strategy-sel",
                            options=[], placeholder="Estrategia...",
                            clearable=False,
                            style={"width": "200px", "fontSize": "0.72rem"},
                        ),
                        _sim_group("Entrada", [
                            _cap_control("entry-sc", "Sc ≥", 20,
                                         "Entrada: score de la estrategia mayor "
                                         "o igual al umbral.",
                                         id_base="chart-strategy",
                                         min_=-100, default_on=True),
                            _cap_control("entry-pct", "Pct ≥", 90,
                                         "Entrada: percentil del activo en el "
                                         "ranking del día (100 = mejor) mayor o "
                                         "igual al umbral. Con varias activas, "
                                         "deben cumplirse TODAS.",
                                         id_base="chart-strategy", min_=0),
                            html.Div(_chk("chart-strategy-rearm", "Cruce"),
                                     id="chart-strategy-rearm-wrap"),
                            dbc.Tooltip(
                                "Re-entrada por cruce: tras una salida, la "
                                "condición de entrada debe dejar de cumplirse "
                                "antes de poder volver a entrar (evita "
                                "re-entradas inmediatas).",
                                target="chart-strategy-rearm-wrap",
                                placement="bottom",
                                style={"fontSize": "0.75rem", "maxWidth": "260px",
                                       "backgroundColor": "#1f2937",
                                       "color": "#dee2e6",
                                       "border": "1px solid #374151"}),
                            _cap_control("cooldown", "Enfr.", 5,
                                         "Enfriamiento: tras una salida, espera "
                                         "N ruedas antes de permitir otra "
                                         "entrada.",
                                         id_base="chart-strategy", min_=0),
                        ]),
                        _sim_group("Salida por score", [
                            _cap_control("xs-abs", "Abs <", 0,
                                         "Sale cuando el score cae bajo un "
                                         "nivel fijo (útil si tus señales "
                                         "cruzan el 0).",
                                         id_base="chart-strategy", min_=-100),
                            _cap_control("xs-dent", "Ent−Δ", 20,
                                         "Sale cuando el score cae Δ puntos "
                                         "bajo el score que tenía al entrar.",
                                         id_base="chart-strategy", min_=1),
                            _cap_control("xs-dmax", "Máx−Δ", 20,
                                         "Sale cuando el score cae Δ puntos "
                                         "desde el máximo del trade (trailing "
                                         "sobre el score).",
                                         id_base="chart-strategy", min_=1),
                            _cap_control("xs-mak", "Media k", 10,
                                         "Sale cuando el score cae bajo su "
                                         "media móvil de k ruedas (el impulso "
                                         "se dio vuelta).",
                                         id_base="chart-strategy", min_=2),
                            _cap_control("xs-pct", "Pct <", 70,
                                         "Sale cuando el percentil del activo "
                                         "en el ranking del día cae bajo el "
                                         "umbral (100 = mejor).",
                                         id_base="chart-strategy", min_=0),
                        ]),
                        _sim_group("Salida por precio/tiempo", [
                            _cap_control("bars", "Ruedas", 60,
                                         "Duración máxima del trade en ruedas."),
                            _cap_control("sl", "SL%", 10,
                                         "Stop loss % desde el precio de "
                                         "entrada."),
                            _cap_control("ts", "TS%", 15,
                                         "Trailing stop % desde el máximo del "
                                         "precio."),
                            _cap_control("tp", "TP%", 20,
                                         "Take profit % desde el precio de "
                                         "entrada."),
                        ]),
                        dbc.Button("?", id="chart-strategy-help-btn",
                                   color="secondary", outline=True, size="sm",
                                   style={"fontSize": "0.7rem",
                                          "padding": "0 7px",
                                          "borderRadius": "50%",
                                          "lineHeight": "1.4"}),
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
                    ], id="chart-strategy-params",
                       className="d-flex align-items-center gap-2 flex-wrap",
                       style={"display": "none"}),
                ], className="d-flex align-items-center gap-1 ind-group flex-wrap"),
                # Resultado SIEMPRE en su propia línea, con rótulo fijo
                html.Div([
                    html.Small("Resultado de la simulación: ",
                               style={"color": "#6c757d", "fontWeight": "600",
                                      "fontSize": "0.7rem"}),
                    html.Span(id="chart-strategy-label",
                              style={"fontSize": "0.68rem", "color": "#aaa"}),
                ], id="chart-strategy-result",
                   className="mt-1", style={"display": "none"}),
            ]), width=12),
        ], className="mb-1 g-2 align-items-center chart-toolbar"),

        # ── Tabs ──────────────────────────────────────────────────────────
        dbc.Tabs(
            [chart_tab, fundamentals_tab, indicators_tab, distribution_tab],
            id="analysis-tabs",
            active_tab="tab-chart",
        ),
    ], style={"padding": "0 8px"})


dash.register_page(__name__, path="/activo", title="Análisis de Activo", layout=layout)
