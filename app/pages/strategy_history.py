from datetime import date, timedelta

import dash
import dash_bootstrap_components as dbc
from dash import dcc, html


def layout(**kwargs):
    from flask_login import current_user
    if not current_user.is_authenticated:
        return html.Div()

    today    = date.today()
    one_year = today - timedelta(days=365)

    return html.Div([
        dcc.Location(id="sth-url", refresh=False),

        dbc.Row([
            dbc.Col(html.H4("Evolución de Estrategia", className="mb-0"), width="auto"),
        ], className="mb-3 align-items-center"),

        dbc.Card(dbc.CardBody([
            dbc.Row([
                dbc.Col([
                    dbc.Label("Estrategia", style={"fontSize": "0.82rem"}),
                    dcc.Dropdown(id="sth-strategy-sel",
                                 placeholder="Seleccionar estrategia...",
                                 style={"fontSize": "0.85rem"}),
                ], md=3),
                dbc.Col([
                    dbc.Label("Desde", style={"fontSize": "0.82rem"}),
                    dcc.DatePickerSingle(id="sth-date-from",
                                        date=str(one_year),
                                        display_format="YYYY-MM-DD",
                                        style={"fontSize": "0.82rem"}),
                ], md=2, className="d-flex flex-column"),
                dbc.Col([
                    dbc.Label("Hasta", style={"fontSize": "0.82rem"}),
                    dcc.DatePickerSingle(id="sth-date-to",
                                        date=str(today),
                                        display_format="YYYY-MM-DD",
                                        style={"fontSize": "0.82rem"}),
                ], md=2, className="d-flex flex-column"),
                dbc.Col([
                    dbc.Label("Ver por", style={"fontSize": "0.82rem"}),
                    dcc.Dropdown(id="sth-mode",
                                 options=[
                                     {"label": "Score",  "value": "score"},
                                     {"label": "Rank",   "value": "rank"},
                                 ],
                                 value="score", clearable=False,
                                 style={"fontSize": "0.83rem"}),
                ], md=2),
                dbc.Col([
                    dbc.Label(" ", style={"fontSize": "0.82rem"}),
                    dbc.Button("Cargar activos", id="sth-btn-load", color="secondary",
                               size="sm", style={"display": "block"}),
                ], md=2, className="d-flex flex-column"),
            ], className="g-2 mb-2"),

            # Selector de activos (se puebla tras "Cargar activos")
            html.Div(id="sth-asset-picker-row", style={"display": "none"}, children=[
                dbc.Row([
                    dbc.Col([
                        dbc.Label("Activos a mostrar", style={"fontSize": "0.80rem"}),
                        dcc.Dropdown(
                            id="sth-asset-sel",
                            options=[],
                            value=[],
                            multi=True,
                            placeholder="Seleccioná activos...",
                            style={"fontSize": "0.83rem"},
                        ),
                    ], md=10),
                    dbc.Col([
                        dbc.Label(" ", style={"fontSize": "0.82rem"}),
                        dbc.Button("Ver", id="sth-btn-view", color="primary",
                                   size="sm", style={"display": "block"}),
                    ], md=2, className="d-flex flex-column"),
                ], className="g-2"),
            ]),
        ]), className="mb-3",
            style={"backgroundColor": "#1f2937", "border": "1px solid #374151"}),

        dcc.Loading(
            html.Div(id="sth-chart-container"),
            type="circle", color="#dee2e6",
        ),

    ], style={"padding": "0 8px"})


dash.register_page(__name__, path="/evolucion-estrategia",
                   title="Evolución de Estrategia", layout=layout)
