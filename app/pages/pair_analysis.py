from datetime import date, timedelta

import dash
import dash_bootstrap_components as dbc
from dash import dcc, html

_radio_sm = {"fontSize": "0.80rem"}


def layout(**kwargs):
    from flask_login import current_user
    if not current_user.is_authenticated:
        return html.Div()

    today    = date.today()
    one_year = today - timedelta(days=365)

    return html.Div([
        dcc.Store(id="pair-scatter-data"),

        dbc.Alert(id="pair-alert", is_open=False, dismissable=True,
                  color="warning", className="mb-2"),

        # ── Panel de controles compartido ─────────────────────────────────
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
                    dbc.Button("⇄", id="pair-swap-btn", color="secondary", size="sm",
                               className="mt-3", title="Intercambiar activos",
                               style={"fontSize": "1rem", "lineHeight": 1}),
                ], width="auto", className="d-flex align-items-end pb-1"),
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
                ], width="auto", className="d-flex flex-column justify-content-start"),
                dbc.Col([
                    html.Small(" ", className="d-block mb-1"),
                    dbc.Button("Analizar", id="pair-btn-analizar",
                               color="primary", size="sm", className="w-100"),
                ], width="auto", className="d-flex flex-column justify-content-start"),
            ], className="g-2 align-items-end"),
        ]), className="mb-3"),

        # ── Tabs ─────────────────────────────────────────────────────────
        dbc.Tabs([

            # — Comparación —
            dbc.Tab(
                dcc.Loading(
                    dcc.Graph(id="pair-graph-comp", style={"height": "520px"},
                              config={"scrollZoom": True,
                                      "modeBarButtonsToRemove": ["lasso2d", "select2d"]}),
                    type="circle", color="#dee2e6",
                ),
                label="Comparación", tab_id="tab-comp",
            ),

            # — Ratio —
            dbc.Tab(
                dcc.Loading(
                    dcc.Graph(id="pair-graph-ratio", style={"height": "520px"},
                              config={"scrollZoom": True,
                                      "modeBarButtonsToRemove": ["lasso2d", "select2d"]}),
                    type="circle", color="#dee2e6",
                ),
                label="Ratio", tab_id="tab-ratio",
            ),

            # — Correlación (ex-scatter) —
            dbc.Tab([
                dbc.Row([
                    dbc.Col([
                        html.Small("Línea de tendencia", className="text-muted d-block mb-1"),
                        dbc.RadioItems(
                            id="pair-trend-type",
                            options=[
                                {"label": "Ninguna",     "value": "none"},
                                {"label": "Lineal",      "value": "linear"},
                                {"label": "Logarítmica", "value": "log"},
                                {"label": "Polinómica",  "value": "poly"},
                                {"label": "Exponencial", "value": "exp"},
                            ],
                            value="none",
                            inline=True,
                            inputStyle={"marginRight": "3px"},
                            labelStyle={"marginRight": "12px", "cursor": "pointer"},
                            style=_radio_sm,
                        ),
                    ], md=5),
                    dbc.Col([
                        html.Small("Grado", className="text-muted d-block mb-1"),
                        dbc.Input(
                            id="pair-poly-degree",
                            type="number", value=2, min=2, max=10, step=1,
                            style={"width": "60px", "fontSize": "0.82rem",
                                   "padding": "2px 6px", "height": "28px"},
                        ),
                    ], id="pair-poly-degree-col", width="auto",
                       style={"display": "none"}),
                    dbc.Col([
                        html.Small("Opciones", className="text-muted d-block mb-1"),
                        dbc.Checklist(
                            id="pair-show-events",
                            options=[{"label": " Eventos de mercado", "value": "events"}],
                            value=[],
                            inline=True,
                            style={"fontSize": "0.85rem"},
                        ),
                    ], width="auto"),
                    dbc.Col([
                        html.Small("Escala logarítmica", className="text-muted d-block mb-1"),
                        dbc.Switch(id="pair-log-axes", value=False, label="Ambos ejes",
                                   style={"fontSize": "0.82rem", "marginBottom": 0}),
                    ], width="auto", className="d-flex flex-column justify-content-start"),
                ], className="g-2 align-items-end mt-2 mb-3"),

                dcc.Loading(
                    dcc.Graph(
                        id="pair-graph-corr",
                        style={"height": "520px"},
                        config={"scrollZoom": True,
                                "modeBarButtonsToRemove": ["lasso2d", "select2d"]},
                    ),
                    type="circle", color="#dee2e6",
                ),
                html.Div(id="pair-scatter-stats", className="mt-2 text-muted",
                         style={"fontSize": "0.78rem"}),
            ], label="Correlación", tab_id="tab-corr"),

        ], id="pair-tabs", active_tab="tab-comp", className="mb-2"),

    ], style={"padding": "0 8px"})


dash.register_page(__name__, path="/par", title="Análisis de Pares", layout=layout)
