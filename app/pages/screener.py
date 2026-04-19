import dash
import dash_bootstrap_components as dbc
from dash import dash_table, dcc, html
from app.components.table_styles import HEADER, DATA, CELL

_DD_SM = {"fontSize": "0.78rem"}

# ── Columnas base ─────────────────────────────────────────────────────────────
_COLUMNS = [
    {"name": "Ticker",       "id": "ticker",     "presentation": "markdown"},
    {"name": "Nombre",       "id": "name"},
    {"name": "Rég. D",       "id": "regime_d"},
    {"name": "Rég. S",       "id": "regime_w"},
    {"name": "Rég. M",       "id": "regime_m"},
    {"name": "Vol. D",       "id": "vol_d"},
    {"name": "Vol. S",       "id": "vol_w"},
    {"name": "Vol. M",       "id": "vol_m"},
    {"name": "RSI D",        "id": "rsi",        "type": "numeric", "format": {"specifier": ".0f"}},
    {"name": "RSI S",        "id": "rsi_w",      "type": "numeric", "format": {"specifier": ".0f"}},
    {"name": "RSI M",        "id": "rsi_m",      "type": "numeric", "format": {"specifier": ".0f"}},
    {"name": "σ SMA D",      "id": "dist_sma_d", "type": "numeric", "format": {"specifier": ".2f"}},
    {"name": "σ SMA S",      "id": "dist_sma_w", "type": "numeric", "format": {"specifier": ".2f"}},
    {"name": "σ SMA M",      "id": "dist_sma_m", "type": "numeric", "format": {"specifier": ".2f"}},
    {"name": "DD %",         "id": "dd_current", "type": "numeric", "format": {"specifier": ".1f"}},
    {"name": "DD Hist.",     "id": "dd_top3"},
    # Scores de grupo por dimensión y timeframe
    {"name": "Sec D",  "id": "gs_sector_d",   "type": "numeric", "format": {"specifier": ".0f"}},
    {"name": "Sec S",  "id": "gs_sector_w",   "type": "numeric", "format": {"specifier": ".0f"}},
    {"name": "Sec M",  "id": "gs_sector_m",   "type": "numeric", "format": {"specifier": ".0f"}},
    {"name": "Ind D",  "id": "gs_industry_d", "type": "numeric", "format": {"specifier": ".0f"}},
    {"name": "Ind S",  "id": "gs_industry_w", "type": "numeric", "format": {"specifier": ".0f"}},
    {"name": "Ind M",  "id": "gs_industry_m", "type": "numeric", "format": {"specifier": ".0f"}},
    {"name": "País D", "id": "gs_country_d",  "type": "numeric", "format": {"specifier": ".0f"}},
    {"name": "País S", "id": "gs_country_w",  "type": "numeric", "format": {"specifier": ".0f"}},
    {"name": "País M", "id": "gs_country_m",  "type": "numeric", "format": {"specifier": ".0f"}},
    {"name": "Tipo D", "id": "gs_itype_d",    "type": "numeric", "format": {"specifier": ".0f"}},
    {"name": "Tipo S", "id": "gs_itype_w",    "type": "numeric", "format": {"specifier": ".0f"}},
    {"name": "Tipo M", "id": "gs_itype_m",    "type": "numeric", "format": {"specifier": ".0f"}},
    {"name": "Mdo D",  "id": "gs_market_d",   "type": "numeric", "format": {"specifier": ".0f"}},
    {"name": "Mdo S",  "id": "gs_market_w",   "type": "numeric", "format": {"specifier": ".0f"}},
    {"name": "Mdo M",  "id": "gs_market_m",   "type": "numeric", "format": {"specifier": ".0f"}},
]

_REGIME_COLS = ["regime_d", "regime_w", "regime_m"]
_VOL_COLS    = ["vol_d",    "vol_w",    "vol_m"]
_GS_COLS     = [c["id"] for c in _COLUMNS if c["id"].startswith("gs_")]

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

_VOL_COLORS = {
    "Extrema | Larga":  "#b71c1c", "Extrema | Media":  "#c62828", "Extrema | Corta":  "#d32f2f",
    "Alta | Larga":     "#e65100", "Alta | Media":     "#ef6c00", "Alta | Corta":     "#f57c00",
    "Normal | Larga":   "#546e7a", "Normal | Media":   "#607d8b", "Normal | Corta":   "#78909c",
    "Baja | Larga":     "#0277bd", "Baja | Media":     "#0288d1", "Baja | Corta":     "#039be5",
}

# Reglas de color para los group-score columns (positivo → verde, negativo → rojo)
_GS_STYLE = [cond
    for col in _GS_COLS
    for cond in [
        {"if": {"filter_query": f"{{{col}}} > 20",  "column_id": col}, "color": "#a5d6a7"},
        {"if": {"filter_query": f"{{{col}}} < -20", "column_id": col}, "color": "#ef9a9a"},
        {"if": {"filter_query": f"{{{col}}} >= 50", "column_id": col}, "color": "#4caf50"},
        {"if": {"filter_query": f"{{{col}}} <= -50","column_id": col}, "color": "#ef5350"},
    ]
]

# Ancho compacto para columnas de score de grupo
_GS_CELL = [{"if": {"column_id": c}, "width": "42px", "minWidth": "36px", "maxWidth": "48px",
              "fontSize": "0.7rem"} for c in _GS_COLS]


def layout(**kwargs):
    from flask_login import current_user
    if not current_user.is_authenticated:
        return html.Div()

    return html.Div([
        # ── Barra de filtros ──────────────────────────────────────────────────
        dbc.Row([
            dbc.Col(dcc.Dropdown(id="scr-filter-country",  multi=True, placeholder="País",      style=_DD_SM),
                    style={"minWidth": "120px", "maxWidth": "180px"}),
            dbc.Col(dcc.Dropdown(id="scr-filter-market",   multi=True, placeholder="Mercado",   style=_DD_SM),
                    style={"minWidth": "120px", "maxWidth": "180px"}),
            dbc.Col(dcc.Dropdown(id="scr-filter-itype",    multi=True, placeholder="Tipo",      style=_DD_SM),
                    style={"minWidth": "100px", "maxWidth": "160px"}),
            dbc.Col(dcc.Dropdown(id="scr-filter-sector",   multi=True, placeholder="Sector",    style=_DD_SM),
                    style={"minWidth": "120px", "maxWidth": "180px"}),
            dbc.Col(dcc.Dropdown(id="scr-filter-industry", multi=True, placeholder="Industria", style=_DD_SM),
                    style={"minWidth": "120px", "maxWidth": "180px"}),
            dbc.Col(dbc.Button("Recalcular snapshots", id="scr-btn-recompute",
                               color="secondary", size="sm"), width="auto"),
            dbc.Col(html.Small(id="scr-recompute-status", className="text-muted"),
                    width="auto", className="d-flex align-items-center"),
            dbc.Col(html.Small(id="scr-result-count", className="text-muted"),
                    width="auto", className="d-flex align-items-center ms-auto"),
        ], className="mb-2 g-2 align-items-center flex-wrap"),

        dcc.Interval(id="scr-interval", interval=800, disabled=True, n_intervals=0),
        dbc.Progress(id="scr-progress", value=0, striped=True, animated=True,
                     label="", className="mb-2", style={"display": "none"}),

        # ── Tabla ─────────────────────────────────────────────────────────────
        dash_table.DataTable(
            id="scr-table",
            columns=_COLUMNS,
            data=[],
            sort_action="native",
            filter_action="native",
            page_size=100,
            tooltip_delay=0,
            tooltip_duration=None,
            tooltip_header={
                "dist_sma_d": {"value": "Distancia en desvíos estándar (σ) entre el precio y la SMA que ese activo respeta más en el timeframe diario. ±1σ es normal, ±2σ es inusual, ±3σ es extremo.", "type": "text"},
                "dist_sma_w": {"value": "Distancia en desvíos estándar (σ) entre el precio y la SMA que ese activo respeta más en el timeframe semanal. ±1σ es normal, ±2σ es inusual, ±3σ es extremo.", "type": "text"},
                "dist_sma_m": {"value": "Distancia en desvíos estándar (σ) entre el precio y la SMA que ese activo respeta más en el timeframe mensual. ±1σ es normal, ±2σ es inusual, ±3σ es extremo.", "type": "text"},
            },
            style_table={"overflowX": "auto"},
            style_header=HEADER,
            style_data=DATA,
            style_cell={**CELL, "textAlign": "center", "fontSize": "0.78rem",
                        "padding": "3px 5px"},
            style_cell_conditional=[
                {"if": {"column_id": "ticker"},
                 "textAlign": "left", "width": "55px", "minWidth": "50px", "maxWidth": "65px"},
                {"if": {"column_id": "name"},
                 "textAlign": "left", "width": "110px", "minWidth": "80px", "maxWidth": "130px",
                 "overflow": "hidden", "textOverflow": "ellipsis", "whiteSpace": "nowrap"},
                *_GS_CELL,
            ],
            style_data_conditional=(
                [{"if": {"filter_query": "{dd_current} < 0", "column_id": "dd_current"},
                  "color": "#ef5350"}]
                + [{"if": {"filter_query": f"{{{c}}} > 0", "column_id": c}, "color": "#4caf50"}
                   for c in ["dist_sma_d", "dist_sma_w", "dist_sma_m"]]
                + [{"if": {"filter_query": f"{{{c}}} < 0", "column_id": c}, "color": "#ef5350"}
                   for c in ["dist_sma_d", "dist_sma_w", "dist_sma_m"]]
                + [{"if": {"filter_query": f"{{{c}}} >= 70", "column_id": c}, "color": "#ef5350"}
                   for c in ["rsi", "rsi_w", "rsi_m"]]
                + [{"if": {"filter_query": f"{{{c}}} <= 30", "column_id": c}, "color": "#4caf50"}
                   for c in ["rsi", "rsi_w", "rsi_m"]]
                + [{"if": {"filter_query": f'{{{c}}} = "{label}"', "column_id": c},
                    "color": color, "fontWeight": "bold"}
                   for label, color in _REGIME_COLORS.items() for c in _REGIME_COLS]
                + [{"if": {"filter_query": f'{{{c}}} = "{label}"', "column_id": c},
                    "color": color, "fontWeight": "bold"}
                   for label, color in _VOL_COLORS.items() for c in _VOL_COLS]
                + _GS_STYLE
            ),
        ),
    ])


dash.register_page(__name__, path="/screener", title="Screener", layout=layout)
