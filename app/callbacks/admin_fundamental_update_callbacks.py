import threading

from dash import Input, Output, State, callback, html, no_update
from flask_login import current_user

import app.services.fundamental_service as svc

_state = {"running": False, "current": 0, "total": 0, "msg": "", "error": None}


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


@callback(
    Output("fund-upd-alert",        "children"),
    Output("fund-upd-alert",        "is_open"),
    Output("fund-upd-alert",        "color"),
    Output("fund-upd-table",        "data",    allow_duplicate=True),
    Output("fund-upd-progress-area","children"),
    Input("fund-upd-btn-all",   "n_clicks"),
    Input("fund-upd-btn-retry", "n_clicks"),
    Input("fund-upd-btn-clear", "n_clicks"),
    prevent_initial_call=True,
)
def handle_buttons(n_all, n_retry, n_clear):
    from dash import ctx
    if not current_user.is_authenticated or not current_user.is_admin:
        return no_update, no_update, no_update, no_update, no_update

    tid = ctx.triggered_id

    if tid == "fund-upd-btn-clear":
        from app.database import get_session
        from app.models import FundamentalUpdateLog
        s = get_session()
        s.query(FundamentalUpdateLog).delete()
        s.commit()
        return "Log limpiado.", True, "success", svc.get_fundamentals_log(), no_update

    if tid in ("fund-upd-btn-all", "fund-upd-btn-retry"):
        if _state["running"]:
            return "Ya hay una actualización en curso.", True, "warning", no_update, no_update

        only_failed = (tid == "fund-upd-btn-retry")
        _state.update({"running": True, "current": 0, "total": 0, "msg": "", "error": None})

        def _run():
            def _cb(cur, tot):
                _state["current"] = cur
                _state["total"]   = tot
            try:
                if only_failed:
                    from app.database import get_session
                    from app.models import Asset, FundamentalUpdateLog
                    s = get_session()
                    failed_ids = {
                        r.asset_id for r in
                        s.query(FundamentalUpdateLog).filter_by(success=False).all()
                    }
                    from app.models import Asset as A
                    assets = s.query(A).filter(
                        A.fundamental_source_id.isnot(None),
                        A.id.in_(failed_ids),
                    ).all()
                    total = len(assets)
                    success = 0
                    errors  = []
                    for i, a in enumerate(assets, 1):
                        _cb(i, total)
                        try:
                            svc.update_asset_fundamentals(a.id, force=True)
                            success += 1
                        except Exception as exc:
                            errors.append({"ticker": a.ticker, "error": str(exc)})
                    summary = {"total": total, "success": success, "errors": errors}
                else:
                    summary = svc.update_all_fundamentals(progress_cb=_cb)
                _state["msg"] = (
                    f"Completado: {summary['success']}/{summary['total']} exitosos, "
                    f"{len(summary['errors'])} errores."
                )
            except Exception as exc:
                _state["error"] = str(exc)
            finally:
                _state["running"] = False

        threading.Thread(target=_run, daemon=True).start()
        return "Actualización iniciada en segundo plano.", True, "info", no_update, no_update

    return no_update, no_update, no_update, no_update, no_update


@callback(
    Output("fund-upd-alert",  "children",  allow_duplicate=True),
    Output("fund-upd-alert",  "is_open",   allow_duplicate=True),
    Output("fund-upd-alert",  "color",     allow_duplicate=True),
    Output("fund-upd-table",  "data",      allow_duplicate=True),
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
