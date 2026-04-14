import dash
import dash_bootstrap_components as dbc
from dash import dcc, html
from app.indicators.registry import overlay_indicators, separate_indicators


def _param_control(ind_id: str, param):
    step = param.step or (1 if param.type == "int" else 0.1)
    return dbc.Row([
        dbc.Col(html.Small(param.label), width=6),
        dbc.Col(
            dbc.Input(
                id=f"chart-ind-{ind_id}-{param.name}",
                type="number",
                value=param.default,
                min=param.min_val,
                max=param.max_val,
                step=step,
                size="sm",
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
                dbc.Switch(id=f"chart-ind-{ind_id}-enabled", label=ind.LABEL, value=False),
                html.Div(
                    [_param_control(ind_id, p) for p in ind.PARAMS],
                    id=f"chart-ind-{ind_id}-params",
                    style={"display": "none"},
                ),
            ]), className="mb-2 p-1")
        )
    return controls


def _build_separate_controls():
    controls = []
    for ind in separate_indicators():
        ind_id = ind.NAME
        controls.append(
            dbc.Card(dbc.CardBody([
                dbc.Switch(id=f"chart-ind-{ind_id}-enabled", label=ind.LABEL, value=False),
                html.Div(
                    [_param_control(ind_id, p) for p in ind.PARAMS],
                    id=f"chart-ind-{ind_id}-params",
                    style={"display": "none"},
                ),
            ]), className="mb-2 p-1")
        )
    return controls


def layout(**kwargs):
    from flask_login import current_user
    if not current_user.is_authenticated:
        return html.Div()

    return dbc.Row([
        dbc.Col(id="chart-controls", children=[
            html.H6("Activo"),
            dbc.Select(id="chart-asset-select", options=[], placeholder="Seleccioná un activo"),
            html.H6("Período", className="mt-2"),
            dbc.Row([
                dbc.Col(dbc.Input(id="chart-date-from", type="date", value=None, placeholder="Desde")),
                dbc.Col(dbc.Input(id="chart-date-to", type="date", value=None, placeholder="Hasta")),
            ], className="mb-2"),
            dbc.Button("Generar gráfico", id="chart-btn-update", color="primary", className="w-100 mb-3"),
            html.H6("Tipo de gráfico"),
            dbc.RadioItems(
                id="chart-type",
                options=[
                    {"label": "Velas japonesas", "value": "candlestick"},
                    {"label": "Línea", "value": "line"},
                ],
                value="candlestick",
                inline=True,
            ),
            html.H6("Escala Y", className="mt-2"),
            dbc.RadioItems(
                id="chart-yscale",
                options=[
                    {"label": "Aritmética", "value": "linear"},
                    {"label": "Logarítmica", "value": "log"},
                ],
                value="linear",
                inline=True,
            ),
            html.Hr(),
            html.H6("Indicadores sobre precio"),
            *_build_overlay_controls(),
            html.Hr(),
            html.H6("Indicadores en paneles separados"),
            *_build_separate_controls(),
        ], md=3, className="border-end pe-3"),
        dbc.Col([
            dcc.Graph(id="chart-figure", style={"height": "80vh"}),
        ], md=9),
    ], className="g-0")


dash.register_page(__name__, path="/chart", title="Gráfico técnico", layout=layout)
