import dash
import dash_bootstrap_components as dbc
from dash import dcc, html

_SMA_COLORS  = ["#ff9800", "#e91e63", "#4caf50"]
_EMA_COLORS  = ["#00bcd4", "#9c27b0", "#ffeb3b"]
_SMA_DEF     = [20, 50, 200]
_EMA_DEF     = [9,  21,  50]


def _sep():
    return html.Div(style={
        "width": "1px", "backgroundColor": "#555",
        "alignSelf": "stretch", "margin": "0 4px",
    })


def _simple_slot(name, slot, color, default_period):
    """Toggle compacto para SMA/EMA: switch + periodo siempre visible."""
    return html.Div([
        dbc.Switch(
            id=f"chart-ind-{name}-{slot}-enabled",
            value=False,
            style={"marginBottom": 0},
        ),
        html.Span(
            name.upper(),
            style={"fontSize": "0.72rem", "color": color},
        ),
        dbc.Input(
            id=f"chart-ind-{name}-{slot}-period",
            type="number", value=default_period, min=2, max=500, step=1,
            style={"width": "44px", "fontSize": "0.7rem", "padding": "1px 3px", "height": "20px"},
        ),
    ], className="d-flex align-items-center border rounded px-2",
       style={"gap": "4px", "paddingTop": "3px", "paddingBottom": "3px"})


def _ind_toggle(label, name, params):
    """Toggle con params colapsables para indicadores de panel separado."""
    # params: [(pname, short_label, default, min, max, step), ...]
    param_inputs = []
    for pname, plabel, pdef, pmin, pmax, pstep in params:
        param_inputs += [
            html.Small(plabel, style={"color": "#aaa", "fontSize": "0.68rem", "whiteSpace": "nowrap"}),
            dbc.Input(
                id=f"chart-ind-{name}-1-{pname}",
                type="number", value=pdef, min=pmin, max=pmax, step=pstep,
                style={"width": "44px", "fontSize": "0.7rem", "padding": "1px 3px", "height": "20px"},
            ),
        ]
    return html.Div([
        dbc.Switch(
            id=f"chart-ind-{name}-1-enabled",
            label=label, value=False,
            style={"fontSize": "0.75rem", "marginBottom": 0},
        ),
        html.Div(
            param_inputs,
            id=f"chart-ind-{name}-1-params",
            className="d-flex align-items-center gap-1 ms-1",
            style={"display": "none"},
        ),
    ], className="d-flex align-items-center border rounded px-2",
       style={"gap": "4px", "paddingTop": "3px", "paddingBottom": "3px"})


def layout(**kwargs):
    from flask_login import current_user
    if not current_user.is_authenticated:
        return html.Div()

    _radio_sm = {"fontSize": "0.75rem"}

    return html.Div([
        # ── Fila 1: activo + frecuencia + tipo + escala ────────────────────────
        dbc.Row([
            dbc.Col(
                dcc.Dropdown(
                    id="chart-asset-select",
                    options=[],
                    placeholder="Selecciona un activo...",
                    searchable=True,
                    clearable=False,
                    style={"fontSize": "0.8rem"},
                ),
                style={"minWidth": "220px", "maxWidth": "320px"},
            ),
            dbc.Col(
                dbc.RadioItems(
                    id="chart-freq",
                    options=[{"label": x, "value": x} for x in ["D", "W", "M"]],
                    value="D", inline=True,
                    inputStyle={"marginRight": "3px"}, style=_radio_sm,
                ),
                width="auto",
            ),
            dbc.Col(
                dbc.RadioItems(
                    id="chart-type",
                    options=[{"label": "Velas", "value": "candlestick"},
                             {"label": "Linea",  "value": "line"}],
                    value="candlestick", inline=True,
                    inputStyle={"marginRight": "3px"}, style=_radio_sm,
                ),
                width="auto",
            ),
            dbc.Col(
                dbc.RadioItems(
                    id="chart-yscale",
                    options=[{"label": "Lin", "value": "linear"},
                             {"label": "Log", "value": "log"}],
                    value="linear", inline=True,
                    inputStyle={"marginRight": "3px"}, style=_radio_sm,
                ),
                width="auto",
            ),
        ], className="mb-1 g-2 align-items-center flex-wrap"),

        # ── Fila 2: controles de indicadores ──────────────────────────────────
        html.Div([
            # Volumen
            html.Div([
                dbc.Switch(id="chart-volume-enabled", value=True,
                           style={"marginBottom": 0}),
                html.Span("Vol", style={"fontSize": "0.72rem"}),
            ], className="d-flex align-items-center border rounded px-2",
               style={"gap": "4px", "paddingTop": "3px", "paddingBottom": "3px"}),
            _sep(),
            # SMA ×3
            *[_simple_slot("sma", i + 1, _SMA_COLORS[i], _SMA_DEF[i]) for i in range(3)],
            _sep(),
            # EMA ×3
            *[_simple_slot("ema", i + 1, _EMA_COLORS[i], _EMA_DEF[i]) for i in range(3)],
            _sep(),
            # Bollinger
            _ind_toggle("Bollinger", "bollinger", [
                ("period", "Per",  20,  5, 100, 1),
                ("std_dev", "Dev", 2.0, 0.5, 4.0, 0.5),
            ]),
            _sep(),
            # Separados
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
            # Drawdown panel (indicador de panel separado)
            html.Div([
                dbc.Switch(id="chart-ind-drawdown-1-enabled", value=False,
                           style={"marginBottom": 0}),
                html.Span("Drawdown %", style={"fontSize": "0.72rem", "color": "#ef5350"}),
            ], className="d-flex align-items-center border rounded px-2",
               style={"gap": "4px", "paddingTop": "3px", "paddingBottom": "3px"}),
            # Drawdown markers (pisos históricos sobre el precio)
            html.Div([
                dbc.Switch(id="chart-dd-enabled", value=False,
                           style={"marginBottom": 0}),
                html.Span("Drawdown Pisos", style={"fontSize": "0.72rem", "color": "#ef5350"}),
            ], className="d-flex align-items-center border rounded px-2",
               style={"gap": "4px", "paddingTop": "3px", "paddingBottom": "3px"}),
            _sep(),
            # Eventos de mercado
            html.Div([
                dbc.Switch(id="chart-events-enabled", value=False,
                           style={"marginBottom": 0}),
                html.Span("Eventos", style={"fontSize": "0.72rem", "color": "#ff9800"}),
            ], className="d-flex align-items-center border rounded px-2",
               style={"gap": "4px", "paddingTop": "3px", "paddingBottom": "3px"}),
            # Régimen de Tendencia
            html.Div([
                dbc.Switch(id="chart-regime-enabled", value=False,
                           style={"marginBottom": 0}),
                html.Span("Tendencia", style={"fontSize": "0.72rem", "color": "#9c27b0"}),
                html.Span(id="chart-regime-label", style={"fontSize": "0.68rem", "color": "#aaa"}),
            ], className="d-flex align-items-center border rounded px-2",
               style={"gap": "4px", "paddingTop": "3px", "paddingBottom": "3px"}),
            # Volatilidad ATR
            html.Div([
                dbc.Switch(id="chart-vol-enabled", value=False,
                           style={"marginBottom": 0}),
                html.Span("Volatilidad", style={"fontSize": "0.72rem", "color": "#ff9800"}),
                html.Span(id="chart-vol-label", style={"fontSize": "0.68rem", "color": "#aaa"}),
            ], className="d-flex align-items-center border rounded px-2",
               style={"gap": "4px", "paddingTop": "3px", "paddingBottom": "3px"}),
            _sep(),
            # Pivots S/R
            html.Div([
                dbc.Switch(id="chart-sr-pivot-enabled", value=False,
                           style={"marginBottom": 0}),
                html.Span("Niveles S/R", style={"fontSize": "0.72rem", "color": "#ef9a9a"}),
                html.Span(id="chart-sr-pivot-label", style={"fontSize": "0.68rem", "color": "#aaa"}),
            ], className="d-flex align-items-center border rounded px-2",
               style={"gap": "4px", "paddingTop": "3px", "paddingBottom": "3px"}),
        ], className="d-flex flex-wrap align-items-center mb-1", style={"gap": "6px"}),

        # ── Stores ─────────────────────────────────────────────────────────────
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

        # ── Contenedor del gráfico ─────────────────────────────────────────────
        dcc.Loading(
            [
                html.Div(id="chart-load-output", style={"display": "none"}),
                html.Div(
                    id="lwc-container",
                    style={"backgroundColor": "#1e1e1e", "padding": "8px", "borderRadius": "4px"},
                ),
            ],
            type="circle",
            color="#dee2e6",
        ),
    ], style={"padding": "0 8px"})


dash.register_page(__name__, path="/chart", title="Grafico tecnico", layout=layout)
