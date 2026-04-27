from datetime import date, timedelta

import dash
import dash_bootstrap_components as dbc
from dash import dcc, html

_th = {"fontSize": "0.74rem", "color": "#9ca3af", "fontWeight": "normal",
       "padding": "4px 8px", "borderBottom": "1px solid #374151"}
_td = {"fontSize": "0.80rem", "padding": "4px 8px", "borderBottom": "1px solid #1f2937"}


def layout(**kwargs):
    from flask_login import current_user
    if not current_user.is_authenticated:
        return html.Div()

    today    = date.today()
    one_year = today - timedelta(days=365)

    return html.Div([
        dcc.Location(id="sh-url", refresh=False),

        dbc.Row([
            dbc.Col(html.H4("Historial de Señales", className="mb-0"), width="auto"),
        ], className="mb-3 align-items-center"),

        # ── Filtros ──────────────────────────────────────────────────────────
        dbc.Card(dbc.CardBody([
            dbc.Row([
                dbc.Col([
                    dbc.Label("Activo", style={"fontSize": "0.82rem"}),
                    dcc.Dropdown(id="sh-asset-sel",
                                 placeholder="Buscar activo...",
                                 searchable=True,
                                 style={"fontSize": "0.85rem"}),
                ], md=4),
                dbc.Col([
                    dbc.Label("Estrategia", style={"fontSize": "0.82rem"}),
                    dcc.Dropdown(id="sh-strategy-sel",
                                 placeholder="Todas las señales",
                                 style={"fontSize": "0.85rem"}),
                ], md=3),
                dbc.Col([
                    dbc.Label("Desde", style={"fontSize": "0.82rem"}),
                    dcc.DatePickerSingle(id="sh-date-from",
                                        date=str(one_year),
                                        display_format="YYYY-MM-DD",
                                        style={"fontSize": "0.82rem"}),
                ], md=2, className="d-flex flex-column"),
                dbc.Col([
                    dbc.Label("Hasta", style={"fontSize": "0.82rem"}),
                    dcc.DatePickerSingle(id="sh-date-to",
                                        date=str(today),
                                        display_format="YYYY-MM-DD",
                                        style={"fontSize": "0.82rem"}),
                ], md=2, className="d-flex flex-column"),
                dbc.Col([
                    dbc.Label(" ", style={"fontSize": "0.82rem"}),
                    dbc.Button("Ver", id="sh-btn-view", color="primary",
                               size="sm", style={"display": "block"}),
                ], md=1, className="d-flex flex-column"),
            ], className="g-2"),
        ]), className="mb-3",
            style={"backgroundColor": "#1f2937", "border": "1px solid #374151"}),

        dcc.Loading(
            html.Div(id="sh-chart-container"),
            type="circle", color="#dee2e6",
        ),

        html.Div(id="sh-table-container", className="mt-3"),

    ], style={"padding": "0 8px"})


dash.register_page(__name__, path="/historial-senales",
                   title="Historial de Señales", layout=layout)
