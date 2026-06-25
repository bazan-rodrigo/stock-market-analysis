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


def _chk(id_, label, default_on=False, color=None):
    """Checkbox estilizado como botón toggle (mismo estilo que D/W/M)."""
    label_style = {"fontSize": "0.75rem"}
    if color:
        label_style["color"] = color
    return dbc.Checklist(
        id=id_,
        options=[{"label": label, "value": 1}],
        value=[1] if default_on else [],
        input_class_name="btn-check",
        label_class_name="btn btn-outline-secondary btn-sm",
        label_checked_class_name="active",
        class_name="chart-ind-check",
        label_style=label_style,
    )


def _simple_slot(name, slot, color, default_period, dist_label_id=None):
    """Botón toggle + periodo siempre visible (SMA / EMA)."""
    children = [
        _chk(f"chart-ind-{name}-{slot}-enabled", name.upper(), color=color),
        dbc.Input(
            id=f"chart-ind-{name}-{slot}-period",
            type="number", value=default_period, min=2, max=500, step=1,
            style={"width": "44px", "fontSize": "0.7rem", "padding": "1px 3px", "height": "24px"},
        ),
    ]
    if dist_label_id:
        children.append(html.Span(
            id=dist_label_id,
            style={"fontSize": "0.68rem", "color": "#aaa"},
        ))
    return html.Div(children, className="d-flex align-items-center gap-1")


def _ind_toggle(label, name, params):
    """Botón toggle con params colapsables (Bollinger, RSI, MACD, etc.)."""
    # params: [(pname, short_label, default, min, max, step), ...]
    param_inputs = []
    for pname, plabel, pdef, pmin, pmax, pstep in params:
        param_inputs += [
            html.Small(plabel, style={"color": "#aaa", "fontSize": "0.68rem", "whiteSpace": "nowrap"}),
            dbc.Input(
                id=f"chart-ind-{name}-1-{pname}",
                type="number", value=pdef, min=pmin, max=pmax, step=pstep,
                style={"width": "44px", "fontSize": "0.7rem", "padding": "1px 3px", "height": "24px"},
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
    ], className="d-flex align-items-center gap-1")


def layout(**kwargs):
    from flask_login import current_user
    if not current_user.is_authenticated:
        return html.Div()

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
                    value="D",
                    input_class_name="btn-check",
                    label_class_name="btn btn-outline-secondary btn-sm",
                    label_checked_class_name="active",
                    class_name="btn-group btn-group-sm",
                ),
                width="auto",
            ),
            dbc.Col(
                dbc.RadioItems(
                    id="chart-type",
                    options=[{"label": "Velas", "value": "candlestick"},
                             {"label": "Línea", "value": "line"}],
                    value="candlestick",
                    input_class_name="btn-check",
                    label_class_name="btn btn-outline-secondary btn-sm",
                    label_checked_class_name="active",
                    class_name="btn-group btn-group-sm",
                ),
                width="auto",
            ),
            dbc.Col(
                dbc.RadioItems(
                    id="chart-yscale",
                    options=[{"label": "Arit", "value": "linear"},
                             {"label": "Log",  "value": "log"}],
                    value="linear",
                    input_class_name="btn-check",
                    label_class_name="btn btn-outline-secondary btn-sm",
                    label_checked_class_name="active",
                    class_name="btn-group btn-group-sm",
                ),
                width="auto",
            ),
        ], className="mb-1 g-2 align-items-center flex-wrap"),

        # ── Fila 2: controles de indicadores ──────────────────────────────────
        html.Div([
            # Volumen
            _chk("chart-volume-enabled", "Vol", default_on=True),
            _sep(),
            # SMA ×3  (slot 1 = mejor MA, muestra distancia % al precio)
            _simple_slot("sma", 1, _SMA_COLORS[0], _SMA_DEF[0], dist_label_id="chart-sma-best-label"),
            *[_simple_slot("sma", i + 1, _SMA_COLORS[i], _SMA_DEF[i]) for i in range(1, 3)],
            _sep(),
            # EMA ×3
            _simple_slot("ema", 1, _EMA_COLORS[0], _EMA_DEF[0], dist_label_id="chart-ema-best-label"),
            *[_simple_slot("ema", i + 1, _EMA_COLORS[i], _EMA_DEF[i]) for i in range(1, 3)],
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
            # Drawdown panel
            _chk("chart-ind-drawdown-1-enabled", "Drawdown %", color="#ef5350"),
            # Drawdown markers (pisos históricos sobre el precio)
            _chk("chart-dd-enabled", "Drawdown Pisos", color="#ef5350"),
            _sep(),
            # Eventos de mercado
            _chk("chart-events-enabled", "Eventos", color="#ff9800"),
            # Régimen de Tendencia
            html.Div([
                _chk("chart-regime-enabled", "Régimen de Tendencia", color="#9c27b0"),
                html.Span(id="chart-regime-label", style={"fontSize": "0.68rem", "color": "#aaa"}),
            ], className="d-flex align-items-center gap-1"),
            # Volatilidad ATR
            html.Div([
                _chk("chart-vol-enabled", "Régimen de Volatilidad", color="#ff9800"),
                html.Span(id="chart-vol-label", style={"fontSize": "0.68rem", "color": "#aaa"}),
            ], className="d-flex align-items-center gap-1"),
            _sep(),
            # Pivots S/R
            html.Div([
                _chk("chart-sr-pivot-enabled", "Soportes / Resistencias", color="#ef9a9a"),
                html.Span(id="chart-sr-pivot-label", style={"fontSize": "0.68rem", "color": "#aaa"}),
            ], className="d-flex align-items-center gap-1"),
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
