import threading

from dash import Input, Output, State, callback, no_update
from flask_login import current_user

import app.services.fundamental_service as svc

_state = {
    "running": False, "current": 0, "total": 0,
    "msg": "", "error": None, "has_errors": False, "phase": "",
}


@callback(
    Output("fund-upd-table", "data"),
    Input("fund-upd-table", "id"),
)
def load_log(_):
    return svc.get_fundamentals_log()


@callback(
    Output("fund-upd-btn-one", "disabled"),
    Input("fund-upd-table", "selected_rows"),
)
def toggle_btn_one(sel):
    return not bool(sel)


# ── Actualizar todos / Reintentar fallidos ────────────────────────────────────

@callback(
    Output("fund-upd-interval",  "disabled"),
    Output("fund-upd-progress",  "style"),
    Output("fund-upd-btn-all",   "disabled"),
    Output("fund-upd-btn-retry", "disabled"),
    Output("fund-upd-alert",     "children"),
    Output("fund-upd-alert",     "is_open"),
    Output("fund-upd-alert",     "color"),
    Output("fund-upd-table",     "data",    allow_duplicate=True),
    Input("fund-upd-btn-all",    "n_clicks"),
    Input("fund-upd-btn-retry",  "n_clicks"),
    Input("fund-upd-btn-clear",  "n_clicks"),
    prevent_initial_call=True,
)
def handle_buttons(n_all, n_retry, n_clear):
    from dash import ctx
    if not current_user.is_authenticated or not current_user.is_admin:
        return no_update, no_update, no_update, no_update, no_update, no_update, no_update, no_update

    tid = ctx.triggered_id
    _no_prog = {"display": "none"}

    if tid == "fund-upd-btn-clear":
        from app.database import get_session
        from app.models import FundamentalUpdateLog
        s = get_session()
        s.query(FundamentalUpdateLog).delete()
        s.commit()
        return True, _no_prog, False, False, "Log limpiado.", True, "success", svc.get_fundamentals_log()

    if tid in ("fund-upd-btn-all", "fund-upd-btn-retry"):
        if _state["running"]:
            return True, _no_prog, True, True, "Ya hay una actualización en curso.", True, "warning", no_update

        only_failed = (tid == "fund-upd-btn-retry")
        _state.update({"running": True, "current": 0, "total": 0,
                        "msg": "", "error": None, "has_errors": False, "phase": "Iniciando..."})

        def _run():
            def _cb(cur, tot):
                _state["current"] = cur
                _state["total"]   = tot
                _state["phase"]   = ""
            try:
                if only_failed:
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
                else:
                    _state["phase"] = "Descargando datos de Yahoo Finance..."
                    summary = svc.update_all_fundamentals(progress_cb=_cb)
                _state["has_errors"] = bool(summary["errors"])
                _state["msg"] = (
                    f"Completado: {summary['success']}/{summary['total']} exitosos, "
                    f"{len(summary['errors'])} errores."
                )
            except Exception as exc:
                _state["error"] = str(exc)
            finally:
                _state["running"] = False

        threading.Thread(target=_run, daemon=True).start()
        return False, {"display": "block"}, True, True, "", False, "info", no_update

    return no_update, no_update, no_update, no_update, no_update, no_update, no_update, no_update


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
    Output("fund-upd-btn-all",   "disabled",          allow_duplicate=True),
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
        return pct, label, _show, False, no_update, no_update, no_update, no_update, True, True

    if _state["error"]:
        return 0, "", _hide, True, no_update, _state["error"], True, "danger", False, False

    msg   = _state["msg"]
    color = "success" if not _state.get("has_errors") else "warning"
    return 100, "Completo", _hide, True, svc.get_fundamentals_log(), msg, True, color, False, False


# ── Actualizar uno seleccionado ───────────────────────────────────────────────

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

    ticker = data[sel_rows[0]]["ticker"]
    from app.database import get_session
    from app.models import Asset
    asset = get_session().query(Asset).filter_by(ticker=ticker).first()
    if not asset:
        return f"Activo '{ticker}' no encontrado.", True, "danger", no_update

    try:
        svc.update_asset_fundamentals(asset.id, force=True)
        msg, color = f"{ticker}: actualizado correctamente.", "success"
    except Exception as exc:
        msg, color = f"{ticker}: error — {exc}", "danger"

    return msg, True, color, svc.get_fundamentals_log()
