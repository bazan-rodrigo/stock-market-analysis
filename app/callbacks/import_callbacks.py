import base64
import threading

from dash import Input, Output, State, callback, dcc, no_update

import app.services.import_service as svc

_state = {"running": False, "current": 0, "total": 0, "results": None, "error": None}


def _logs_to_rows(logs) -> list[dict]:
    return [
        {
            "ticker": log.ticker,
            "status": log.status,
            "detail": log.detail or "",
            "attempted_at": str(log.attempted_at)[:19],
        }
        for log in logs
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
    return dcc.send_bytes(svc.generate_template(), "template_activos.xlsx")


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
    Output("import-interval",  "disabled"),
    Output("import-progress",  "style"),
    Output("import-alert",     "children"),
    Output("import-alert",     "is_open"),
    Output("import-alert",     "color"),
    Input("import-btn-run", "n_clicks"),
    State("import-file-store", "data"),
    prevent_initial_call=True,
)
def run_import(_, file_data):
    if not file_data:
        return True, {"display": "none"}, "No hay archivo cargado.", True, "warning"

    _header, encoded = file_data.split(",", 1)
    file_bytes = base64.b64decode(encoded)
    _state.update({"running": True, "current": 0, "total": 0, "results": None, "error": None})

    def _run():
        def _progress(current, total):
            _state["current"] = current
            _state["total"]   = total
        try:
            _state["results"] = svc.import_from_excel(file_bytes, progress_cb=_progress)
        except Exception as exc:
            _state["error"] = str(exc)
        finally:
            _state["running"] = False

    threading.Thread(target=_run, daemon=True).start()
    return False, {"display": "block"}, "", False, "info"


@callback(
    Output("import-progress",  "value"),
    Output("import-progress",  "label"),
    Output("import-progress",  "style",    allow_duplicate=True),
    Output("import-interval",  "disabled", allow_duplicate=True),
    Output("import-log-table", "data",     allow_duplicate=True),
    Output("import-alert",     "children", allow_duplicate=True),
    Output("import-alert",     "is_open",  allow_duplicate=True),
    Output("import-alert",     "color",    allow_duplicate=True),
    Input("import-interval", "n_intervals"),
    prevent_initial_call=True,
)
def poll_import(_):
    if _state["running"]:
        current = _state["current"]
        total   = _state["total"] or 1
        pct     = int(current / total * 100)
        label   = f"{current} / {_state['total']}" if _state["total"] else "Iniciando..."
        return pct, label, {"display": "block"}, False, no_update, no_update, no_update, no_update

    if _state["error"]:
        return 0, "", {"display": "none"}, True, no_update, _state["error"], True, "danger"

    results = _state["results"] or []
    imported = sum(1 for r in results if r["status"] == "imported")
    skipped  = sum(1 for r in results if r["status"] == "skipped")
    errors   = sum(1 for r in results if r["status"] == "error")
    msg = f"Procesados {len(results)}: {imported} importados, {skipped} omitidos, {errors} con error."
    color = "success" if not errors else "warning"
    return 100, "Completo", {"display": "none"}, True, _logs_to_rows(svc.get_import_logs()), msg, True, color


@callback(
    Output("import-log-table", "data", allow_duplicate=True),
    Input("import-btn-clear", "n_clicks"),
    prevent_initial_call=True,
)
def clear_logs(_):
    svc.clear_import_logs()
    return []
