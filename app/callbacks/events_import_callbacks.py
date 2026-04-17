import base64
import threading

from dash import Input, Output, State, callback, dcc, no_update

import app.services.events_import_service as svc

_state = {"running": False, "current": 0, "total": 0, "results": None, "error": None}


@callback(
    Output("ev-import-download", "data"),
    Input("ev-import-btn-template", "n_clicks"),
    prevent_initial_call=True,
)
def download_template(_):
    return dcc.send_bytes(svc.generate_template(), "template_eventos.xlsx")


@callback(
    Output("ev-import-file-store", "data"),
    Output("ev-import-filename",   "children"),
    Output("ev-import-btn-run",    "disabled"),
    Input("ev-import-upload", "contents"),
    State("ev-import-upload", "filename"),
    prevent_initial_call=True,
)
def store_file(contents, filename):
    if contents is None:
        return no_update, no_update, True
    return contents, filename, False


@callback(
    Output("ev-import-interval",  "disabled"),
    Output("ev-import-progress",  "style"),
    Output("ev-import-alert",     "children"),
    Output("ev-import-alert",     "is_open"),
    Output("ev-import-alert",     "color"),
    Input("ev-import-btn-run", "n_clicks"),
    State("ev-import-file-store", "data"),
    prevent_initial_call=True,
)
def run_import(_, contents):
    if not contents:
        return True, {"display": "none"}, "No hay archivo seleccionado.", True, "warning"

    _, b64 = contents.split(",", 1)
    file_bytes = base64.b64decode(b64)
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
    Output("ev-import-progress",   "value"),
    Output("ev-import-progress",   "label"),
    Output("ev-import-progress",   "style",    allow_duplicate=True),
    Output("ev-import-interval",   "disabled", allow_duplicate=True),
    Output("ev-import-log-table",  "data",     allow_duplicate=True),
    Output("ev-import-alert",      "children", allow_duplicate=True),
    Output("ev-import-alert",      "is_open",  allow_duplicate=True),
    Output("ev-import-alert",      "color",    allow_duplicate=True),
    Input("ev-import-interval", "n_intervals"),
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
    errors   = sum(1 for r in results if r["status"] == "error")
    msg = f"{imported} importados, {errors} errores."
    color = "success" if not errors else "warning"
    return 100, "Completo", {"display": "none"}, True, results, msg, True, color


@callback(
    Output("ev-import-log-table", "data", allow_duplicate=True),
    Input("ev-import-btn-clear", "n_clicks"),
    prevent_initial_call=True,
)
def clear_results(_):
    return []
