import dash
import dash_bootstrap_components as dbc
from dash import dcc, html

_th = {"fontSize": "0.74rem", "color": "#9ca3af", "fontWeight": "normal",
       "padding": "4px 8px", "borderBottom": "1px solid #374151",
       "whiteSpace": "nowrap"}
_td = {"fontSize": "0.80rem", "padding": "4px 8px", "borderBottom": "1px solid #1f2937"}

_SORT_OPTS = [
    {"label": "Rank ↑",       "value": "rank"},
    {"label": "Score ↓",      "value": "score"},
    {"label": "Δ Score ↓",    "value": "delta_score"},
    {"label": "Δ Rank ↑",     "value": "delta_rank"},
    {"label": "Ticker A-Z",   "value": "ticker"},
]


def layout(**kwargs):
    from flask_login import current_user
    if not current_user.is_authenticated:
        return html.Div()

    return html.Div([
        dcc.Store(id="ss-comp-meta",    data=[]),
        dcc.Store(id="ss-results-store", data=None),
        dcc.Download(id="ss-download"),

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
            ], className="g-2 mb-2"),

            # ── Segunda fila: ordenar + exportar ─────────────────────────────
            dbc.Row([
                dbc.Col([
                    dbc.Label("Ordenar por", style={"fontSize": "0.80rem"}),
                    dcc.Dropdown(id="ss-sort-col", options=_SORT_OPTS,
                                 value="rank", clearable=False,
                                 style={"fontSize": "0.83rem"}),
                ], md=3),
                dbc.Col([
                    dbc.Label(" ", style={"fontSize": "0.82rem"}),
                    dbc.Button("Exportar Excel", id="ss-btn-export", color="secondary",
                               size="sm", outline=True, disabled=True,
                               style={"display": "block"}),
                ], md=2, className="d-flex flex-column"),
            ], className="g-2"),
        ]), className="mb-3",
            style={"backgroundColor": "#1f2937", "border": "1px solid #374151"}),

        html.Div(id="ss-table-container", style={"overflowX": "auto"}),

    ], style={"padding": "0 8px"})


dash.register_page(__name__, path="/senales",
                   title="Screener de Señales", layout=layout)
