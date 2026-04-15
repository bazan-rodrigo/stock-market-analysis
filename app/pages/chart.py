import dash
import dash_bootstrap_components as dbc
from dash import dcc, html
from app.indicators.registry import overlay_indicators, separate_indicators, all_indicators


def _param_inputs(ind):
    inputs = []
    for p in ind.PARAMS:
        inputs += [
            html.Small(p.label[:4], style={"color": "#aaa", "fontSize": "0.68rem", "whiteSpace": "nowrap"}),
            dbc.Input(
                id=f"chart-ind-{ind.NAME}-{p.name}",
                type="number",
                value=p.default,
                min=p.min_val,
                max=p.max_val,
                step=p.step or (1 if p.type == "int" else 0.1),
                style={"width": "44px", "fontSize": "0.7rem", "padding": "1px 3px", "height": "20px"},
            ),
        ]
    return inputs


def _ind_toggle(ind):
    return html.Div([
        dbc.Switch(
            id=f"chart-ind-{ind.NAME}-enabled",
            label=ind.LABEL,
            value=False,
            style={"fontSize": "0.75rem", "marginBottom": 0},
        ),
        html.Div(
            _param_inputs(ind),
            id=f"chart-ind-{ind.NAME}-params",
            className="d-flex align-items-center gap-1 ms-1",
            style={"display": "none"},
        ),
    ], className="d-flex align-items-center border rounded px-2",
       style={"gap": "4px", "paddingTop": "3px", "paddingBottom": "3px"})


def _vol_toggle():
    return html.Div([
        dbc.Switch(
            id="chart-volume-enabled",
            label="Vol",
            value=True,
            style={"fontSize": "0.75rem", "marginBottom": 0},
        ),
    ], className="d-flex align-items-center border rounded px-2",
       style={"gap": "4px", "paddingTop": "3px", "paddingBottom": "3px"})


def layout(**kwargs):
    from flask_login import current_user
    if not current_user.is_authenticated:
        return html.Div()

    _radio_sm = {"fontSize": "0.75rem"}
    _sep = html.Div(style={
        "width": "1px", "backgroundColor": "#555",
        "alignSelf": "stretch", "margin": "0 4px",
    })

    return html.Div([
        # ── Fila 1: activo + frecuencia + tipo + escala ────────────────────────
        dbc.Row([
            dbc.Col(
                dbc.Select(
                    id="chart-asset-select",
                    options=[],
                    placeholder="Selecciona un activo...",
                    style={"fontSize": "0.8rem", "height": "30px", "padding": "2px 8px"},
                ),
                style={"maxWidth": "280px"},
            ),
            dbc.Col(
                dbc.RadioItems(
                    id="chart-freq",
                    options=[
                        {"label": "D", "value": "D"},
                        {"label": "W", "value": "W"},
                        {"label": "M", "value": "M"},
                    ],
                    value="D",
                    inline=True,
                    inputStyle={"marginRight": "3px"},
                    style=_radio_sm,
                ),
                width="auto",
            ),
            dbc.Col(
                dbc.RadioItems(
                    id="chart-type",
                    options=[
                        {"label": "Velas", "value": "candlestick"},
                        {"label": "Linea",  "value": "line"},
                    ],
                    value="candlestick",
                    inline=True,
                    inputStyle={"marginRight": "3px"},
                    style=_radio_sm,
                ),
                width="auto",
            ),
            dbc.Col(
                dbc.RadioItems(
                    id="chart-yscale",
                    options=[
                        {"label": "Lin", "value": "linear"},
                        {"label": "Log", "value": "log"},
                    ],
                    value="linear",
                    inline=True,
                    inputStyle={"marginRight": "3px"},
                    style=_radio_sm,
                ),
                width="auto",
            ),
        ], className="mb-1 g-2 align-items-center flex-wrap"),

        # ── Fila 2: volumen + indicadores ──────────────────────────────────────
        html.Div([
            _vol_toggle(),
            _sep,
            *[_ind_toggle(ind) for ind in overlay_indicators()],
            _sep,
            *[_ind_toggle(ind) for ind in separate_indicators()],
        ], className="d-flex flex-wrap align-items-center mb-1", style={"gap": "6px"}),

        # ── Stores ─────────────────────────────────────────────────────────────
        dcc.Store(id="chart-data"),
        dcc.Store(id="chart-render-dummy"),
        dcc.Store(id="chart-type-dummy"),
        dcc.Store(id="chart-freq-dummy"),
        dcc.Store(id="chart-scale-dummy"),
        dcc.Store(id="chart-ind-dummy"),
        dcc.Store(id="chart-volume-dummy"),

        # ── Contenedor del grafico (alto calculado en JS) ──────────────────────
        dcc.Loading(
            [
                html.Div(id="chart-load-output", style={"display": "none"}),
                html.Div(
                    id="lwc-container",
                    style={
                        "backgroundColor": "#1e1e1e",
                        "padding": "8px",
                        "borderRadius": "4px",
                    },
                ),
            ],
            type="circle",
            color="#dee2e6",
        ),
    ], style={"padding": "0 8px"})


dash.register_page(__name__, path="/chart", title="Grafico tecnico", layout=layout)
