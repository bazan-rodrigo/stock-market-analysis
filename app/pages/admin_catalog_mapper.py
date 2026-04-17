import dash
import dash_bootstrap_components as dbc
from dash import dcc, html

_ENTITY_TABS = [
    ("tab-country",          "País"),
    ("tab-market",           "Mercado"),
    ("tab-instrument_type",  "Tipo de instrumento"),
    ("tab-sector",           "Sector"),
    ("tab-industry",         "Industria"),
]


def layout(**kwargs):
    from flask_login import current_user
    if not current_user.is_authenticated or not current_user.is_admin:
        return html.Div()

    tabs = [dbc.Tab(label=label, tab_id=tab_id) for tab_id, label in _ENTITY_TABS]

    return html.Div([
        dcc.Store(id="mapper-pending-merge", data=None),
        html.Div(id="mapper-dnd-dummy", style={"display": "none"}),
        html.Button(id="mapper-drop-trigger", style={"display": "none"}, n_clicks=0),

        html.H3("Mapper de Catálogo", className="mb-1"),
        html.P(
            "Arrastrá una entidad de la columna izquierda sobre una de la derecha "
            "para fusionarlas. La de la derecha es la canónica y sobrevive; "
            "la de la izquierda será eliminada.",
            className="text-muted mb-3",
        ),

        dbc.Tabs(tabs, id="mapper-tabs", active_tab="tab-country", className="mb-3"),
        dbc.Alert(id="mapper-alert", is_open=False, dismissable=True, className="mb-3"),

        dbc.Row([
            dbc.Col([
                html.H6("Origen — arrastrá", className="text-muted mb-2"),
                html.Div(id="mapper-source-col", style={"minHeight": "200px"}),
            ], md=5),
            dbc.Col(
                html.Div("→", style={"fontSize": "2rem", "textAlign": "center", "paddingTop": "28px"}),
                md=2,
            ),
            dbc.Col([
                html.H6("Destino — soltá aquí", className="text-muted mb-2"),
                html.Div(id="mapper-target-col", style={"minHeight": "200px"}),
            ], md=5),
        ]),

        dbc.Modal([
            dbc.ModalHeader(dbc.ModalTitle("Confirmar fusión")),
            dbc.ModalBody(id="mapper-confirm-body"),
            dbc.ModalFooter([
                dbc.Button("Fusionar", id="mapper-btn-confirm", color="danger"),
                dbc.Button("Cancelar", id="mapper-btn-cancel", color="secondary", className="ms-2"),
            ]),
        ], id="mapper-confirm-modal", is_open=False),
    ])


dash.register_page(
    __name__,
    path="/admin/catalog-mapper",
    title="Mapper de Catálogo",
    layout=layout,
)
