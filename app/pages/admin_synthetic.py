import dash
import dash_bootstrap_components as dbc
from dash import dcc, html

_th = {"fontSize": "0.78rem", "color": "#aaa", "fontWeight": "normal",
       "padding": "6px 8px", "borderBottom": "1px solid #374151"}
_td = {"fontSize": "0.82rem", "padding": "5px 8px", "borderBottom": "1px solid #1f2937"}


def layout(**kwargs):
    from flask_login import current_user
    if not current_user.is_authenticated or not current_user.is_admin:
        return html.Div()

    modal = dbc.Modal([
        dbc.ModalHeader(dbc.ModalTitle(id="syn-modal-title")),
        dbc.ModalBody([
            dbc.Row([
                dbc.Col([
                    dbc.Label("Activo sintético (fuente Calculado)", style={"fontSize": "0.82rem"}),
                    dcc.Dropdown(id="syn-f-asset", placeholder="Seleccionar...",
                                 style={"fontSize": "0.85rem"}),
                ]),
            ], className="mb-3"),
            dbc.Row([
                dbc.Col([
                    dbc.Label("Numerador", style={"fontSize": "0.82rem"}),
                    dcc.Dropdown(id="syn-f-numerator", placeholder="Seleccionar...",
                                 style={"fontSize": "0.85rem"}),
                ], md=6),
                dbc.Col([
                    dbc.Label("Denominador", style={"fontSize": "0.82rem"}),
                    dcc.Dropdown(id="syn-f-denominator", placeholder="Seleccionar...",
                                 style={"fontSize": "0.85rem"}),
                ], md=6),
            ], className="mb-2"),
            html.Div(id="syn-formula-preview",
                     className="mt-2 text-muted", style={"fontSize": "0.78rem"}),
            dbc.Alert(id="syn-modal-error", is_open=False, color="danger",
                      className="mt-3 mb-0 small py-1"),
        ]),
        dbc.ModalFooter([
            dbc.Button("Guardar", id="syn-btn-save", color="primary"),
            dbc.Button("Cancelar", id="syn-btn-cancel", color="secondary", className="ms-2"),
        ]),
    ], id="syn-modal", is_open=False)

    return html.Div([
        dcc.Store(id="syn-editing-id", data=None),

        dbc.Row([
            dbc.Col(html.H4("Activos Sintéticos", className="mb-0"), width="auto"),
            dbc.Col(
                dbc.Button("+ Nuevo", id="syn-btn-add", color="primary", size="sm"),
                className="d-flex align-items-center",
            ),
        ], className="mb-3 align-items-center g-2"),

        dbc.Alert(id="syn-alert", is_open=False, dismissable=True, className="mb-3"),

        html.Div(id="syn-table-container"),

        # Info box
        dbc.Card(dbc.CardBody([
            html.P([
                html.Strong("Activos sintéticos: ", style={"color": "#e5e7eb"}),
                "activos cuyo precio se calcula como el cociente diario de dos activos existentes. "
                "Ejemplo: Dólar CCL = GGAL (ARS) / GGAL (USD). "
                "El activo destino debe tener la fuente de precios ",
                html.Strong('"Calculado"', style={"color": "#e5e7eb"}),
                " y debe estar dado de alta previamente en la gestión de activos.",
            ], className="mb-0", style={"fontSize": "0.78rem", "color": "#d1d5db"}),
        ]), className="mt-3",
           style={"backgroundColor": "#1f2937", "border": "1px solid #374151"}),

        modal,
    ], style={"padding": "0 8px"})


dash.register_page(__name__, path="/admin/synthetic", title="Activos Sintéticos", layout=layout)
