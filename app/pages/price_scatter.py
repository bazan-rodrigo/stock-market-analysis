import dash
import dash_bootstrap_components as dbc
from dash import dcc, html


def layout(**kwargs):
    from flask_login import current_user
    if not current_user.is_authenticated:
        return html.Div()

    _radio_sm = {"fontSize": "0.80rem"}

    return html.Div([
        # ── Fila 1: activos ──────────────────────────────────────────────────
        dbc.Row([
            dbc.Col([
                html.Small("Activo 1 (eje X)", className="text-muted d-block mb-1"),
                dcc.Dropdown(
                    id="scatter-asset1",
                    placeholder="Seleccionar...",
                    style={"fontSize": "0.85rem"},
                ),
            ], md=4),
            dbc.Col([
                dbc.Button(
                    "⇄",
                    id="scatter-swap-btn",
                    color="secondary",
                    size="sm",
                    className="mt-3",
                    title="Intercambiar activos",
                    style={"fontSize": "1rem", "lineHeight": 1},
                ),
            ], width="auto", className="d-flex align-items-end pb-1"),
            dbc.Col([
                html.Small("Activo 2 (eje Y)", className="text-muted d-block mb-1"),
                dcc.Dropdown(
                    id="scatter-asset2",
                    placeholder="Seleccionar...",
                    style={"fontSize": "0.85rem"},
                ),
            ], md=4),
            dbc.Col([
                html.Small("Opciones", className="text-muted d-block mb-1"),
                dbc.Checklist(
                    id="scatter-show-events",
                    options=[{"label": " Eventos de mercado", "value": "events"}],
                    value=[],
                    inline=True,
                    style={"fontSize": "0.85rem"},
                ),
            ]),
        ], className="mb-2 g-2 align-items-end"),

        # ── Fila 2: tendencia + escala ────────────────────────────────────────
        dbc.Row([
            dbc.Col([
                html.Small("Línea de tendencia", className="text-muted d-block mb-1"),
                dbc.RadioItems(
                    id="scatter-trend-type",
                    options=[
                        {"label": "Ninguna",      "value": "none"},
                        {"label": "Lineal",       "value": "linear"},
                        {"label": "Logarítmica",  "value": "log"},
                        {"label": "Polinómica",   "value": "poly"},
                        {"label": "Exponencial",  "value": "exp"},
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
                    id="scatter-poly-degree",
                    type="number", value=2, min=2, max=10, step=1,
                    style={"width": "60px", "fontSize": "0.82rem",
                           "padding": "2px 6px", "height": "28px"},
                ),
            ], id="scatter-poly-degree-col", width="auto",
               style={"display": "none"}),
            dbc.Col([
                html.Small("R²", className="text-muted d-block mb-1"),
                dbc.Switch(
                    id="scatter-show-r2",
                    value=True,
                    style={"marginBottom": 0},
                ),
            ], width="auto", className="d-flex flex-column justify-content-start"),
            dbc.Col([
                html.Small("Escala logarítmica", className="text-muted d-block mb-1"),
                dbc.Checklist(
                    id="scatter-log-axes",
                    options=[
                        {"label": " Eje X", "value": "x"},
                        {"label": " Eje Y", "value": "y"},
                    ],
                    value=[],
                    inline=True,
                    style={"fontSize": "0.82rem"},
                ),
            ]),
        ], className="mb-3 g-2 align-items-end"),

        dcc.Loading(
            dcc.Graph(
                id="scatter-graph",
                style={"height": "560px"},
                config={
                    "displayModeBar": True,
                    "modeBarButtonsToRemove": ["lasso2d", "select2d"],
                    "scrollZoom": True,
                },
            ),
            type="circle",
            color="#dee2e6",
        ),

        html.Div(id="scatter-stats", className="mt-2 text-muted",
                 style={"fontSize": "0.78rem"}),

    ], style={"padding": "0 8px"})


dash.register_page(__name__, path="/scatter", title="Correlación de precios", layout=layout)
