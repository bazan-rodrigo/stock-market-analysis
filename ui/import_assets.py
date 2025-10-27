# -*- coding: utf-8 -*-
"""
Pantalla de importacion masiva de activos (solo admin).
Permite subir un archivo CSV con multiples activos para registrar en la base.
Usa la capa de servicios (asset_service).
"""

import io
import pandas as pd
from dash import html, dcc, Input, Output, State
import dash_bootstrap_components as dbc
from flask_login import current_user
from core.logging_config import get_logger
from services import asset_service

logger = get_logger()

# ==========================================================
# LAYOUT
# ==========================================================
def import_assets_layout():
    """Layout principal de la pantalla de importacion de activos."""
    if not current_user.is_authenticated or current_user.role != "admin":
        return dbc.Alert("Acceso restringido a usuarios administradores.", color="danger")

    return html.Div([
        html.H4("Importacion masiva de activos"),
        html.Hr(),
        html.P("Suba un archivo CSV con las siguientes columnas obligatorias:"),
        html.Ul([
            html.Li("symbol"),
            html.Li("name"),
            html.Li("source_code"),
            html.Li("source_symbol"),
            html.Li("country"),
            html.Li("currency"),
        ]),
        dcc.Upload(
            id="upload-assets-file",
            children=html.Div(["Arrastre un archivo CSV o haga clic para seleccionar."]),
            style={
                "width": "100%", "height": "80px", "lineHeight": "80px",
                "borderWidth": "1px", "borderStyle": "dashed",
                "borderRadius": "5px", "textAlign": "center", "margin": "10px",
            },
            multiple=False,
        ),
        dbc.Button("Procesar archivo", id="btn-process-assets", color="primary", className="mt-3"),
        html.Div(id="import-result", className="mt-4"),
    ])

# ==========================================================
# CALLBACKS
# ==========================================================
def register_import_assets_callbacks(app):
    """Registra los callbacks para la importacion masiva de activos."""

    @app.callback(
        Output("import-result", "children"),
        Input("btn-process-assets", "n_clicks"),
        State("upload-assets-file", "contents"),
        State("upload-assets-file", "filename"),
        prevent_initial_call=True
    )
    def process_uploaded_assets(n_clicks, file_content, filename):
        if not file_content:
            return dbc.Alert("No se ha cargado ningun archivo.", color="warning")

        try:
            # Extraer contenido del archivo
            content_type, content_string = file_content.split(",")
            decoded = io.BytesIO(base64.b64decode(content_string))
            df = pd.read_csv(decoded)

            required_cols = {"symbol", "name", "source_code", "source_symbol", "country", "currency"}
            if not required_cols.issubset(set(df.columns)):
                return dbc.Alert("El archivo CSV no tiene todas las columnas requeridas.", color="danger")

            total = len(df)
            success, failed = 0, 0
            errors = []

            # Procesar cada fila
            for _, row in df.iterrows():
                try:
                    msg, ok = asset_service.create_asset(
                        symbol=row["symbol"],
                        name=row["name"],
                        source_id=asset_service.get_source_id_by_code(row["source_code"]),
                        source_symbol=row["source_symbol"],
                        country=row["country"],
                        currency=row["currency"],
                    )
                    if ok:
                        success += 1
                    else:
                        failed += 1
                        errors.append(msg)
                except Exception as e:
                    failed += 1
                    errors.append(str(e))
                    logger.error(f"Error importando asset: {e}")

            summary = html.Div([
                html.H5("Resumen de importacion"),
                html.Ul([
                    html.Li(f"Total de registros: {total}"),
                    html.Li(f"Importados correctamente: {success}"),
                    html.Li(f"Fallidos: {failed}"),
                ]),
            ])

            if failed > 0:
                summary.children.append(html.H6("Errores detectados:"))
                summary.children.append(html.Ul([html.Li(e) for e in errors[:10]]))  # muestra max 10 errores

            color = "success" if failed == 0 else "warning"
            return dbc.Alert(summary, color=color, style={"whiteSpace": "pre-wrap"})

        except Exception as e:
            logger.exception(f"Error procesando importacion masiva: {e}")
            return dbc.Alert(f"Error al procesar el archivo: {e}", color="danger")