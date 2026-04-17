import threading

from dash import Input, Output, State, callback, no_update

_state = {"running": False, "result": None, "error": None}


@callback(
    Output("cleanup-modal", "is_open"),
    Output("cleanup-check", "value"),
    Input("cleanup-btn-open",    "n_clicks"),
    Input("cleanup-btn-cancel",  "n_clicks"),
    Input("cleanup-btn-confirm", "n_clicks"),
    prevent_initial_call=True,
)
def toggle_modal(n_open, n_cancel, n_confirm):
    from dash import ctx
    t = ctx.triggered_id
    if t == "cleanup-btn-open":
        return True, False
    return False, False


@callback(
    Output("cleanup-btn-confirm", "disabled"),
    Input("cleanup-check", "value"),
)
def toggle_confirm_btn(checked):
    return not bool(checked)


@callback(
    Output("cleanup-interval",  "disabled"),
    Output("cleanup-progress",  "style"),
    Output("cleanup-btn-open",  "disabled"),
    Input("cleanup-btn-confirm", "n_clicks"),
    prevent_initial_call=True,
)
def run_cleanup(_):
    from sqlalchemy import text
    from app.database import engine
    from app.pages.admin_cleanup import _TABLES_INFO

    tables = [t for t, _ in _TABLES_INFO]
    _state.update({"running": True, "result": None, "error": None})

    def _run():
        try:
            with engine.begin() as conn:
                conn.execute(text("SET FOREIGN_KEY_CHECKS = 0"))
                total = 0
                for table in tables:
                    result = conn.execute(text(f"DELETE FROM `{table}`"))
                    total += result.rowcount
                conn.execute(text("SET FOREIGN_KEY_CHECKS = 1"))
            _state["result"] = f"Limpieza completada. {total} filas eliminadas."
        except Exception as exc:
            _state["error"] = f"Error durante la limpieza: {exc}"
        finally:
            _state["running"] = False

    threading.Thread(target=_run, daemon=True).start()
    return False, {"display": "block"}, True


@callback(
    Output("cleanup-progress", "style",    allow_duplicate=True),
    Output("cleanup-interval", "disabled", allow_duplicate=True),
    Output("cleanup-alert",    "children"),
    Output("cleanup-alert",    "is_open"),
    Output("cleanup-alert",    "color"),
    Output("cleanup-btn-open", "disabled", allow_duplicate=True),
    Input("cleanup-interval", "n_intervals"),
    prevent_initial_call=True,
)
def poll_cleanup(_):
    if _state["running"]:
        return {"display": "block"}, False, no_update, no_update, no_update, True

    if _state["error"]:
        return {"display": "none"}, True, _state["error"], True, "danger", False

    if _state["result"]:
        return {"display": "none"}, True, _state["result"], True, "success", False

    return no_update, no_update, no_update, no_update, no_update, no_update
