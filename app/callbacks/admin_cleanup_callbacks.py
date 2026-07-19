import threading

from dash import Input, Output, callback, html, no_update

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
    from app.services import db_compat

    tables = [t for t, _ in _TABLES_INFO]
    _state.update({"running": True, "result": None, "error": None})

    def _run():
        try:
            with engine.begin() as conn:
                # Desactivar el chequeo de FKs permite borrar en cualquier
                # orden — solo existe como knob de sesión en MySQL/MariaDB.
                # En PG/sqlite se borra igual: _TABLES_INFO son tablas hijas
                # (nada las referencia), el orden no importa.
                if db_compat.is_mysql(engine):
                    conn.execute(text("SET FOREIGN_KEY_CHECKS = 0"))
                total = 0
                for table in tables:
                    q = db_compat.quote_ident(engine, table)
                    result = conn.execute(text(f"DELETE FROM {q}"))
                    total += result.rowcount
                if db_compat.is_mysql(engine):
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


# ── Recuperar espacio (VACUUM FULL / OPTIMIZE TABLE) ──────────────────────────
_vac_state = {"running": False, "result": None, "error": None}


@callback(
    Output("vacuum-interval", "disabled"),
    Output("vacuum-progress", "style"),
    Output("vacuum-btn",      "disabled"),
    Input("vacuum-btn", "n_clicks"),
    prevent_initial_call=True,
)
def run_vacuum(_):
    from app.services import maintenance_service

    _vac_state.update({"running": True, "result": None, "error": None})

    def _run():
        try:
            res = maintenance_service.vacuum_bloat_tables()
            freed_mb = res["freed_bytes"] / 1024 / 1024
            n = len(res["tables"])
            if res["dialect"] == "sqlite":
                _vac_state["result"] = "VACUUM de la base completado (sqlite)."
            else:
                _vac_state["result"] = (
                    f"Espacio recuperado: {freed_mb:.1f} MB en {n} tablas "
                    f"({res['dialect']}).")
        except Exception as exc:
            _vac_state["error"] = f"Error al recuperar espacio: {exc}"
        finally:
            _vac_state["running"] = False

    threading.Thread(target=_run, daemon=True).start()
    return False, {"display": "block"}, True


@callback(
    Output("vacuum-progress", "style",    allow_duplicate=True),
    Output("vacuum-interval", "disabled", allow_duplicate=True),
    Output("vacuum-alert",    "children"),
    Output("vacuum-alert",    "is_open"),
    Output("vacuum-alert",    "color"),
    Output("vacuum-btn",      "disabled", allow_duplicate=True),
    Input("vacuum-interval", "n_intervals"),
    prevent_initial_call=True,
)
def poll_vacuum(_):
    if _vac_state["running"]:
        return {"display": "block"}, False, no_update, no_update, no_update, True

    if _vac_state["error"]:
        return {"display": "none"}, True, _vac_state["error"], True, "danger", False

    if _vac_state["result"]:
        return {"display": "none"}, True, _vac_state["result"], True, "success", False

    return no_update, no_update, no_update, no_update, no_update, no_update


# ── Uso de espacio en disco (solo lectura) ────────────────────────────────────

def _pct(part: int, total: int) -> str:
    return f"{100 * part / total:.1f}%" if total else "—"


@callback(
    Output("dbsize-content", "children"),
    Input("dbsize-refresh", "n_clicks"),
)
def render_db_size(_n):
    import dash_bootstrap_components as dbc
    from app.services import maintenance_service as ms

    try:
        rep = ms.database_size_report()
    except Exception as exc:  # noqa: BLE001 — mostrar el error, no romper la página
        return dbc.Alert(f"No se pudo leer el uso de espacio: {exc}",
                         color="danger", className="mb-0")

    total = rep["total_bytes"]
    fam_rows = [
        html.Tr([
            html.Td(r["family"]),
            html.Td(r["count"], className="text-end"),
            html.Td(ms.format_bytes(r["bytes"]), className="text-end"),
            html.Td(_pct(r["bytes"], total), className="text-end"),
        ])
        for r in rep["by_family"]
    ]
    tbl_rows = [
        html.Tr([
            html.Td(name),
            html.Td(ms.format_bytes(size), className="text-end"),
        ])
        for name, size in rep["tables"]
    ]

    return html.Div([
        html.P([
            "Tamaño total de la base: ",
            html.Strong(ms.format_bytes(total)),
            html.Span(f"  ({rep['dialect']})", className="text-muted small"),
        ], className="mb-2"),

        html.H6("Por familia", className="mb-1"),
        dbc.Table([
            html.Thead(html.Tr([
                html.Th("Familia"),
                html.Th("Tablas", className="text-end"),
                html.Th("Tamaño", className="text-end"),
                html.Th("% total", className="text-end"),
            ])),
            html.Tbody(fam_rows),
        ], bordered=True, size="sm", hover=True, className="w-auto mb-4"),

        html.H6("Tablas más grandes", className="mb-1"),
        dbc.Table([
            html.Thead(html.Tr([
                html.Th("Tabla"),
                html.Th("Tamaño", className="text-end"),
            ])),
            html.Tbody(tbl_rows),
        ], bordered=True, size="sm", hover=True, className="w-auto"),
    ])
