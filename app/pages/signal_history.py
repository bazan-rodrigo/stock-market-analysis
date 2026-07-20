from datetime import date, timedelta

import dash
import dash_bootstrap_components as dbc
from dash import dcc, html

from app.components.help import help_link

from app.components.ui_constants import TH as _th, TD as _td, CARD_STYLE


def layout(**kwargs):
    from flask_login import current_user
    if not current_user.is_authenticated:
        return html.Div()

    today    = date.today()
    one_year = today - timedelta(days=365)

    return html.Div([
        dcc.Location(id="sh-url", refresh=False),
        dcc.Store(id="sh-available-signals", data=[]),

        dbc.Row([
            dbc.Col(html.H4(["Historial de Señales ", help_link("historial-de-senales")], className="mb-0"), width="auto"),
        ], className="mb-3 align-items-center"),

        # ── Filtros ──────────────────────────────────────────────────────────
        dbc.Card(dbc.CardBody([
            # Fila 1: activo, estrategia, fechas, botón
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
            ], className="g-2 mb-2"),

            # Fila 2: selector multi de señales (se muestra tras primer "Ver")
            html.Div(id="sh-signal-picker-row", style={"display": "none"}, children=[
                dbc.Row([
                    dbc.Col([
                        dbc.Label("Señales a mostrar", style={"fontSize": "0.82rem"}),
                        dcc.Dropdown(
                            id="sh-signal-sel",
                            options=[],
                            value=[],
                            multi=True,
                            placeholder="Seleccioná señales...",
                            style={"fontSize": "0.83rem"},
                        ),
                    ]),
                ], className="g-2"),
            ]),
        ]), className="mb-3",
            style=CARD_STYLE),

        dcc.Loading(
            html.Div(id="sh-chart-container"),
            type="circle", color="#dee2e6",
        ),

        html.Div(id="sh-table-container", className="mt-3"),

    ], style={"padding": "0 8px"})


dash.register_page(__name__, path="/historial-senales",
                   title="Historial de Señales", layout=layout)
