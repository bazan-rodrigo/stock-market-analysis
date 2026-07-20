import threading

from dash import Input, Output, callback, html, no_update

from app.services import run_lock_service as _rl

_state = {"running": False, "result": None, "error": None}

_BUSY = ("Hay otra operación pesada en curso (Centro de Datos, precios o la "
         "corrida nocturna). Esperá a que termine antes de lanzar esta.")


def _launch_locked(state, work, ok_msg, err_prefix) -> bool:
    """Toma el lock HEAVY_WRITE y corre `work()` en un thread daemon, con
    heartbeat mientras dura (heartbeating libera el lock al salir).

    Las dos operaciones de esta pantalla tocan las MISMAS tablas que el
    pipeline, así que comparten su lock:
      - la limpieza las vacía: hacerlo con una corrida en curso deja la base a
        medias (peor: un `signal_eval_log` repoblado a medias hace que el
        delta SALTEE fechas ya limpiadas);
      - el VACUUM/OPTIMIZE toma lock exclusivo por tabla — en PostgreSQL
        ACCESS EXCLUSIVE, que bloquea hasta los SELECT — y dejaría al pipeline
        esperando (o al revés).
    Antes solo lo advertía un texto en pantalla, nada lo impedía.

    guarded_acquire es fail-open: sin la migración 0076 procede igual que
    antes. Devuelve False si otra corrida pesada tiene el lock; el estado
    queda con el mensaje de ocupado para que lo muestre el poll.
    """
    token = _rl.guarded_acquire(_rl.HEAVY_WRITE)
    if token is None:
        state.update({"running": False, "result": None, "error": _BUSY})
        return False

    state.update({"running": True, "result": None, "error": None})

    def _wrapped():
        try:
            with _rl.heartbeating(_rl.HEAVY_WRITE, token):
                res = work()
            state["result"] = ok_msg(res)
        except Exception as exc:  # noqa: BLE001 — se muestra en el alert
            state["error"] = f"{err_prefix}: {exc}"
        finally:
            state["running"] = False

    threading.Thread(target=_wrapped, daemon=True).start()
    return True


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
    from app.services import cleanup_service

    def _ok(res):
        return (f"Limpieza completada: {len(res['tables'])} tablas vaciadas. "
                "Regenerá los datos con «Recalcular completo» en el Centro de Datos.")

    started = _launch_locked(_state, cleanup_service.clean_data, _ok,
                             "Error durante la limpieza")
    if not started:
        # Interval habilitado igual: el poll ve running=False + error y muestra
        # el aviso de ocupado en el mismo alert que los errores.
        return False, {"display": "none"}, False
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

    def _ok(res):
        if res["dialect"] == "sqlite":
            return "VACUUM de la base completado (sqlite)."
        return (f"Espacio recuperado: {res['freed_bytes'] / 1024 / 1024:.1f} MB "
                f"en {len(res['tables'])} tablas ({res['dialect']}).")

    started = _launch_locked(_vac_state, maintenance_service.vacuum_bloat_tables,
                             _ok, "Error al recuperar espacio")
    if not started:
        return False, {"display": "none"}, False
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
