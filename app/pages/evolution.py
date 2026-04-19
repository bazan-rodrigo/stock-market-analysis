import dash
import dash_bootstrap_components as dbc
from dash import dcc, html


def layout(**kwargs):
    from flask_login import current_user
    if not current_user.is_authenticated:
        return html.Div()

    return html.Div([
        dcc.Store(id="evol-series", data=[]),

        # Controls row
        dbc.Row([
            dbc.Col([
                html.Small("Activo principal", className="text-muted d-block mb-1"),
                dcc.Dropdown(
                    id="evol-primary",
                    placeholder="Seleccionar activo...",
                    style={"fontSize": "0.85rem"},
                ),
            ], md=4),
            dbc.Col([
                html.Small("Agregar serie manual", className="text-muted d-block mb-1"),
                dbc.InputGroup([
                    dcc.Dropdown(
                        id="evol-add-select",
                        placeholder="Seleccionar...",
                        style={"fontSize": "0.85rem", "flex": "1 1 auto"},
                    ),
                    dbc.Button("Agregar", id="evol-btn-add", color="secondary", size="sm"),
                ]),
            ], md=4),
            dbc.Col([
                html.Small("Fecha base", className="text-muted d-block mb-1"),
                dcc.DatePickerSingle(
                    id="evol-base-date",
                    display_format="YYYY-MM-DD",
                    placeholder="Inicio de datos",
                    style={"fontSize": "0.85rem"},
                ),
            ], md=2),
            dbc.Col([
                html.Small("Mostrar relacionados", className="text-muted d-block mb-1"),
                dbc.Switch(id="evol-show-related", value=True, label="Sí"),
            ], md=2, className="d-flex flex-column justify-content-start"),
        ], className="mb-3 g-2 align-items-end"),

        dbc.Alert(id="evol-alert", is_open=False, dismissable=True,
                  color="warning", className="mb-2"),

        # Series list + chart
        dbc.Row([
            dbc.Col([
                html.Div(id="evol-series-list"),
            ], md=3),
            dbc.Col([
                dcc.Loading(
                    dcc.Graph(
                        id="evol-graph",
                        style={"height": "540px"},
                        config={
                            "displayModeBar": True,
                            "modeBarButtonsToRemove": ["lasso2d", "select2d"],
                            "scrollZoom": True,
                        },
                    ),
                    type="circle",
                    color="#dee2e6",
                ),
            ], md=9),
        ]),
    ], style={"padding": "0 8px"})


dash.register_page(__name__, path="/evolucion", title="Evolución Relativa", layout=layout)
