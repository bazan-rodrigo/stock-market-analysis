import dash
import dash_bootstrap_components as dbc
from dash import dash_table, dcc, html

_COLUMNS = [
    {"name": "Ticker", "id": "ticker"},
    {"name": "Nombre", "id": "name"},
    {"name": "País", "id": "country_name"},
    {"name": "Mercado", "id": "market_name"},
    {"name": "Tipo", "id": "instrument_type_name"},
    {"name": "Moneda", "id": "currency_iso"},
    {"name": "Sector", "id": "sector_name"},
    {"name": "Fuente", "id": "source_name"},
    {"name": "Activo", "id": "active"},
]


def _build_asset_form():
    return dbc.Form([
        dbc.Row([
            dbc.Col([dbc.Label("Ticker *"), dbc.Input(id="assets-f-ticker", placeholder="AAPL")]),
            dbc.Col([dbc.Label("Nombre *"), dbc.Input(id="assets-f-name", placeholder="Apple Inc.")]),
        ], className="mb-3"),
        dbc.Row([
            dbc.Col([dbc.Label("Fuente de precios *"), dbc.Select(id="assets-f-price_source_id", options=[])]),
            dbc.Col([dbc.Label("Moneda *"), dbc.Select(id="assets-f-currency_id", options=[])]),
        ], className="mb-3"),
        dbc.Row([
            dbc.Col([dbc.Label("País *"), dbc.Select(id="assets-f-country_id", options=[])]),
            dbc.Col([dbc.Label("Mercado *"), dbc.Select(id="assets-f-market_id", options=[])]),
        ], className="mb-3"),
        dbc.Row([
            dbc.Col([dbc.Label("Tipo de instrumento *"), dbc.Select(id="assets-f-instrument_type_id", options=[])]),
            dbc.Col([dbc.Label("Sector"), dbc.Select(id="assets-f-sector_id", options=[])]),
        ], className="mb-3"),
        dbc.Row([
            dbc.Col([dbc.Label("Industria"), dbc.Select(id="assets-f-industry_id", options=[])]),
            dbc.Col([dbc.Label("Activo"), dbc.Switch(id="assets-f-active", value=True, label="Sí")]),
        ]),
        dbc.Alert(id="assets-autocomplete-alert", is_open=False, color="info", className="mt-3"),
    ])


def layout(**kwargs):
    from flask_login import current_user
    if not current_user.is_authenticated:
        return html.Div()
    is_admin = current_user.is_admin

    admin_buttons = []
    if is_admin:
        admin_buttons = [
            dbc.Button("+ Nuevo activo", id="assets-btn-add", color="primary", size="sm", className="me-2"),
            dbc.Button("Editar", id="assets-btn-edit", color="secondary", size="sm", disabled=True, className="me-2"),
            dbc.Button("Activar/Desactivar", id="assets-btn-toggle", color="warning", size="sm", disabled=True, className="me-2"),
            dbc.Button("Eliminar", id="assets-btn-delete", color="danger", size="sm", disabled=True),
        ]

    return html.Div([
        dcc.Store(id="assets-editing-id", data=None),
        dcc.Store(id="assets-autocomplete-data", data=None),
        html.Div([
            html.H3("Activos", className="d-inline-block me-3"),
            *admin_buttons,
        ], className="d-flex align-items-center mb-3"),
        dbc.Alert(id="assets-alert", is_open=False, dismissable=True),
        dash_table.DataTable(
            id="assets-table",
            columns=_COLUMNS,
            data=[],
            row_selectable="single",
            selected_rows=[],
            style_table={"overflowX": "auto"},
            style_cell={"textAlign": "left", "padding": "6px 12px"},
            style_header={"fontWeight": "bold", "backgroundColor": "#f8f9fa"},
            page_size=30,
            sort_action="native",
            filter_action="native",
        ),
        dbc.Modal([
            dbc.ModalHeader(dbc.ModalTitle(id="assets-modal-title")),
            dbc.ModalBody(_build_asset_form()),
            dbc.ModalFooter([
                dbc.Button("Autocompletar desde fuente", id="assets-btn-autocomplete", color="info", size="sm", className="me-auto"),
                dbc.Button("Guardar", id="assets-btn-save", color="primary"),
                dbc.Button("Cancelar", id="assets-btn-cancel", color="secondary", className="ms-2"),
            ]),
        ], id="assets-modal", is_open=False, size="lg"),
        dbc.Modal([
            dbc.ModalHeader(dbc.ModalTitle("Confirmar eliminación")),
            dbc.ModalBody("¿Eliminás este activo y toda su historia de precios?"),
            dbc.ModalFooter([
                dbc.Button("Sí, eliminar", id="assets-btn-confirm-delete", color="danger"),
                dbc.Button("Cancelar", id="assets-btn-cancel-delete", color="secondary", className="ms-2"),
            ]),
        ], id="assets-confirm-modal", is_open=False),
    ])


dash.register_page(__name__, path="/assets", title="Activos", layout=layout)
