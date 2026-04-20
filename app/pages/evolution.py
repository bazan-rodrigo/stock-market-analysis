from datetime import date, timedelta

import dash
import dash_bootstrap_components as dbc
from dash import dcc, html


def layout(**kwargs):
    from flask_login import current_user
    if not current_user.is_authenticated:
        return html.Div()

    today     = date.today()
    one_year  = today - timedelta(days=365)

    return html.Div([
        dcc.Store(id="evol-series",      data=[]),
        dcc.Store(id="evol-pending-add", data=None),

        # ── Modal: agregar activos relacionados ───────────────────────────
        dbc.Modal([
            dbc.ModalHeader(dbc.ModalTitle(id="evol-rel-modal-title")),
            dbc.ModalBody(id="evol-rel-modal-body"),
            dbc.ModalFooter([
                dbc.Button("Sí, agregar relacionados", id="evol-rel-btn-yes",
                           color="primary", size="sm"),
                dbc.Button("Solo el activo",           id="evol-rel-btn-no",
                           color="secondary", size="sm", className="ms-2"),
            ]),
        ], id="evol-rel-modal", is_open=False),

        dbc.Alert(id="evol-alert", is_open=False, dismissable=True,
                  color="warning", className="mb-2"),

        # ── Panel de controles ────────────────────────────────────────────
        dbc.Card(dbc.CardBody([
            # Fila 1: selector individual + fechas + eventos
            dbc.Row([
                dbc.Col([
                    html.Small("Activo", className="text-muted d-block mb-1"),
                    dbc.InputGroup([
                        dcc.Dropdown(
                            id="evol-add-select",
                            placeholder="Buscar activo...",
                            style={"fontSize": "0.85rem", "flex": "1 1 auto"},
                        ),
                        dbc.Button("Agregar", id="evol-btn-add",
                                   color="primary", size="sm"),
                    ]),
                ], md=4),
                dbc.Col([
                    html.Small("Fecha desde", className="text-muted d-block mb-1"),
                    dcc.DatePickerSingle(
                        id="evol-date-from",
                        date=one_year.isoformat(),
                        display_format="YYYY-MM-DD",
                        style={"fontSize": "0.85rem"},
                    ),
                ], md=2),
                dbc.Col([
                    html.Small("Fecha hasta", className="text-muted d-block mb-1"),
                    dcc.DatePickerSingle(
                        id="evol-date-to",
                        date=today.isoformat(),
                        display_format="YYYY-MM-DD",
                        style={"fontSize": "0.85rem"},
                    ),
                ], md=2),
                dbc.Col([
                    html.Small("Eventos de Mercado", className="text-muted d-block mb-1"),
                    dbc.Switch(id="evol-show-events", value=False,
                               label="Mostrar eventos"),
                ], md=2, className="d-flex flex-column justify-content-start"),
                dbc.Col([
                    html.Small("\u00a0", className="d-block mb-1"),
                    dbc.Button("Limpiar todo", id="evol-btn-clear",
                               color="outline-danger", size="sm"),
                ], md=2, className="d-flex flex-column justify-content-start"),
            ], className="mb-3 g-2 align-items-end"),

            # Fila 2: filtros de grupo
            dbc.Row([
                dbc.Col(html.Small("Agregar por grupo:", className="text-muted"),
                        width=12, className="mb-1"),
                dbc.Col([
                    dcc.Dropdown(id="evol-f-country",  placeholder="País",
                                 multi=True, style={"fontSize": "0.78rem"}),
                ], md=2),
                dbc.Col([
                    dcc.Dropdown(id="evol-f-currency", placeholder="Moneda",
                                 multi=True, style={"fontSize": "0.78rem"}),
                ], md=2),
                dbc.Col([
                    dcc.Dropdown(id="evol-f-itype",    placeholder="Tipo",
                                 multi=True, style={"fontSize": "0.78rem"}),
                ], md=2),
                dbc.Col([
                    dcc.Dropdown(id="evol-f-sector",   placeholder="Sector",
                                 multi=True, style={"fontSize": "0.78rem"}),
                ], md=2),
                dbc.Col([
                    dcc.Dropdown(id="evol-f-industry", placeholder="Industria",
                                 multi=True, style={"fontSize": "0.78rem"}),
                ], md=2),
                dbc.Col([
                    dcc.Dropdown(id="evol-f-market",   placeholder="Mercado",
                                 multi=True, style={"fontSize": "0.78rem"}),
                ], md=1),
                dbc.Col([
                    dbc.Button("Agregar grupo", id="evol-btn-add-group",
                               color="secondary", size="sm"),
                ], md=1, className="d-flex align-items-end"),
            ], className="g-2"),
        ]), className="mb-3"),

        # ── Gráfico + lista de series ─────────────────────────────────────
        dbc.Row([
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
                    type="circle", color="#dee2e6",
                ),
            ], md=9),
            dbc.Col([
                html.Div(id="evol-series-list",
                         style={"maxHeight": "540px", "overflowY": "auto",
                                "fontSize": "0.78rem"}),
            ], md=3),
        ]),
    ], style={"padding": "0 8px"})


dash.register_page(__name__, path="/evolucion", title="Evolución Relativa", layout=layout)
