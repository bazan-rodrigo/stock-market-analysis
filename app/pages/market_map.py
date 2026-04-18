import dash
import dash_bootstrap_components as dbc
from dash import dcc, html

_DIMS = [
    ("sector",   "Sectores"),
    ("industry", "Industrias"),
    ("country",  "Países"),
    ("itype",    "Tipos"),
    ("market",   "Mercados"),
]


def _score_badge(score):
    """Celda coloreada para un score -100..+100 (o None)."""
    if score is None:
        return html.Td("—", style={"color": "#555", "textAlign": "center"})
    if score >= 50:
        color = "#4caf50"
    elif score >= 20:
        color = "#a5d6a7"
    elif score <= -50:
        color = "#ef5350"
    elif score <= -20:
        color = "#ef9a9a"
    else:
        color = "#90a4ae"
    return html.Td(
        f"{score:+.0f}",
        style={"color": color, "fontWeight": "bold", "textAlign": "center",
               "fontSize": "0.82rem", "width": "60px"},
    )


def _build_table(dim_data: dict) -> html.Table:
    """Construye la tabla de grupos para una dimensión."""
    rows_sorted = sorted(
        dim_data.values(),
        key=lambda g: (g.get("d") or 0),
        reverse=True,
    )
    tbody_rows = []
    for g in rows_sorted:
        tbody_rows.append(html.Tr([
            html.Td(g["name"],
                    style={"fontSize": "0.82rem", "whiteSpace": "nowrap",
                           "overflow": "hidden", "textOverflow": "ellipsis",
                           "maxWidth": "200px"}),
            html.Td(str(g["n"]),
                    style={"textAlign": "center", "color": "#aaa", "fontSize": "0.78rem"}),
            _score_badge(g.get("d")),
            _score_badge(g.get("w")),
            _score_badge(g.get("m")),
        ]))

    return html.Table([
        html.Thead(html.Tr([
            html.Th("Grupo",    style={"fontSize": "0.78rem", "color": "#aaa", "fontWeight": "normal"}),
            html.Th("N",        style={"textAlign": "center", "fontSize": "0.78rem", "color": "#aaa", "fontWeight": "normal", "width": "40px"}),
            html.Th("Score D",  style={"textAlign": "center", "fontSize": "0.78rem", "color": "#aaa", "fontWeight": "normal", "width": "60px"}),
            html.Th("Score S",  style={"textAlign": "center", "fontSize": "0.78rem", "color": "#aaa", "fontWeight": "normal", "width": "60px"}),
            html.Th("Score M",  style={"textAlign": "center", "fontSize": "0.78rem", "color": "#aaa", "fontWeight": "normal", "width": "60px"}),
        ]), style={"borderBottom": "1px solid #444"}),
        html.Tbody(tbody_rows),
    ], style={"width": "100%", "borderCollapse": "collapse"})


def layout(**kwargs):
    from flask_login import current_user
    if not current_user.is_authenticated:
        return html.Div()

    return html.Div([
        dbc.Row([
            dbc.Col(html.H4("Mapa de Mercado", className="mb-0"), width="auto"),
            dbc.Col(
                html.Small(
                    "Score de tendencia por grupo (−100 Bajista fuerte · 0 Lateral · +100 Alcista fuerte). "
                    "Calculado sobre todos los activos activos con snapshot.",
                    className="text-muted",
                    style={"fontSize": "0.75rem"},
                ),
                className="d-flex align-items-center",
            ),
        ], className="mb-3 align-items-center"),

        dbc.Alert(id="market-map-alert", is_open=False, dismissable=True, className="mb-2"),

        dbc.Tabs(
            [dbc.Tab(label=label, tab_id=dim_key) for dim_key, label in _DIMS],
            id="market-map-tabs",
            active_tab="sector",
            className="mb-3",
        ),

        dcc.Loading(
            html.Div(id="market-map-content"),
            type="circle",
            color="#dee2e6",
        ),
    ], style={"padding": "0 8px"})


dash.register_page(__name__, path="/market-map", title="Mapa de Mercado", layout=layout)
