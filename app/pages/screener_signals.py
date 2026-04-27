import dash
import dash_bootstrap_components as dbc
from dash import dcc, html

_th = {"fontSize": "0.74rem", "color": "#9ca3af", "fontWeight": "normal",
       "padding": "4px 8px", "borderBottom": "1px solid #374151",
       "whiteSpace": "nowrap"}
_td = {"fontSize": "0.80rem", "padding": "4px 8px", "borderBottom": "1px solid #1f2937"}


def layout(**kwargs):
    from flask_login import current_user
    if not current_user.is_authenticated:
        return html.Div()

    return html.Div([
        dcc.Store(id="ss-comp-meta", data=[]),

        dbc.Row([
            dbc.Col(html.H4("Screener de Señales", className="mb-0"), width="auto"),
        ], className="mb-3 align-items-center"),

        # ── Filtros ──────────────────────────────────────────────────────────
        dbc.Card(dbc.CardBody([
            dbc.Row([
                dbc.Col([
                    dbc.Label("Estrategia", style={"fontSize": "0.82rem"}),
                    dcc.Dropdown(id="ss-strategy-sel",
                                 placeholder="Seleccionar estrategia...",
                                 style={"fontSize": "0.85rem"}),
                ], md=4),
                dbc.Col([
                    dbc.Label("Fecha", style={"fontSize": "0.82rem"}),
                    dcc.DatePickerSingle(id="ss-date",
                                        display_format="YYYY-MM-DD",
                                        style={"fontSize": "0.82rem"}),
                ], md=2, className="d-flex flex-column"),
                dbc.Col([
                    dbc.Label("Sector", style={"fontSize": "0.82rem"}),
                    dcc.Dropdown(id="ss-sector-filter", placeholder="Todos",
                                 style={"fontSize": "0.85rem"}),
                ], md=2),
                dbc.Col([
                    dbc.Label("Mercado", style={"fontSize": "0.82rem"}),
                    dcc.Dropdown(id="ss-market-filter", placeholder="Todos",
                                 style={"fontSize": "0.85rem"}),
                ], md=2),
                dbc.Col([
                    dbc.Label(" ", style={"fontSize": "0.82rem"}),
                    dbc.Button("Buscar", id="ss-btn-search", color="primary",
                               size="sm", style={"display": "block"}),
                ], md=1, className="d-flex flex-column"),
                dbc.Col([
                    dbc.Label(" ", style={"fontSize": "0.82rem"}),
                    dcc.Loading(
                        html.Div(id="ss-result-count",
                                 style={"fontSize": "0.80rem", "color": "#94a3b8",
                                        "paddingTop": "6px"}),
                        type="circle", color="#dee2e6",
                    ),
                ], md=1),
            ], className="g-2"),
        ]), className="mb-3",
            style={"backgroundColor": "#1f2937", "border": "1px solid #374151"}),

        html.Div(id="ss-table-container", style={"overflowX": "auto"}),

    ], style={"padding": "0 8px"})


dash.register_page(__name__, path="/senales",
                   title="Screener de Señales", layout=layout)
