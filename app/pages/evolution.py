from datetime import date, timedelta

import dash
import dash_bootstrap_components as dbc
from dash import dcc, html


def layout(**kwargs):
    from flask_login import current_user
    if not current_user.is_authenticated:
        return html.Div()

    today    = date.today()
    one_year = today - timedelta(days=365)

    _radio_opts = [
        {"label": "Por activo",    "value": "activo"},
        {"label": "Por benchmark", "value": "benchmark"},
        {"label": "Por sintético", "value": "sintetico"},
        {"label": "Por grupos",    "value": "grupos"},
    ]

    return html.Div([
        dcc.Store(id="evol-series",      data=[]),
        dcc.Store(id="evol-pending-add", data=None),

        # ── Modal: activos relacionados ───────────────────────────────────
        dbc.Modal([
            dbc.ModalHeader(dbc.ModalTitle(id="evol-rel-modal-title")),
            dbc.ModalBody(id="evol-rel-modal-body"),
            dbc.ModalFooter([
                dbc.Button("Sí, agregar relacionados", id="evol-rel-btn-yes",
                           color="primary", size="sm"),
                dbc.Button("Solo el activo", id="evol-rel-btn-no",
                           color="secondary", size="sm", className="ms-2"),
            ]),
        ], id="evol-rel-modal", is_open=False),

        dbc.Alert(id="evol-alert", is_open=False, dismissable=True,
                  color="warning", className="mb-2"),

        # ── Panel de controles ────────────────────────────────────────────
        dbc.Card(dbc.CardBody([
            dbc.Row([
                dbc.Col([
                    html.Small("Modo de selección", className="text-muted d-block mb-1"),
                    dbc.RadioItems(
                        id="evol-mode",
                        options=_radio_opts,
                        value="activo",
                        inline=True,
                        inputStyle={"marginRight": "4px"},
                        labelStyle={"marginRight": "14px", "fontSize": "0.83rem",
                                    "cursor": "pointer"},
                    ),
                ], md=4),
                dbc.Col([
                    html.Small("Fecha desde", className="text-muted d-block mb-1"),
                    dcc.DatePickerSingle(
                        id="evol-date-from", date=one_year.isoformat(),
                        display_format="YYYY-MM-DD", style={"fontSize": "0.85rem"},
                    ),
                ], md=2),
                dbc.Col([
                    html.Small("Fecha hasta", className="text-muted d-block mb-1"),
                    dcc.DatePickerSingle(
                        id="evol-date-to", date=today.isoformat(),
                        display_format="YYYY-MM-DD", style={"fontSize": "0.85rem"},
                    ),
                ], md=2),
                dbc.Col([
                    html.Small("Eventos de Mercado", className="text-muted d-block mb-1"),
                    dbc.Switch(id="evol-show-events", value=False,
                               label="Mostrar eventos"),
                ], md=2, className="d-flex flex-column justify-content-start"),
            ], className="g-2 align-items-end"),
        ]), className="mb-3"),

        # ── Panel de agregar + limpiar (sobre el gráfico) ─────────────────
        dbc.Card(dbc.CardBody([
            dbc.Row([
                dbc.Col([
                    # — Por activo —
                    html.Div([
                        dbc.InputGroup([
                            dcc.Dropdown(
                                id="evol-add-select",
                                placeholder="Buscar activo...",
                                style={"fontSize": "0.85rem", "flex": "1 1 auto"},
                            ),
                            dbc.Button("Agregar", id="evol-btn-add",
                                       color="primary", size="sm"),
                        ]),
                    ], id="evol-panel-activo"),

                    # — Por benchmark —
                    html.Div([
                        dbc.InputGroup([
                            dcc.Dropdown(
                                id="evol-bm-select",
                                placeholder="Seleccionar benchmark...",
                                style={"fontSize": "0.85rem", "flex": "1 1 auto"},
                            ),
                            dbc.Button("Agregar", id="evol-btn-add-bm",
                                       color="primary", size="sm"),
                        ]),
                    ], id="evol-panel-benchmark", style={"display": "none"}),

                    # — Por sintético —
                    html.Div([
                        dbc.InputGroup([
                            dcc.Dropdown(
                                id="evol-syn-select",
                                placeholder="Seleccionar sintético...",
                                style={"fontSize": "0.85rem", "flex": "1 1 auto"},
                            ),
                            dbc.Button("Agregar", id="evol-btn-add-syn",
                                       color="primary", size="sm"),
                        ]),
                    ], id="evol-panel-sintetico", style={"display": "none"}),

                    # — Por grupos —
                    html.Div([
                        dbc.Row([
                            dbc.Col([
                                dcc.Dropdown(id="evol-f-country",  placeholder="País",
                                             multi=True, style={"fontSize": "0.78rem"}),
                            ], md=3),
                            dbc.Col([
                                dcc.Dropdown(id="evol-f-currency", placeholder="Moneda",
                                             multi=True, style={"fontSize": "0.78rem"}),
                            ], md=3),
                            dbc.Col([
                                dcc.Dropdown(id="evol-f-itype",    placeholder="Tipo",
                                             multi=True, style={"fontSize": "0.78rem"}),
                            ], md=3),
                            dbc.Col([
                                dcc.Dropdown(id="evol-f-sector",   placeholder="Sector",
                                             multi=True, style={"fontSize": "0.78rem"}),
                            ], md=3),
                            dbc.Col([
                                dcc.Dropdown(id="evol-f-industry", placeholder="Industria",
                                             multi=True, style={"fontSize": "0.78rem"}),
                            ], md=3),
                            dbc.Col([
                                dcc.Dropdown(id="evol-f-market",   placeholder="Mercado",
                                             multi=True, style={"fontSize": "0.78rem"}),
                            ], md=3),
                            dbc.Col([
                                dbc.Button("Agregar", id="evol-btn-add-group",
                                           color="primary", size="sm"),
                            ], md=2, className="d-flex align-items-end"),
                        ], className="g-2 align-items-end"),
                    ], id="evol-panel-grupos", style={"display": "none"}),
                ]),
                dbc.Col([
                    dbc.Button("Limpiar todo", id="evol-btn-clear",
                               color="outline-danger", size="sm"),
                ], width="auto", className="d-flex align-items-end"),
            ], className="g-2 align-items-end"),
        ]), className="mb-3"),

        # ── Lista de series (chips horizontales) ─────────────────────────
        html.Div(id="evol-series-list",
                 style={"marginBottom": "8px", "display": "flex", "flexWrap": "wrap",
                        "gap": "4px", "fontSize": "0.78rem"}),

        # ── Gráfico ───────────────────────────────────────────────────────
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
            type="circle", color="#dee2e6",
        ),
    ], style={"padding": "0 8px"})


dash.register_page(__name__, path="/evolucion", title="Evolución Relativa", layout=layout)
