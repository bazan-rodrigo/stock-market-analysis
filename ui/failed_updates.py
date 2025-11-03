# -*- coding: utf-8 -*-
"""
UI: failed_updates.py
--------------------------------------------------------
Pantalla de monitoreo y administración de errores de actualización de precios.
Incluye:
 - Botones por fila: Marcar resuelto / Reintentar
 - Columna de estado dinámica
"""

from dash import html, Input, Output, State, callback, dash_table, ctx
import dash_bootstrap_components as dbc
from flask_login import current_user
from core.logging_config import get_logger
from services import failed_updates, price_updater
import dash
import json

logger = get_logger(__name__)


# ==========================================================
# LAYOUT PRINCIPAL
# ==========================================================
def failed_updates_layout():
    """Renderiza el layout principal de la pantalla de errores."""
    if not current_user.is_authenticated or current_user.role != "admin":
        return dbc.Alert("Acceso restringido a administradores.", color="danger")

    return html.Div([
        html.H4("Errores en actualización de precios"),
        html.Hr(),

        dbc.Row([
            dbc.Col(dbc.Button("🔄 Refrescar lista", id="btn-refresh-failed", color="secondary"), width="auto"),
        ], className="mb-3"),

        dbc.Alert(id="failed-msg", is_open=False, color="info"),
        html.Div(id="failed-table-container"),
    ])


# ==========================================================
# REGISTRO DE CALLBACKS
# ==========================================================
def register_failed_updates_callbacks(app):
    """Registra los callbacks de la pantalla de errores."""

    # ------------------------------------------------------
    # Cargar lista de errores
    # ------------------------------------------------------
    @app.callback(
        Output("failed-table-container", "children"),
        Input("btn-refresh-failed", "n_clicks"),
        prevent_initial_call=True
    )
    def refresh_failed_updates(_):
        """Carga los errores pendientes desde la base de datos."""
        try:
            rows = failed_updates.list_failed_updates()
            if not rows:
                return dbc.Alert("✅ No hay errores pendientes.", color="success")

            header = html.Thead(html.Tr([
                html.Th("ID"),
                html.Th("Símbolo"),
                html.Th("Fuente"),
                html.Th("Mensaje"),
                html.Th("Modo"),
                html.Th("Fecha"),
                html.Th("Estado"),
                html.Th("Acciones")
            ]))

            body = html.Tbody([
                html.Tr([
                    html.Td(r.get("id")),
                    html.Td(r.get("symbol") or "-"),
                    html.Td(r.get("source") or "-"),
                    html.Td(r.get("error_message")),
                    html.Td(r.get("run_type")),
                    html.Td(r.get("timestamp")),
                    html.Td("Pendiente", id={"type": "cell-status", "index": r["id"]}),
                    html.Td([
                        dbc.Button(
                            "Marcar resuelto",
                            id={"type": "btn-resolve-error", "index": r["id"]},
                            color="success", size="sm", className="me-2"
                        ),
                        dbc.Button(
                            "Reintentar",
                            id={"type": "btn-retry-error", "index": r["id"]},
                            color="warning", size="sm"
                        )
                    ])
                ]) for r in rows
            ])

            return dbc.Table([header, body], bordered=True, hover=True, striped=True)

        except Exception as e:
            logger.exception(e)
            return dbc.Alert(f"Error cargando lista de errores: {e}", color="danger")

    # ------------------------------------------------------
    # Marcar error como resuelto
    # ------------------------------------------------------
    @app.callback(
        Output({"type": "cell-status", "index": dash.ALL}, "children"),
        Output("failed-msg", "children"),
        Output("failed-msg", "color"),
        Output("failed-msg", "is_open"),
        Input({"type": "btn-resolve-error", "index": str}, "n_clicks"),
        State({"type": "cell-status", "index": dash.ALL}, "id"),
        prevent_initial_call=True
    )
    def resolve_error(n_clicks, all_status_ids):
        """Callback para marcar error como resuelto y actualizar su estado."""
        if not ctx.triggered_id:
            raise dash.exceptions.PreventUpdate

        error_id = ctx.triggered_id["index"]

        try:
            failed_updates.mark_failed_update_resolved(error_id)
            msg = f"✅ Error {error_id} marcado como resuelto."
            logger.info(msg)

            # Actualizar el estado dinámicamente en la tabla
            updated_status = [
                "Resuelto" if s["index"] == error_id else dash.no_update
                for s in all_status_ids
            ]
            return updated_status, msg, "success", True

        except Exception as e:
            logger.error(f"Error al marcar {error_id} como resuelto: {e}")
            return dash.no_update, f"No se pudo marcar {error_id}: {e}", "danger", True

    # ------------------------------------------------------
    # Reintentar actualización del símbolo
    # ------------------------------------------------------
    @app.callback(
        Output({"type": "cell-status", "index": dash.ALL}, "children"),
        Output("failed-msg", "children"),
        Output("failed-msg", "color"),
        Output("failed-msg", "is_open"),
        Input({"type": "btn-retry-error", "index": str}, "n_clicks"),
        State({"type": "cell-status", "index": dash.ALL}, "id"),
        prevent_initial_call=True
    )
    def retry_error(n_clicks, all_status_ids):
        """Reintenta la actualización del símbolo con error y actualiza el estado."""
        if not ctx.triggered_id:
            raise dash.exceptions.PreventUpdate

        error_id = ctx.triggered_id["index"]

        try:
            errors = failed_updates.list_failed_updates()
            err_row = next((r for r in errors if r["id"] == error_id), None)
            if not err_row:
                raise ValueError("No se encontró el registro en la lista actual.")

            symbol = err_row.get("symbol")
            if not symbol:
                raise ValueError("No se encontró el símbolo asociado al error.")

            logger.info(f"🔁 Reintentando actualización de {symbol} (error_id={error_id})...")
            success = price_updater.update_single_asset(symbol)

            if success:
                failed_updates.mark_failed_update_resolved(error_id)
                msg = f"✅ Reintento exitoso: {symbol} actualizado y error {error_id} resuelto."
                color = "success"
                updated_status = [
                    "Reintentado ✅" if s["index"] == error_id else dash.no_update
                    for s in all_status_ids
                ]
            else:
                msg = f"❌ No se pudo actualizar {symbol}. Ver logs para más detalles."
                color = "danger"
                updated_status = [
                    "Error persistente ❌" if s["index"] == error_id else dash.no_update
                    for s in all_status_ids
                ]

            return updated_status, msg, color, True

        except Exception as e:
            logger.error(f"Error reintentando actualización del error {error_id}: {e}")
            return dash.no_update, f"Error reintentando actualización: {e}", "danger", True