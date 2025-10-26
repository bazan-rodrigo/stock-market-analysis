# -*- coding: utf-8 -*-
"""
Pantalla de administracion de activos (Assets).
Usa la capa de servicios (asset_service) para acceder a la base de datos.
"""

from dash import html, dcc, Input, Output, State, dash_table
import dash_bootstrap_components as dbc
from flask_login import current_user
from core.logging_config import get_logger
from services import asset_service

logger = get_logger()

# ==========================================================
# LAYOUT
# ==========================================================
def admin_assets_layout():
    """Layout principal de la pantalla de administración de activos."""
    if not current_user.is_authenticated or current_user.role != "admin":
        return dbc.Alert("Acceso restringido a usuarios administradores.", color="danger")

    return html.Div([
        html.H4("Administración de activos"),
        html.Hr(),

        # Formulario
        dbc.Row([
            dbc.Col([
                dbc.Label("Símbolo (Ticker):"),
                dbc.Input(id="asset-symbol", type="text", placeholder="Ej: AAPL"),
            ], md=2),

            dbc.Col([
                dbc.Label("Nombre:"),
                dbc.Input(id="asset-name", type="text", placeholder="Ej: Apple Inc."),
            ], md=3),

            dbc.Col([
                dbc.Label("Fuente:"),
                dcc.Dropdown(id="asset-source", placeholder="Seleccione fuente"),
            ], md=3),

            dbc.Col([
                dbc.Label("Símbolo en fuente:"),
                dbc.Input(id="asset-source-symbol", type="text", placeholder="Ej: AAPL"),
            ], md=2),

            dbc.Col([
                dbc.Button("Agregar", id="btn-add-asset", color="success", className="mt-4"),
            ], md=2),
        ], className="mb-4"),

        dbc.Alert(id="asset-message", color="info", is_open=False),
        html.Hr(),

        html.H5("Lista de activos"),
        dash_table.DataTable(
            id="asset-table",
            columns=[
                {"name": "ID", "id": "id"},
                {"name": "Símbolo", "id": "symbol"},
                {"name": "Nombre", "id": "name"},
                {"name": "Fuente", "id": "source"},
                {"name": "Símbolo Fuente", "id": "source_symbol"},
                {"name": "País", "id": "country"},
                {"name": "Moneda", "id": "currency"},
            ],
            data=[],
            page_size=10,
            style_table={"overflowX": "auto"},
            style_cell={"textAlign": "center"},
            row_deletable=True
        ),
    ])

# ==========================================================
# CALLBACKS
# ==========================================================
def register_admin_asset_callbacks(app):
    """Registra los callbacks de la pantalla de activos."""

    # Cargar fuentes
    @app.callback(Output("asset-source", "options"), Input("url", "pathname"))
    def load_sources(path):
        if path != "/admin-assets":
            raise dash.exceptions.PreventUpdate
        return asset_service.list_sources()

    # Agregar activo
    @app.callback(
        Output("asset-message", "children"),
        Output("asset-message", "is_open"),
        Output("asset-table", "data"),
        Input("btn-add-asset", "n_clicks"),
        State("asset-symbol", "value"),
        State("asset-name", "value"),
        State("asset-source", "value"),
        State("asset-source-symbol", "value"),
        prevent_initial_call=True
    )
    def add_asset(n_clicks, symbol, name, source_id, source_symbol):
        if not all([symbol, name, source_id, source_symbol]):
            return "Complete todos los campos.", True, asset_service.list_assets()

        msg, ok = asset_service.create_asset(symbol, name, source_id, source_symbol)
        return msg, True, asset_service.list_assets()

    # Eliminar activo
    @app.callback(
        Output("asset-table", "data"),
        Input("asset-table", "data_previous"),
        State("asset-table", "data"),
        prevent_initial_call=True
    )
    def delete_asset(previous, current):
        if previous is None:
            raise dash.exceptions.PreventUpdate

        deleted = [p for p in previous if p not in current]
        if not deleted:
            raise dash.exceptions.PreventUpdate

        deleted_id = deleted[0]["id"]
        asset_service.delete_asset(deleted_id)
        return asset_service.list_assets()

    # Cargar tabla inicial
    @app.callback(Output("asset-table", "data"), Input("url", "pathname"))
    def load_assets(path):
        if path != "/admin-assets":
            raise dash.exceptions.PreventUpdate
        return asset_service.list_assets()