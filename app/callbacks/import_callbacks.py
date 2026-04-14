import base64

from dash import Input, Output, State, callback, dcc, no_update

import app.services.import_service as svc


def _logs_to_rows(logs) -> list[dict]:
    return [
        {
            "ticker": l.ticker,
            "status": l.status,
            "detail": l.detail or "",
            "attempted_at": str(l.attempted_at)[:19],
        }
        for l in logs
    ]


@callback(
    Output("import-log-table", "data"),
    Input("import-log-table", "id"),
)
def load_import_logs(_):
    return _logs_to_rows(svc.get_import_logs())


@callback(
    Output("import-download-template", "data"),
    Input("import-btn-template", "n_clicks"),
    prevent_initial_call=True,
)
def download_template(_):
    content = svc.generate_template()
    return dcc.send_bytes(content, "template_activos.xlsx")


@callback(
    Output("import-file-store", "data"),
    Output("import-filename", "children"),
    Output("import-btn-run", "disabled"),
    Input("import-upload", "contents"),
    State("import-upload", "filename"),
    prevent_initial_call=True,
)
def store_uploaded_file(contents, filename):
    if contents is None:
        return None, "", True
    return contents, f"Archivo seleccionado: {filename}", False


@callback(
    Output("import-log-table", "data", allow_duplicate=True),
    Output("import-alert", "children"),
    Output("import-alert", "is_open"),
    Output("import-alert", "color"),
    Input("import-btn-run", "n_clicks"),
    State("import-file-store", "data"),
    prevent_initial_call=True,
)
def run_import(_, file_data):
    if not file_data:
        return no_update, "No hay archivo cargado.", True, "warning"
    try:
        # Decodificar el contenido base64 de dcc.Upload
        _header, encoded = file_data.split(",", 1)
        file_bytes = base64.b64decode(encoded)
        results = svc.import_from_excel(file_bytes)
        imported = sum(1 for r in results if r["status"] == "imported")
        skipped = sum(1 for r in results if r["status"] == "skipped")
        errors = sum(1 for r in results if r["status"] == "error")
        msg = f"Procesados {len(results)}: {imported} importados, {skipped} omitidos, {errors} con error."
        return _logs_to_rows(svc.get_import_logs()), msg, True, "info"
    except Exception as exc:
        return no_update, str(exc), True, "danger"


@callback(
    Output("import-log-table", "data", allow_duplicate=True),
    Input("import-btn-clear", "n_clicks"),
    prevent_initial_call=True,
)
def clear_logs(_):
    svc.clear_import_logs()
    return []
