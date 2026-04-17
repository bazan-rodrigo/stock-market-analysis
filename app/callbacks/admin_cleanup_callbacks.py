from dash import Input, Output, State, callback, no_update


@callback(
    Output("cleanup-modal", "is_open"),
    Output("cleanup-check", "value"),
    Input("cleanup-btn-open", "n_clicks"),
    Input("cleanup-btn-cancel", "n_clicks"),
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
    Output("cleanup-alert", "children"),
    Output("cleanup-alert", "is_open"),
    Output("cleanup-alert", "color"),
    Input("cleanup-btn-confirm", "n_clicks"),
    prevent_initial_call=True,
)
def run_cleanup(_):
    from sqlalchemy import text
    from app.database import engine
    from app.pages.admin_cleanup import _TABLES_INFO

    tables = [t for t, _ in _TABLES_INFO]
    try:
        with engine.begin() as conn:
            conn.execute(text("SET FOREIGN_KEY_CHECKS = 0"))
            total = 0
            for table in tables:
                result = conn.execute(text(f"DELETE FROM `{table}`"))
                total += result.rowcount
            conn.execute(text("SET FOREIGN_KEY_CHECKS = 1"))
        return f"Limpieza completada. {total} filas eliminadas.", True, "success"
    except Exception as exc:
        return f"Error durante la limpieza: {exc}", True, "danger"
