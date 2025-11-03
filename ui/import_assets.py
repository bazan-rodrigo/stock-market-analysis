# ==========================================================
# CALLBACKS
# ==========================================================
from dash import callback, Input, Output, State, no_update
import base64, io, pandas as pd
import dash_bootstrap_components as dbc
from core.logging_config import get_logger
from services.asset_importer import import_asset

logger = get_logger(__name__)

@callback(
    Output("import-result", "children"),
    Input("btn-process-assets", "n_clicks"),
    State("upload-assets-file", "contents"),
    prevent_initial_call=True
)
def process_imported_assets(n_clicks, contents):
    """Procesa el archivo CSV subido y llama al servicio de importación masiva."""
    if not contents:
        return dbc.Alert("⚠️ No se cargó ningún archivo.", color="warning")

    try:
        # Decodificar CSV
        content_type, content_string = contents.split(",")
        decoded = base64.b64decode(content_string)
        df = pd.read_csv(io.StringIO(decoded.decode("utf-8")))

        # Validar columnas requeridas
        required_cols = ["symbol", "name", "source_code", "source_symbol", "country", "currency"]
        missing = [c for c in required_cols if c not in df.columns]
        if missing:
            return dbc.Alert(f"❌ Faltan columnas: {', '.join(missing)}", color="danger")

        stats = {"created": 0, "updated": 0, "skipped": 0, "failed": 0}
        errors = []

        # Procesar cada fila del archivo
        for _, row in df.iterrows():
            result = import_asset(row.to_dict())

            if result.get("success"):
                action = result.get("action")
                if action in stats:
                    stats[action] += 1
            else:
                stats["failed"] += 1
                errors.append(result.get("symbol", "desconocido"))

        # Construir mensaje resumen
        summary = [
            html.H5("✅ Importación completada"),
            html.Ul([
                html.Li(f"🆕 Nuevos activos: {stats['created']}"),
                html.Li(f"🔁 Actualizados: {stats['updated']}"),
                html.Li(f"⏸️ Sin cambios: {stats['skipped']}"),
                html.Li(f"❌ Errores: {stats['failed']}"),
            ])
        ]
        if errors:
            summary.append(html.P(f"Errores en símbolos: {', '.join(errors[:10])}"))

        logger.info(f"Importación masiva completada: {stats}")
        return dbc.Alert(summary, color="success")

    except Exception as e:
        logger.error(f"Error procesando el archivo: {e}")
        return dbc.Alert(f"❌ Error procesando archivo: {e}", color="danger")