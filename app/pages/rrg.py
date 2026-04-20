import dash
import dash_bootstrap_components as dbc
from dash import dcc, html


def layout(**kwargs):
    from flask_login import current_user
    if not current_user.is_authenticated:
        return html.Div()

    return html.Div([
        dcc.Store(id="rrg-selected-assets", data=[]),
        dcc.Store(id="rrg-full-data", data=None),

        # ── Controles superiores: benchmark + cola ────────────────────────
        dbc.Row([
            dbc.Col([
                html.Small("Benchmark", className="text-muted d-block mb-1"),
                dcc.Dropdown(
                    id="rrg-benchmark-select",
                    placeholder="Seleccionar benchmark...",
                    style={"fontSize": "0.85rem"},
                ),
            ], md=4),
            dbc.Col([
                html.Small("Cola (semanas)", className="text-muted d-block mb-1"),
                dcc.Slider(
                    id="rrg-tail",
                    min=1, max=30, value=12, step=1,
                    marks={1: "1", 5: "5", 10: "10", 20: "20", 30: "30"},
                    tooltip={
                        "placement": "bottom",
                        "always_visible": True,
                        "style": {"color": "#dee2e6", "background": "#374151",
                                  "borderRadius": "4px", "padding": "2px 8px"},
                    },
                    updatemode="drag",
                ),
            ], md=5),
            dbc.Col([
                dbc.Button(
                    "Limpiar",
                    id="rrg-btn-clear",
                    color="secondary",
                    size="sm",
                    className="mt-3 w-100",
                ),
            ], md=3),
        ], className="mb-3 g-2 align-items-end"),

        dbc.Alert(
            id="rrg-alert",
            is_open=False,
            dismissable=True,
            className="mb-2",
            style={"fontSize": "0.85rem", "padding": "6px 12px"},
        ),

        dcc.Loading(
            html.Div(id="rrg-load-trigger", style={"display": "none"}),
            type="circle",
            color="#dee2e6",
        ),

        # ── Gráfico + panel lateral ───────────────────────────────────────
        dbc.Row([
            # Gráfico
            dbc.Col([
                dcc.Graph(
                    id="rrg-graph",
                    style={"height": "600px"},
                    config={
                        "displayModeBar": True,
                        "modeBarButtonsToRemove": ["lasso2d", "select2d"],
                        "scrollZoom": True,
                    },
                ),
            ], md=9),

            # Panel lateral: agregar activo + tabla
            dbc.Col([
                html.Small("Agregar activo", className="text-muted d-block mb-1"),
                dbc.InputGroup([
                    dcc.Dropdown(
                        id="rrg-asset-add-select",
                        placeholder="Buscar activo...",
                        style={"flex": 1, "fontSize": "0.85rem"},
                    ),
                    dbc.Button("+", id="rrg-btn-add", color="primary", size="sm"),
                ], size="sm", className="mb-3"),

                html.Div(
                    id="rrg-asset-list",
                    style={"overflowY": "auto", "maxHeight": "520px"},
                ),
            ], md=3),
        ], className="g-2"),

    ], style={"padding": "0 8px"})


dash.register_page(__name__, path="/rrg",
                   title="Rotación Relativa (RRG)", layout=layout)
