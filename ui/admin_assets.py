# -*- coding: utf-8 -*-
"""
Pantalla de administración de activos (Assets).
Usa la capa de servicios (asset_service) para acceder a la base de datos.
"""

from dash import html, dcc, Input, Output, State, dash_table
import dash_bootstrap_components as dbc
from flask_login import current_user
from core.logging_config import get_logger
from services import asset_service
from ui.import_assets import import_assets_layout
import dash

logger = get_logger(__name__)

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

        # Formulario de creación
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

        dbc.Alert(id="asset-message", is_open=False),
        html.Hr(),

        dbc.Row([
            dbc.Col(html.H5("Lista de activos"), md=9),
            dbc.Col(dbc.Button("⬆️ Importar desde CSV", id="btn-show-import", color="info"), md=3, style={"textAlign": "right"}),
        ]),
        html.Div(id="import-section", style={"marginTop": "20px"}),

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

    # ------------------------------------------------------
    # Cargar fuentes
    # ------------------------------------------------------
    @app.callback(Output("asset-source", "options"), Input("url", "pathname"))
    def load_sources(path):
        if path != "/admin-assets":
            raise dash.exceptions.PreventUpdate
        return asset_service.list_sources()

    # ------------------------------------------------------
    # Agregar activo
    # ------------------------------------------------------
    @app.callback(
        Output("asset-message", "children"),
        Output("asset-message", "color"),
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
            return "⚠️ Complete todos los campos.", "warning", True, asset_service.list_assets()

        msg, ok = asset_service.create_asset(symbol, name, source_id, source_symbol)
        color = "success" if ok else "danger"

        if ok:
            logger.info(f"Asset creado exitosamente: {symbol}")
        else:
            logger.error(f"Error al crear asset: {symbol} ({msg})")

        return msg, color, True, asset_service.list_assets()

    # ------------------------------------------------------
    # Eliminar activo (con confirmación)
    # ------------------------------------------------------
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
        symbol = deleted[0].get("symbol", "?")

        try:
            asset_service.delete_asset(deleted_id)
            logger.info(f"Asset eliminado: {symbol} (ID {deleted_id})")
        except Exception as e:
            logger.error(f"Error al eliminar asset {symbol}: {e}")

        return asset_service.list_assets()

    # ------------------------------------------------------
    # Cargar tabla inicial
    # ------------------------------------------------------
    @app.callback(Output("asset-table", "data"), Input("url", "pathname"))
    def load_assets(path):
        if path != "/admin-assets":
            raise dash.exceptions.PreventUpdate
        return asset_service.list_assets()

    # ------------------------------------------------------
    # Mostrar módulo de importación
    # ------------------------------------------------------
    @app.callback(
        Output("import-section", "children"),
        Input("btn-show-import", "n_clicks"),
        prevent_initial_call=True
    )
    def show_import_section(n_clicks):
        logger.info("Se abrió el módulo de importación de assets.")
        return import_assets_layout()