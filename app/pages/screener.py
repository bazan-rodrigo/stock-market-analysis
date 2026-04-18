import dash
import dash_bootstrap_components as dbc
from dash import dash_table, dcc, html
from app.components.table_styles import HEADER, DATA, CELL

_DD_SM = {"fontSize": "0.78rem"}

_COLUMNS = [
    {"name": "Ticker",        "id": "ticker",     "presentation": "markdown"},
    {"name": "Nombre",        "id": "name"},
    {"name": "Rég. D",        "id": "regime_d"},
    {"name": "Rég. S",        "id": "regime_w"},
    {"name": "Rég. M",        "id": "regime_m"},
    {"name": "RSI S",         "id": "rsi_w",      "type": "numeric", "format": {"specifier": ".1f"}},
    {"name": "σ SMA D",       "id": "dist_sma_d", "type": "numeric", "format": {"specifier": ".2f"}},
    {"name": "σ SMA S",       "id": "dist_sma_w", "type": "numeric", "format": {"specifier": ".2f"}},
    {"name": "σ SMA M",       "id": "dist_sma_m", "type": "numeric", "format": {"specifier": ".2f"}},
    {"name": "DD Actual %",   "id": "dd_current", "type": "numeric", "format": {"specifier": ".1f"}},
    {"name": "DD Hist. Máx",  "id": "dd_top3"},
]

_VAR_COLS = []
_REGIME_COLS = ["regime_d", "regime_w", "regime_m"]
_REGIME_MAP = {
    "bullish_nascent_strong": "Alcista naciente fuerte",
    "bullish_nascent":        "Alcista naciente",
    "bullish_strong":         "Alcista fuerte",
    "bullish":                "Alcista",
    "lateral_nascent":        "Lateral naciente",
    "lateral":                "Lateral",
    "bearish_nascent_strong": "Bajista naciente fuerte",
    "bearish_nascent":        "Bajista naciente",
    "bearish_strong":         "Bajista fuerte",
    "bearish":                "Bajista",
}
_REGIME_COLORS = {
    "Alcista naciente fuerte": "#66bb6a",
    "Alcista naciente":        "#a5d6a7",
    "Alcista fuerte":          "#2e7d32",
    "Alcista":                 "#4caf50",
    "Lateral naciente":        "#90caf9",
    "Lateral":                 "#6495ed",
    "Bajista naciente fuerte": "#ef5350",
    "Bajista naciente":        "#ef9a9a",
    "Bajista fuerte":          "#b71c1c",
    "Bajista":                 "#ef5350",
}


def layout(**kwargs):
    from flask_login import current_user
    if not current_user.is_authenticated:
        return html.Div()

    return html.Div([
        # ── Barra de filtros ───────────────────────────────────────────────────
        dbc.Row([
            dbc.Col(
                dcc.Dropdown(id="scr-filter-country",  multi=True,
                             placeholder="País", style=_DD_SM),
                style={"minWidth": "130px", "maxWidth": "200px"},
            ),
            dbc.Col(
                dcc.Dropdown(id="scr-filter-market",   multi=True,
                             placeholder="Mercado", style=_DD_SM),
                style={"minWidth": "130px", "maxWidth": "200px"},
            ),
            dbc.Col(
                dcc.Dropdown(id="scr-filter-itype",    multi=True,
                             placeholder="Tipo", style=_DD_SM),
                style={"minWidth": "120px", "maxWidth": "180px"},
            ),
            dbc.Col(
                dcc.Dropdown(id="scr-filter-sector",   multi=True,
                             placeholder="Sector", style=_DD_SM),
                style={"minWidth": "130px", "maxWidth": "200px"},
            ),
            dbc.Col(
                dcc.Dropdown(id="scr-filter-industry", multi=True,
                             placeholder="Industria", style=_DD_SM),
                style={"minWidth": "130px", "maxWidth": "200px"},
            ),
            dbc.Col(
                dbc.Button("Recalcular snapshots", id="scr-btn-recompute",
                           color="secondary", size="sm", disabled=False),
                width="auto",
            ),
            dbc.Col(
                html.Small(id="scr-recompute-status", className="text-muted"),
                width="auto", className="d-flex align-items-center",
            ),
            dbc.Col(
                html.Small(id="scr-result-count", className="text-muted"),
                width="auto", className="d-flex align-items-center ms-auto",
            ),
        ], className="mb-2 g-2 align-items-center flex-wrap"),

        dcc.Interval(id="scr-interval", interval=800, disabled=True, n_intervals=0),
        dbc.Progress(id="scr-progress", value=0, striped=True, animated=True,
                     label="", className="mb-2", style={"display": "none"}),

        # ── Tabla ──────────────────────────────────────────────────────────────
        dash_table.DataTable(
            id="scr-table",
            columns=_COLUMNS,
            data=[],
            sort_action="native",
            filter_action="native",
            page_size=100,
            style_table={"overflowX": "auto"},
            style_header=HEADER,
            style_data=DATA,
            style_cell={**CELL, "textAlign": "center"},
            style_cell_conditional=[
                {"if": {"column_id": "ticker"}, "textAlign": "left", "width": "80px", "minWidth": "80px", "maxWidth": "80px"},
                {"if": {"column_id": "name"},   "textAlign": "left", "width": "150px", "minWidth": "100px", "maxWidth": "180px",
                 "overflow": "hidden", "textOverflow": "ellipsis", "whiteSpace": "nowrap"},
            ],
            style_data_conditional=(
                [{"if": {"filter_query": "{dd_current} < 0",
                          "column_id": "dd_current"}, "color": "#ef5350"}]
                + [{"if": {"filter_query": f"{{{c}}} > 0", "column_id": c},
                    "color": "#4caf50"} for c in ["dist_sma_d", "dist_sma_w", "dist_sma_m"]]
                + [{"if": {"filter_query": f"{{{c}}} < 0", "column_id": c},
                    "color": "#ef5350"} for c in ["dist_sma_d", "dist_sma_w", "dist_sma_m"]]
                + [
                    {"if": {"filter_query": f'{{{c}}} = "{label}"', "column_id": c},
                     "color": color, "fontWeight": "bold"}
                    for label, color in _REGIME_COLORS.items()
                    for c in _REGIME_COLS
                ]
            ),
        ),
    ])


dash.register_page(__name__, path="/screener", title="Screener", layout=layout)
