import dash
import dash_bootstrap_components as dbc
from dash import dcc, html


def layout(**kwargs):
    from flask_login import current_user
    if not current_user.is_authenticated:
        return html.Div()

    return html.Div([
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
                    options=[{"label": " Mostrar eventos de mercado", "value": "events"}],
                    value=[],
                    inline=True,
                    style={"fontSize": "0.85rem"},
                ),
            ], md=4),
        ], className="mb-3 g-2 align-items-end"),

        dcc.Loading(
            dcc.Graph(
                id="scatter-graph",
                style={"height": "580px"},
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


dash.register_page(__name__, path="/scatter", title="Dispersión", layout=layout)
