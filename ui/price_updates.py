# -*- coding: utf-8 -*-
"""
UI: price_updates.py
--------------------------------------------------------
Pantalla unificada de actualización de precios,
con indicador de progreso, fecha de última actualización,
tabla de errores con estado dinámico y reintentos.
"""

from dash import html, Input, Output, State, ctx
import dash_bootstrap_components as dbc
from flask_login import current_user
from core.logging_config import get_logger
from services import price_updater, failed_updates
import dash
from datetime import datetime

logger = get_logger(__name__)


# ==========================================================
# LAYOUT PRINCIPAL
# ==========================================================
def price_updates_layout():
    """Renderiza la pantalla de actualización de precios."""
    if not current_user.is_authenticated or current_user.role != "admin":
        return dbc.Alert("Acceso restringido a administradores.", color="danger")

    last = price_updater.get_last_update_date()
    last_str = (
        f"📅 Última actualización: {last.strftime('%Y-%m-%d %H:%M:%S')}"
        if last else "📅 Sin registros previos de actualización"
    )

    return html.Div([
        html.H4("Actualización de precios"),
        html.Hr(),

        dbc.Row([
            dbc.Col(
                dbc.Button("🔄 Actualizar todos los precios", id="btn-update-all", color="primary"),
                width="auto"
            ),
            dbc.Col(html.Div(id="update-status", style={"marginLeft": "15px"}))
        ], className="mb-3"),

        html.Div(id="progress-container", style={"marginBottom": "10px"}),

        html.Div(id="last-update-display", children=last_str, style={"marginBottom": "10px"}),

        html.H5("Errores recientes"),
        dbc.Alert(id="failed-msg", is_open=False, color="info"),
        html.Div(id="failed-table-container"),
    ])


# ==========================================================
# CALLBACKS
# ==========================================================
def register_price_updates_callbacks(app):
    """Registra los callbacks de la pantalla de actualización de precios."""

    # ------------------------------------------------------
    # Mostrar spinner mientras corre la actualización
    # ------------------------------------------------------
    @app.callback(
        Output("progress-container", "children"),
        Input("btn-update-all", "n_clicks"),
        prevent_initial_call=True
    )
    def show_spinner(_):
        """Muestra un spinner mientras se ejecuta la actualización."""
        spinner = dbc.Spinner(size="sm", color="primary", children=[
            html.Span(" Actualizando precios... ", style={"marginLeft": "10px"})
        ])
        return spinner

    # ------------------------------------------------------
    # Ejecutar actualización global
    # ------------------------------------------------------
    @app.callback(
        Output("update-status", "children"),
        Output("last-update-display", "children"),
        Output("failed-table-container", "children"),
        Output("progress-container", "children"),
        Input("btn-update-all", "n_clicks"),
        prevent_initial_call=True
    )
    def update_all_prices(_):
        """Ejecuta actualización de todos los activos y refresca tabla de errores."""
        try:
            updated = price_updater.update_all_assets(run_type="manual")
            last = price_updater.get_last_update_date()
            msg = f"✅ Se actualizaron los precios de {updated} activos correctamente."
            last_str = f"📅 Última actualización: {last.strftime('%Y-%m-%d %H:%M:%S')}" if last else "📅 Sin registros previos"
            logger.info(msg)

            rows = failed_updates.list_failed_updates()
            if not rows:
                failed_table = dbc.Alert("✅ Sin errores registrados.", color="success")
            else:
                failed_table = _render_failed_updates_table(rows)

            # Vacía el spinner al finalizar
            return msg, last_str, failed_table, html.Span("")

        except Exception as e:
            logger.error(f"Error global de actualización: {e}")
            return f"❌ Error global: {e}", dash.no_update, dash.no_update, html.Span("")

    # ------------------------------------------------------
    # Reintentar actualización individual con estado dinámico
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
    def retry_failed_update(_, all_status_ids):
        """Reintenta actualización individual y actualiza el estado dinámico."""
        if not ctx.triggered_id:
            raise dash.exceptions.PreventUpdate

        error_id = ctx.triggered_id["index"]

        try:
            errors = failed_updates.list_failed_updates()
            err = next((e for e in errors if str(e["id"]) == str(error_id)), None)
            if not err:
                raise ValueError("No se encontró el registro del error.")
            symbol = err["symbol"]

            logger.info(f"🔁 Reintentando actualización de {symbol} (error_id={error_id})...")
            ok = price_updater.update_single_asset(symbol)

            if ok:
                failed_updates.mark_failed_update_resolved(error_id)
                msg, color = f"✅ {symbol} actualizado correctamente.", "success"
                updated_status = [
                    "🟢 Reintentado" if s["index"] == error_id else dash.no_update
                    for s in all_status_ids
                ]
            else:
                msg, color = f"❌ {symbol} no pudo actualizarse.", "danger"
                updated_status = [
                    "🔴 Error persistente" if s["index"] == error_id else dash.no_update
                    for s in all_status_ids
                ]

            return updated_status, msg, color, True

        except Exception as e:
            logger.error(f"Error reintentando actualización: {e}")
            return dash.no_update, f"Error reintentando: {e}", "danger", True


# ==========================================================
# TABLA DE ERRORES
# ==========================================================
def _render_failed_updates_table(rows):
    """Crea una tabla de errores con columna de estado dinámico y botón de reintento."""
    header = html.Thead(html.Tr([
        html.Th("ID"), html.Th("Símbolo"), html.Th("Fuente"),
        html.Th("Mensaje"), html.Th("Modo"), html.Th("Fecha"),
        html.Th("Estado"), html.Th("Acción")
    ]))

    body = html.Tbody([
        html.Tr([
            html.Td(r["id"]),
            html.Td(r["symbol"]),
            html.Td(r["source"]),
            html.Td(r["error_message"]),
            html.Td(r["run_type"]),
            html.Td(r["timestamp"]),
            html.Td("🟡 Pendiente", id={"type": "cell-status", "index": r["id"]}),
            html.Td(
                dbc.Button(
                    "Reintentar",
                    id={"type": "btn-retry-error", "index": r["id"]},
                    color="warning", size="sm"
                )
            )
        ]) for r in rows
    ])

    return dbc.Table([header, body], bordered=True, hover=True, striped=True)