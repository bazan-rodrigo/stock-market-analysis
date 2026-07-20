import threading

from dash import Input, Output, State, callback, no_update
from flask_login import current_user

import app.services.fundamental_service as svc
from app.services import run_lock_service as _rl

_state = {
    "running": False, "current": 0, "total": 0,
    "msg": "", "error": None, "has_errors": False, "phase": "",
}

# Estas operaciones escriben las MISMAS tablas de ratios que la actualización de
# precios y el Centro de Datos, así que comparten su lock persistido
# HEAVY_WRITE. Antes solo se coordinaban con el flag en memoria _state["running"],
# que es por-proceso: con multi-worker (o contra el scheduler nocturno) dos
# corridas podían escribir en paralelo. "Actualizar seleccionados" ni siquiera
# miraba el flag.


def _launch_locked_bg(run_fn) -> bool:
    """Toma HEAVY_WRITE y corre run_fn en un thread con heartbeat; libera al
    terminar. Devuelve False si otra corrida pesada ya tiene el lock."""
    token = _rl.guarded_acquire(_rl.HEAVY_WRITE)
    if token is None:
        return False

    def _wrapped():
        try:
            with _rl.heartbeating(_rl.HEAVY_WRITE, token):
                run_fn()
        finally:
            _state["running"] = False

    threading.Thread(target=_wrapped, daemon=True).start()
    return True


@callback(
    Output("fund-upd-table", "data"),
    Input("fund-upd-table", "id"),
)
def load_log(_):
    return svc.get_fundamentals_log()


@callback(
    Output("fund-upd-btn-one", "disabled"),
    Output("fund-upd-btn-redownload-selected", "disabled"),
    Input("fund-upd-table", "selected_rows"),
)
def toggle_btn_one(sel):
    return not bool(sel), not bool(sel)


# ── Reintentar fallidos ────────────────────────────────────────────────────────

@callback(
    Output("fund-upd-interval",  "disabled"),
    Output("fund-upd-progress",  "style"),
    Output("fund-upd-btn-retry", "disabled"),
    Output("fund-upd-alert",     "children"),
    Output("fund-upd-alert",     "is_open"),
    Output("fund-upd-alert",     "color"),
    Output("fund-upd-table",     "data",    allow_duplicate=True),
    Input("fund-upd-btn-retry",  "n_clicks"),
    Input("fund-upd-btn-clear",  "n_clicks"),
    prevent_initial_call=True,
)
def handle_buttons(n_retry, n_clear):
    from dash import ctx
    if not current_user.is_authenticated or not current_user.is_admin:
        return no_update, no_update, no_update, no_update, no_update, no_update, no_update

    tid = ctx.triggered_id
    _no_prog = {"display": "none"}

    if tid == "fund-upd-btn-clear":
        from app.database import get_session
        from app.models import FundamentalUpdateLog
        s = get_session()
        s.query(FundamentalUpdateLog).delete()
        s.commit()
        return True, _no_prog, False, "Log limpiado.", True, "success", svc.get_fundamentals_log()

    if tid == "fund-upd-btn-retry":
        if _state["running"]:
            return True, _no_prog, True, "Ya hay una actualización en curso.", True, "warning", no_update

        _state.update({"running": True, "current": 0, "total": 0,
                        "msg": "", "error": None, "has_errors": False, "phase": "Iniciando..."})

        def _run():  # noqa: E306  (definido antes de tomar el lock a propósito)
            def _cb(cur, tot, label=""):
                _state["current"] = cur
                _state["total"]   = tot
                _state["phase"]   = label
            try:
                from app.database import get_session
                from app.models import Asset, FundamentalUpdateLog as FUL
                s = get_session()
                failed_ids = {r.asset_id for r in s.query(FUL).filter_by(success=False).all()}
                assets = s.query(Asset).filter(
                    Asset.fundamental_source_id.isnot(None),
                    Asset.id.in_(failed_ids),
                ).all()
                total = len(assets)
                ok, errs = 0, []
                for i, a in enumerate(assets, 1):
                    _cb(i, total)
                    try:
                        svc.update_asset_fundamentals(a.id, force=True)
                        ok += 1
                    except Exception as exc:
                        errs.append({"ticker": a.ticker, "error": str(exc)})
                summary = {"total": total, "success": ok, "errors": errs}
                _state["has_errors"] = bool(summary["errors"])
                _state["msg"] = (
                    f"Completado: {summary['success']}/{summary['total']} exitosos, "
                    f"{len(summary['errors'])} errores."
                )
            except Exception as exc:
                _state["error"] = str(exc)
            # _state["running"] lo baja _launch_locked_bg al terminar el thread.

        if not _launch_locked_bg(_run):
            _state["running"] = False
            return (True, _no_prog, True,
                    "Hay otra actualización pesada en curso (precios, "
                    "fundamentales o Centro de Datos). Esperá a que termine.",
                    True, "warning", no_update)
        return False, {"display": "block"}, True, "", False, "info", no_update

    return no_update, no_update, no_update, no_update, no_update, no_update, no_update


# ── Polling del progreso ──────────────────────────────────────────────────────

@callback(
    Output("fund-upd-progress",  "value",             allow_duplicate=True),
    Output("fund-upd-progress",  "label",             allow_duplicate=True),
    Output("fund-upd-progress",  "style",             allow_duplicate=True),
    Output("fund-upd-interval",  "disabled",          allow_duplicate=True),
    Output("fund-upd-table",     "data",              allow_duplicate=True),
    Output("fund-upd-alert",     "children",          allow_duplicate=True),
    Output("fund-upd-alert",     "is_open",           allow_duplicate=True),
    Output("fund-upd-alert",     "color",             allow_duplicate=True),
    Output("fund-upd-btn-retry", "disabled",          allow_duplicate=True),
    Input("fund-upd-interval", "n_intervals"),
    prevent_initial_call=True,
)
def poll_progress(_):
    _show = {"display": "block"}
    _hide = {"display": "none"}

    if _state["running"]:
        cur   = _state["current"]
        tot   = _state["total"] or 1
        pct   = int(cur / tot * 100)
        label = f"{cur} / {_state['total']}" if _state["total"] else (_state.get("phase") or "Iniciando...")
        return pct, label, _show, False, no_update, no_update, no_update, no_update, True

    if _state["error"]:
        return 0, "", _hide, True, no_update, _state["error"], True, "danger", False

    msg   = _state["msg"]
    color = "success" if not _state.get("has_errors") else "warning"
    return 100, "Completo", _hide, True, svc.get_fundamentals_log(), msg, True, color, False


# ── Actualizar seleccionados ────────────────────────────────────────────────────

@callback(
    Output("fund-upd-alert",  "children", allow_duplicate=True),
    Output("fund-upd-alert",  "is_open",  allow_duplicate=True),
    Output("fund-upd-alert",  "color",    allow_duplicate=True),
    Output("fund-upd-table",  "data",     allow_duplicate=True),
    Input("fund-upd-btn-one", "n_clicks"),
    State("fund-upd-table",   "selected_rows"),
    State("fund-upd-table",   "data"),
    prevent_initial_call=True,
)
def update_one(_, sel_rows, data):
    if not current_user.is_authenticated or not current_user.is_admin:
        return no_update, no_update, no_update, no_update
    if not sel_rows:
        return no_update, no_update, no_update, no_update

    # Corre síncrono en el hilo del request, pero escribe las tablas de ratios
    # → toma el mismo lock que el resto. Antes no miraba nada y podía pisar una
    # corrida de precios o del scheduler.
    token = _rl.guarded_acquire(_rl.HEAVY_WRITE)
    if token is None:
        return ("Hay otra actualización pesada en curso. Esperá a que termine.",
                True, "warning", no_update)

    from app.database import get_session
    from app.models import Asset
    tickers = [data[i]["ticker"] for i in sel_rows]
    successes, errors = [], []
    try:
        for ticker in tickers:
            asset = get_session().query(Asset).filter_by(ticker=ticker).first()
            if not asset:
                errors.append(f"{ticker}: no encontrado")
                continue
            try:
                svc.update_asset_fundamentals(asset.id, force=True)
                successes.append(ticker)
            except Exception as exc:
                errors.append(f"{ticker}: {exc}")
    finally:
        _rl.release(_rl.HEAVY_WRITE, token)

    if not errors:
        msg, color = f"{len(successes)} actualizados correctamente.", "success"
    elif not successes:
        msg, color = f"{len(errors)} errores: {', '.join(errors[:5])}", "danger"
    else:
        msg, color = (f"{len(successes)} actualizados, {len(errors)} errores: "
                      f"{', '.join(errors[:5])}"), "warning"

    return msg, True, color, svc.get_fundamentals_log()


# ── Redescargar seleccionados ───────────────────────────────────────────────────

@callback(
    Output("fund-upd-redownload-selected-modal", "is_open"),
    Input("fund-upd-btn-redownload-selected", "n_clicks"),
    Input("fund-upd-btn-redownload-selected-confirm", "n_clicks"),
    Input("fund-upd-btn-redownload-selected-cancel", "n_clicks"),
    prevent_initial_call=True,
)
def toggle_redownload_selected_modal(n_open, n_confirm, n_cancel):
    from dash import ctx
    return ctx.triggered_id == "fund-upd-btn-redownload-selected"


@callback(
    Output("fund-upd-redownload-selected-modal", "is_open", allow_duplicate=True),
    Output("fund-upd-interval", "disabled", allow_duplicate=True),
    Output("fund-upd-progress", "style",    allow_duplicate=True),
    Input("fund-upd-btn-redownload-selected-confirm", "n_clicks"),
    State("fund-upd-table", "selected_rows"),
    State("fund-upd-table", "data"),
    prevent_initial_call=True,
)
def redownload_selected(_, sel_rows, data):
    if not current_user.is_authenticated or not current_user.is_admin:
        return no_update, no_update, no_update
    if not sel_rows:
        return False, True, {"display": "none"}
    if _state["running"]:
        return False, True, {"display": "none"}

    from app.database import get_session
    from app.models import Asset
    tickers   = [data[i]["ticker"] for i in sel_rows]
    s         = get_session()
    asset_ids = [a.id for a in (s.query(Asset).filter_by(ticker=t).first() for t in tickers) if a is not None]

    _state.update({"running": True, "current": 0, "total": 0,
                    "msg": "", "error": None, "has_errors": False, "phase": "Iniciando..."})

    def _run():
        def _cb(cur, tot, label=""):
            _state["current"] = cur
            _state["total"]   = tot
            _state["phase"]   = label
        try:
            summary = svc.redownload_all_fundamentals(asset_ids=asset_ids, progress_cb=_cb)
            _state["has_errors"] = bool(summary["errors"])
            _state["msg"] = (
                f"Redescargar completo (seleccionados): {summary['success']}/{summary['total']} exitosos, "
                f"{len(summary['errors'])} errores."
            )
        except Exception as exc:
            _state["error"] = str(exc)
        # _state["running"] lo baja _launch_locked_bg al terminar el thread.

    if not _launch_locked_bg(_run):
        # Otra corrida pesada tiene el lock: no arranca, avisa vía error.
        _state.update({"running": False,
                       "error": "Hay otra actualización pesada en curso "
                                "(precios, fundamentales o Centro de Datos). "
                                "Esperá a que termine."})
        return False, False, {"display": "none"}
    return False, False, {"display": "block"}  # cierra modal, activa interval
