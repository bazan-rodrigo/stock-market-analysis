import dash
import dash_bootstrap_components as dbc
from dash import dcc, html

_TOP_N_OPTS = [
    {"label": "Top 20",  "value": 20},
    {"label": "Top 50",  "value": 50},
    {"label": "Top 100", "value": 100},
    {"label": "Todos",   "value": 0},
]


def layout(**kwargs):
    from flask_login import current_user
    if not current_user.is_authenticated:
        return html.Div()

    return html.Div([
        dbc.Row([
            dbc.Col(html.H4("Mapa de Calor de Señales", className="mb-0"), width="auto"),
        ], className="mb-3 align-items-center"),

        dbc.Card(dbc.CardBody([
            dbc.Row([
                dbc.Col([
                    dbc.Label("Estrategia", style={"fontSize": "0.82rem"}),
                    dcc.Dropdown(id="hm-strategy-sel",
                                 placeholder="Seleccionar estrategia...",
                                 style={"fontSize": "0.85rem"}),
                ], md=3),
                dbc.Col([
                    dbc.Label("Fecha", style={"fontSize": "0.82rem"}),
                    dcc.DatePickerSingle(id="hm-date",
                                        display_format="YYYY-MM-DD",
                                        style={"fontSize": "0.82rem"}),
                ], md=2, className="d-flex flex-column"),
                dbc.Col([
                    dbc.Label("Sector", style={"fontSize": "0.82rem"}),
                    dcc.Dropdown(id="hm-sector-filter", placeholder="Todos",
                                 style={"fontSize": "0.85rem"}),
                ], md=2),
                dbc.Col([
                    dbc.Label("Mercado", style={"fontSize": "0.82rem"}),
                    dcc.Dropdown(id="hm-market-filter", placeholder="Todos",
                                 style={"fontSize": "0.85rem"}),
                ], md=2),
                dbc.Col([
                    dbc.Label("Mostrar", style={"fontSize": "0.82rem"}),
                    dcc.Dropdown(id="hm-top-n", options=_TOP_N_OPTS, value=50,
                                 clearable=False, style={"fontSize": "0.83rem"}),
                ], md=1),
                dbc.Col([
                    dbc.Label(" ", style={"fontSize": "0.82rem"}),
                    dbc.Button("Ver", id="hm-btn-view", color="primary",
                               size="sm", style={"display": "block"}),
                ], md=1, className="d-flex flex-column"),
                dbc.Col([
                    dbc.Label(" ", style={"fontSize": "0.82rem"}),
                    dcc.Loading(
                        html.Div(id="hm-result-count",
                                 style={"fontSize": "0.80rem", "color": "#94a3b8",
                                        "paddingTop": "6px"}),
                        type="circle", color="#dee2e6",
                    ),
                ], md=1),
            ], className="g-2"),
        ]), className="mb-3",
            style={"backgroundColor": "#1f2937", "border": "1px solid #374151"}),

        dcc.Loading(
            html.Div(id="hm-chart-container"),
            type="circle", color="#dee2e6",
        ),

    ], style={"padding": "0 8px"})


dash.register_page(__name__, path="/mapa-senales",
                   title="Mapa de Señales", layout=layout)
