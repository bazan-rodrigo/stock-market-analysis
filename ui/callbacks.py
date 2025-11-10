# -*- coding: utf-8 -*-
"""
Callbacks y ruteo de la aplicacion Dash.
 - Controla la navegacion por URL.
 - Ejecuta el proceso de actualizacion manual.
 - Conecta pantallas principales.
"""

from dash import Output, Input, html, dash_table
import dash_bootstrap_components as dbc
from services.price_updater import update_all_assets
from core.logging_config import get_logger
from ui.admin_users import admin_users_layout, register_admin_callbacks
from ui.admin_assets import admin_assets_layout, register_admin_asset_callbacks
from ui.import_assets import import_assets_layout, register_import_assets_callbacks
from ui.price_updates import price_updates_layout, register_price_updates_callbacks

logger = get_logger(__name__)

# -----------------------------------------------------
# PANTALLAS SIMPLES (placeholder)
# -----------------------------------------------------
def dashboard_layout():
    """
    Pantalla principal (Dashboard)
    """
    return dbc.Container([
        html.H4("Actualizacion manual de precios"),
        dbc.Button("Ejecutar actualizacion", id="btn-run-update", n_clicks=0, className="mt-3"),
        html.Div(id="update-results", className="mt-3")
    ])

def failed_updates_layout():
    """
    Pantalla de actualizaciones fallidas
    """
    return dbc.Container([
        html.H4("Actualizaciones fallidas"),
        html.P("Proximamente: listado y gestion de errores de actualizacion.")
    ])

# -----------------------------------------------------
# REGISTRO DE CALLBACKS
# -----------------------------------------------------
def register_callbacks(app):
    """
    Registra los callbacks principales de la aplicacion Dash.
    """

    # Navegacion entre paginas
    @app.callback(Output("page-content", "children"), Input("url", "pathname"))
    def display_page(pathname):
        if pathname == "/admin-users":
            return admin_users_layout()
        elif pathname == "/admin-assets":
            return admin_assets_layout()
        if pathname == "/import-assets":
            return import_assets_layout()
        elif pathname == "/price-updates":
            return price_updates_layout()
        else:
            return dashboard_layout()

    # -------------------------------------------------
    # Boton: ejecutar actualizacion manual de precios
    # -------------------------------------------------
    @app.callback(
        Output("update-results", "children"),
        Input("btn-run-update", "n_clicks"),
        prevent_initial_call=True
    )
    def on_run_update(n_clicks):
        """
        Ejecuta la actualizacion manual de precios
        y muestra un resumen con la cantidad de exitos y fallos.
        """
        try:
            results = update_all_assets(run_type="manual")
            if not results:
                return dbc.Alert("Sin resultados.", color="warning")

            rows = [{"Campo": "Exitosos", "Valor": results.get("success")},
                    {"Campo": "Fallidos", "Valor": results.get("failures")}]

            return dash_table.DataTable(
                columns=[{"name": "Campo", "id": "Campo"}, {"name": "Valor", "id": "Valor"}],
                data=rows,
                style_table={"overflowX": "auto"},
                style_cell={"textAlign": "center"}
            )
        except Exception as e:
            logger.exception(e)
            return dbc.Alert(f"Fallo al ejecutar actualizacion: {e}", color="danger")


    # Registrar los callbacks del modulo de administracion
    register_admin_callbacks(app)
    register_admin_asset_callbacks(app)
    register_import_assets_callbacks(app)
    register_price_updates_callbacks(app)