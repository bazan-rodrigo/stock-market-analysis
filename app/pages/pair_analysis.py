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
        dbc.Alert(id="pair-alert", is_open=False, dismissable=True,
                  color="warning", className="mb-2"),

        # ── Panel de controles ────────────────────────────────────────────
        dbc.Card(dbc.CardBody([
            dbc.Row([
                dbc.Col([
                    html.Small("Activo 1", className="text-muted d-block mb-1"),
                    dcc.Dropdown(
                        id="pair-asset1",
                        placeholder="Buscar activo...",
                        style={"fontSize": "0.85rem"},
                    ),
                ], md=3),
                dbc.Col([
                    html.Small("Activo 2", className="text-muted d-block mb-1"),
                    dcc.Dropdown(
                        id="pair-asset2",
                        placeholder="Buscar activo...",
                        style={"fontSize": "0.85rem"},
                    ),
                ], md=3),
                dbc.Col([
                    html.Small("Fecha desde", className="text-muted d-block mb-1"),
                    dcc.DatePickerSingle(
                        id="pair-date-from", date=one_year.isoformat(),
                        display_format="YYYY-MM-DD", style={"fontSize": "0.85rem"},
                    ),
                ], md=2),
                dbc.Col([
                    html.Small("Fecha hasta", className="text-muted d-block mb-1"),
                    dcc.DatePickerSingle(
                        id="pair-date-to", date=today.isoformat(),
                        display_format="YYYY-MM-DD", style={"fontSize": "0.85rem"},
                    ),
                ], md=2),
                dbc.Col([
                    html.Small("Escala", className="text-muted d-block mb-1"),
                    dbc.Switch(id="pair-log-scale", value=False, label="Logarítmica"),
                ], md=1, className="d-flex flex-column justify-content-start"),
                dbc.Col([
                    html.Small(" ", className="d-block mb-1"),
                    dbc.Button("Analizar", id="pair-btn-analizar",
                               color="primary", size="sm", className="w-100"),
                ], md=1, className="d-flex flex-column justify-content-start"),
            ], className="g-2 align-items-end"),
        ]), className="mb-3"),

        # ── Tabs con los tres gráficos ────────────────────────────────────
        dbc.Tabs([
            dbc.Tab(
                dcc.Loading(
                    dcc.Graph(id="pair-graph-comp", style={"height": "520px"},
                              config={"scrollZoom": True,
                                      "modeBarButtonsToRemove": ["lasso2d", "select2d"]}),
                    type="circle", color="#dee2e6",
                ),
                label="Comparación", tab_id="tab-comp",
            ),
            dbc.Tab(
                dcc.Loading(
                    dcc.Graph(id="pair-graph-ratio", style={"height": "520px"},
                              config={"scrollZoom": True,
                                      "modeBarButtonsToRemove": ["lasso2d", "select2d"]}),
                    type="circle", color="#dee2e6",
                ),
                label="Ratio", tab_id="tab-ratio",
            ),
            dbc.Tab(
                dcc.Loading(
                    dcc.Graph(id="pair-graph-scatter", style={"height": "520px"},
                              config={"scrollZoom": True,
                                      "modeBarButtonsToRemove": ["lasso2d", "select2d"]}),
                    type="circle", color="#dee2e6",
                ),
                label="Dispersión", tab_id="tab-scatter",
            ),
        ], id="pair-tabs", active_tab="tab-comp", className="mb-2"),

    ], style={"padding": "0 8px"})


dash.register_page(__name__, path="/par", title="Análisis de Pares", layout=layout)
