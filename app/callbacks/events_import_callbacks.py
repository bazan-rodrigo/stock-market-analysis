import base64

from dash import Input, Output, State, callback, dcc, no_update

import app.services.events_import_service as svc


@callback(
    Output("ev-import-download", "data"),
    Input("ev-import-btn-template", "n_clicks"),
    prevent_initial_call=True,
)
def download_template(_):
    return dcc.send_bytes(svc.generate_template(), "template_eventos.xlsx")


@callback(
    Output("ev-import-file-store", "data"),
    Output("ev-import-filename", "children"),
    Output("ev-import-btn-run", "disabled"),
    Input("ev-import-upload", "contents"),
    State("ev-import-upload", "filename"),
    prevent_initial_call=True,
)
def store_file(contents, filename):
    if contents is None:
        return no_update, no_update, True
    return contents, filename, False


@callback(
    Output("ev-import-log-table", "data"),
    Output("ev-import-alert", "children"),
    Output("ev-import-alert", "is_open"),
    Output("ev-import-alert", "color"),
    Input("ev-import-btn-run", "n_clicks"),
    State("ev-import-file-store", "data"),
    prevent_initial_call=True,
)
def run_import(_, contents):
    if not contents:
        return no_update, "No hay archivo seleccionado.", True, "warning"
    try:
        _, b64 = contents.split(",", 1)
        file_bytes = base64.b64decode(b64)
        results = svc.import_from_excel(file_bytes)
        imported = sum(1 for r in results if r["status"] == "imported")
        errors   = sum(1 for r in results if r["status"] == "error")
        msg = f"{imported} importados, {errors} errores."
        color = "success" if errors == 0 else "warning"
        return results, msg, True, color
    except Exception as exc:
        return no_update, str(exc), True, "danger"


@callback(
    Output("ev-import-log-table", "data", allow_duplicate=True),
    Input("ev-import-btn-clear", "n_clicks"),
    prevent_initial_call=True,
)
def clear_results(_):
    return []
