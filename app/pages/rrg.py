import dash
import dash_bootstrap_components as dbc
from dash import dcc, html


def layout(**kwargs):
    from flask_login import current_user
    if not current_user.is_authenticated:
        return html.Div()

    return html.Div([
        dcc.Store(id="rrg-selected-assets", data=[]),

        # ── Controles ────────────────────────────────────────────────────────
        dbc.Row([
            dbc.Col([
                html.Small("Benchmark", className="text-muted d-block mb-1"),
                dcc.Dropdown(
                    id="rrg-benchmark-select",
                    placeholder="Seleccionar benchmark...",
                    style={"fontSize": "0.85rem"},
                ),
            ], md=3),
            dbc.Col([
                html.Small("Cola (semanas)", className="text-muted d-block mb-1"),
                dcc.Slider(
                    id="rrg-tail",
                    min=1, max=30, value=12, step=1,
                    marks={1: "1", 5: "5", 10: "10", 20: "20", 30: "30"},
                    tooltip={"placement": "bottom", "always_visible": True},
                ),
            ], md=3),
            dbc.Col([
                html.Small("Agregar activo", className="text-muted d-block mb-1"),
                dbc.InputGroup([
                    dcc.Dropdown(
                        id="rrg-asset-add-select",
                        placeholder="Buscar activo...",
                        style={"flex": 1, "fontSize": "0.85rem"},
                    ),
                    dbc.Button("+", id="rrg-btn-add", color="primary", size="sm"),
                ], size="sm"),
            ], md=4),
            dbc.Col([
                dbc.Button(
                    "Limpiar",
                    id="rrg-btn-clear",
                    color="secondary",
                    size="sm",
                    className="mt-3 w-100",
                ),
            ], md=2),
        ], className="mb-3 g-2 align-items-end"),

        dbc.Alert(
            id="rrg-alert",
            is_open=False,
            dismissable=True,
            className="mb-2",
            style={"fontSize": "0.85rem", "padding": "6px 12px"},
        ),

        # ── Gráfico ──────────────────────────────────────────────────────────
        dcc.Loading(
            dcc.Graph(
                id="rrg-graph",
                style={"height": "620px"},
                config={"displayModeBar": False},
            ),
            type="circle",
            color="#dee2e6",
        ),

        # ── Tabla de activos seleccionados ───────────────────────────────────
        html.Div(id="rrg-asset-list", className="mt-2"),

    ], style={"padding": "0 8px"})


dash.register_page(__name__, path="/rrg", title="RRG", layout=layout)
