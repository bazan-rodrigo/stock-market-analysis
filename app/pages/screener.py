import dash
import dash_bootstrap_components as dbc
from dash import dash_table, dcc, html
from app.components.table_styles import HEADER, DATA, CELL

_COLUMNS = [
    {"name": "Ticker", "id": "ticker"},
    {"name": "Nombre", "id": "name"},
    {"name": "Var. día %", "id": "var_daily", "type": "numeric", "format": {"specifier": ".2f"}},
    {"name": "Var. mes %", "id": "var_month", "type": "numeric", "format": {"specifier": ".2f"}},
    {"name": "Var. quarter %", "id": "var_quarter", "type": "numeric", "format": {"specifier": ".2f"}},
    {"name": "Var. año %", "id": "var_year", "type": "numeric", "format": {"specifier": ".2f"}},
    {"name": "Var. 52s %", "id": "var_52w", "type": "numeric", "format": {"specifier": ".2f"}},
    {"name": "RSI", "id": "rsi", "type": "numeric", "format": {"specifier": ".1f"}},
    {"name": "vs SMA20 %", "id": "vs_sma20", "type": "numeric", "format": {"specifier": ".2f"}},
    {"name": "vs SMA50 %", "id": "vs_sma50", "type": "numeric", "format": {"specifier": ".2f"}},
    {"name": "vs SMA200 %", "id": "vs_sma200", "type": "numeric", "format": {"specifier": ".2f"}},
]


def layout(**kwargs):
    from flask_login import current_user
    if not current_user.is_authenticated:
        return html.Div()

    _label = {"fontSize": "0.75rem", "fontWeight": "600", "marginBottom": "2px", "marginTop": "6px", "display": "block"}
    _dd_sm = {"fontSize": "0.75rem"}
    _hr = {"margin": "6px 0"}
    _radio_opts = [
        {"label": "Cualquiera", "value": "any"},
        {"label": "Por encima", "value": "above"},
        {"label": "Por debajo", "value": "below"},
    ]

    return html.Div([
        dcc.Location(id="screener-redirect"),
        dbc.Row([
            dbc.Col(style={"fontSize": "0.75rem"}, children=[
                html.Span("Filtros", style={"fontSize": "0.9rem", "fontWeight": "700", "display": "block", "marginBottom": "6px"}),
                html.Span("País", style=_label),
                dcc.Dropdown(id="scr-filter-country", multi=True, placeholder="Todos", style=_dd_sm),
                html.Span("Mercado", style=_label),
                dcc.Dropdown(id="scr-filter-market", multi=True, placeholder="Todos", style=_dd_sm),
                html.Span("Tipo de instrumento", style=_label),
                dcc.Dropdown(id="scr-filter-itype", multi=True, placeholder="Todos", style=_dd_sm),
                html.Span("Sector", style=_label),
                dcc.Dropdown(id="scr-filter-sector", multi=True, placeholder="Todos", style=_dd_sm),
                html.Span("Industria", style=_label),
                dcc.Dropdown(id="scr-filter-industry", multi=True, placeholder="Todos", style=_dd_sm),
                html.Hr(style=_hr),
                html.Span("RSI", style=_label),
                dcc.RangeSlider(
                    id="scr-filter-rsi",
                    min=0, max=100, step=1,
                    value=[0, 100],
                    marks={0: "0", 30: "30", 50: "50", 70: "70", 100: "100"},
                    tooltip={"placement": "bottom", "always_visible": False},
                ),
                html.Hr(style=_hr),
                html.Span("Precio vs SMA 20", style=_label),
                dbc.RadioItems(id="scr-filter-sma20", options=_radio_opts, value="any",
                               style={"fontSize": "0.75rem"}),
                html.Span("Precio vs SMA 50", style=_label),
                dbc.RadioItems(id="scr-filter-sma50", options=_radio_opts, value="any",
                               style={"fontSize": "0.75rem"}),
                html.Span("Precio vs SMA 200", style=_label),
                dbc.RadioItems(id="scr-filter-sma200", options=_radio_opts, value="any",
                               style={"fontSize": "0.75rem"}),
                dbc.Button("Aplicar filtros", id="scr-btn-apply", color="primary",
                           className="mt-2 w-100", size="sm"),
            ], md=3, className="border-end pe-3"),
            dbc.Col([
                html.Div([
                    html.H5("Resultados", className="d-inline-block"),
                    html.Small(id="scr-result-count", className="text-muted ms-3"),
                ], className="mb-2"),
                dash_table.DataTable(
                    id="scr-table",
                    columns=_COLUMNS,
                    data=[],
                    sort_action="native",
                    filter_action="none",
                    page_size=50,
                    row_selectable="single",
                    selected_rows=[],
                    style_table={"overflowX": "auto"},
                    style_header=HEADER,
                    style_data=DATA,
                    style_cell={**CELL, "textAlign": "center"},
                    style_cell_conditional=[
                        {"if": {"column_id": c}, "textAlign": "left"}
                        for c in ["ticker", "name"]
                    ],
                    style_data_conditional=(
                        [
                            {"if": {"filter_query": f"{{{col}}} > 0", "column_id": col}, "color": "#4caf50"}
                            for col in ["var_daily", "var_month", "var_quarter", "var_year", "var_52w"]
                        ] + [
                            {"if": {"filter_query": f"{{{col}}} < 0", "column_id": col}, "color": "#ef5350"}
                            for col in ["var_daily", "var_month", "var_quarter", "var_year", "var_52w"]
                        ]
                    ),
                ),
            ], md=9),
        ]),
    ])


dash.register_page(__name__, path="/screener", title="Screener", layout=layout)
