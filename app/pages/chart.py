import dash
import dash_bootstrap_components as dbc
from dash import dcc, html
from app.indicators.registry import overlay_indicators, separate_indicators


def _param_control(ind_id: str, param):
    step = param.step or (1 if param.type == "int" else 0.1)
    return dbc.Row([
        dbc.Col(html.Small(param.label, style={"fontSize": "0.72rem"}), width=6),
        dbc.Col(
            dbc.Input(
                id=f"chart-ind-{ind_id}-{param.name}",
                type="number",
                value=param.default,
                min=param.min_val,
                max=param.max_val,
                step=step,
                size="sm",
                style={"fontSize": "0.72rem", "padding": "1px 4px"},
            ),
            width=6,
        ),
    ], className="mb-1")


def _build_overlay_controls():
    controls = []
    for ind in overlay_indicators():
        ind_id = ind.NAME
        controls.append(
            dbc.Card(dbc.CardBody([
                dbc.Switch(id=f"chart-ind-{ind_id}-enabled", label=ind.LABEL, value=False,
                           style={"fontSize": "0.75rem"}),
                html.Div(
                    [_param_control(ind_id, p) for p in ind.PARAMS],
                    id=f"chart-ind-{ind_id}-params",
                    style={"display": "none"},
                ),
            ], style={"padding": "4px 8px"}), className="mb-1")
        )
    return controls


def _build_separate_controls():
    controls = []
    for ind in separate_indicators():
        ind_id = ind.NAME
        controls.append(
            dbc.Card(dbc.CardBody([
                dbc.Switch(id=f"chart-ind-{ind_id}-enabled", label=ind.LABEL, value=False,
                           style={"fontSize": "0.75rem"}),
                html.Div(
                    [_param_control(ind_id, p) for p in ind.PARAMS],
                    id=f"chart-ind-{ind_id}-params",
                    style={"display": "none"},
                ),
            ], style={"padding": "4px 8px"}), className="mb-1")
        )
    return controls


def layout(**kwargs):
    from flask_login import current_user
    if not current_user.is_authenticated:
        return html.Div()

    _label = {"fontSize": "0.75rem", "fontWeight": "600", "marginBottom": "2px", "marginTop": "6px", "display": "block"}
    _input_sm = {"fontSize": "0.75rem", "padding": "2px 6px", "height": "28px"}
    _hr = {"margin": "6px 0"}

    return dbc.Row([
        dbc.Col(id="chart-controls", style={"fontSize": "0.75rem"}, children=[
            html.Span("Activo", style=_label),
            dbc.Select(id="chart-asset-select", options=[], placeholder="Seleccioná un activo",
                       style=_input_sm),
            html.Span("Período", style=_label),
            dbc.Row([
                dbc.Col(dbc.Input(id="chart-date-from", type="date", value=None,
                                  style=_input_sm), className="pe-1"),
                dbc.Col(dbc.Input(id="chart-date-to", type="date", value=None,
                                  style=_input_sm), className="ps-1"),
            ], className="mb-1 g-0"),
            dbc.Button("Generar gráfico", id="chart-btn-update", color="primary",
                       className="w-100 mb-2", size="sm"),
            html.Span("Tipo de gráfico", style=_label),
            dbc.RadioItems(
                id="chart-type",
                options=[
                    {"label": "Velas japonesas", "value": "candlestick"},
                    {"label": "Línea", "value": "line"},
                ],
                value="candlestick",
                inline=True,
                style={"fontSize": "0.75rem"},
            ),
            html.Span("Escala Y", style={**_label, "marginTop": "4px"}),
            dbc.RadioItems(
                id="chart-yscale",
                options=[
                    {"label": "Aritmética", "value": "linear"},
                    {"label": "Logarítmica", "value": "log"},
                ],
                value="linear",
                inline=True,
                style={"fontSize": "0.75rem"},
            ),
            html.Hr(style=_hr),
            html.Span("Indicadores sobre precio", style=_label),
            *_build_overlay_controls(),
            html.Hr(style=_hr),
            html.Span("Indicadores en paneles separados", style=_label),
            *_build_separate_controls(),
        ], md=3, className="border-end pe-3"),
        dbc.Col([
            dcc.Graph(id="chart-figure", style={"height": "80vh"}),
        ], md=9),
    ], className="g-0")


dash.register_page(__name__, path="/chart", title="Gráfico técnico", layout=layout)
