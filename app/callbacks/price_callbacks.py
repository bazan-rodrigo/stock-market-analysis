import threading

from dash import Input, Output, State, callback, no_update, html

import app.services.price_service as svc
from app.services import run_lock_service as _rl

_prices_state = {"running": False, "current": 0, "total": 0, "summary": None, "error": None, "msg": "", "phase": ""}

_BUSY_PRICES = "Hay otra operación pesada en curso. Esperá a que termine antes de lanzar esta."


def _launch_locked_bg(run_fn) -> bool:
    """Toma el lock persistido HEAVY_WRITE y lanza run_fn en un thread daemon,
    con heartbeat mientras corre y liberación al terminar. Devuelve False si
    otra corrida pesada tiene el lock (el caller debe refrescar el estado y
    mostrar 'ocupado'). Con multi-worker (gunicorn en Railway) esto evita que
    un botón de precios de un worker escriba en paralelo con el scheduler o el
    Centro de Datos de otro. guarded_acquire es fail-open: sin la migración
    0076 procede igual que antes (coordinación en memoria de siempre)."""
    token = _rl.guarded_acquire(_rl.HEAVY_WRITE)
    if token is None:
        return False

    def _wrapped():
        try:
            with _rl.heartbeating(_rl.HEAVY_WRITE, token):
                run_fn()
        finally:
            _prices_state["running"] = False

    threading.Thread(target=_wrapped, daemon=True).start()
    return True


def _logs_to_rows(logs) -> list[dict]:
    return [
        {
            "ticker": log.asset.ticker,
            "asset_name": log.asset.name,
            "last_attempt_at": str(log.last_attempt_at)[:19],
            "result": "Éxito" if log.success else "Error",
            "error_detail": log.error_detail or "",
        }
        for log in logs
    ]


@callback(
    Output("prices-log-table", "data"),
    Input("prices-log-table", "id"),
)
def load_price_logs(_):
    return svc.get_all_assets_with_log()


@callback(
    Output("prices-btn-one", "disabled"),
    Output("prices-btn-redownload-selected", "disabled"),
    Output("prices-btn-indicators", "disabled"),
    Input("prices-log-table", "selected_rows"),
)
def price_row_selection(sel_rows):
    return not bool(sel_rows), not bool(sel_rows), not bool(sel_rows)


@callback(
    Output("prices-progress",     "value"),
    Output("prices-progress",     "label"),
    Output("prices-progress",     "style",    allow_duplicate=True),
    Output("prices-interval",     "disabled", allow_duplicate=True),
    Output("prices-log-table",    "data",     allow_duplicate=True),
    Output("prices-alert",        "children", allow_duplicate=True),
    Output("prices-alert",        "is_open",  allow_duplicate=True),
    Output("prices-alert",        "color",    allow_duplicate=True),
    Output("prices-btn-indicators", "disabled", allow_duplicate=True),
    Input("prices-interval", "n_intervals"),
    prevent_initial_call=True,
)
def poll_prices(_):
    if _prices_state["running"]:
        current = _prices_state["current"]
        total   = _prices_state["total"] or 1
        pct     = int(current / total * 100)
        if _prices_state["total"]:
            label = f"{current} / {_prices_state['total']}"
        else:
            label = _prices_state.get("phase") or "Iniciando..."
        return pct, label, {"display": "block"}, False, no_update, no_update, no_update, no_update, True

    if _prices_state["error"]:
        return 0, "", {"display": "none"}, True, no_update, _prices_state["error"], True, "danger", False

    msg   = _prices_state["msg"]
    color = "success" if not _prices_state.get("has_errors") else "warning"
    return 100, "Completo", {"display": "none"}, True, svc.get_all_assets_with_log(), msg, True, color, False


@callback(
    Output("prices-log-table", "data", allow_duplicate=True),
    Output("prices-alert", "children", allow_duplicate=True),
    Output("prices-alert", "is_open", allow_duplicate=True),
    Output("prices-alert", "color", allow_duplicate=True),
    Input("prices-btn-one", "n_clicks"),
    State("prices-log-table", "selected_rows"),
    State("prices-log-table", "data"),
    prevent_initial_call=True,
)
def update_one(_, sel_rows, data):
    if not sel_rows:
        return no_update, no_update, no_update, no_update
    # Síncrono (thread del request), pero escribe prices/ind_* → mismo lock
    # que las corridas pesadas. Sin heartbeating: es corto y no cruza threads.
    token = _rl.guarded_acquire(_rl.HEAVY_WRITE)
    if token is None:
        return no_update, _BUSY_PRICES, True, "warning"
    try:
        from app.services.asset_service import get_asset_by_ticker
        tickers = [data[i]["ticker"] for i in sel_rows]
        successes, errors = [], []
        for ticker in tickers:
            try:
                asset = get_asset_by_ticker(ticker)
                if asset is None:
                    errors.append(f"{ticker}: no encontrado")
                    continue
                svc.update_asset_prices(asset.id)
                successes.append(ticker)
            except Exception as exc:
                errors.append(f"{ticker}: {exc}")
        if not errors:
            msg, color = f"{len(successes)} actualizados correctamente.", "success"
        elif not successes:
            msg, color = f"{len(errors)} errores: {', '.join(errors[:5])}", "danger"
        else:
            msg, color = (f"{len(successes)} actualizados, {len(errors)} errores: "
                          f"{', '.join(errors[:5])}"), "warning"
        result = svc.get_all_assets_with_log(), msg, True, color
    finally:
        _rl.release(_rl.HEAVY_WRITE, token)
    return result


@callback(
    Output("prices-interval", "disabled", allow_duplicate=True),
    Output("prices-progress", "style",    allow_duplicate=True),
    Output("prices-alert",    "children", allow_duplicate=True),
    Output("prices-alert",    "is_open",  allow_duplicate=True),
    Output("prices-alert",    "color",    allow_duplicate=True),
    Input("prices-btn-retry", "n_clicks"),
    prevent_initial_call=True,
)
def retry_failed(_):
    logs = svc.get_all_assets_with_log()
    failed = [r for r in logs if r["result"] == "Error"]
    if not failed:
        return True, {"display": "none"}, "No hay activos con error.", True, "info"

    total = len(failed)
    _prices_state.update({"running": True, "current": 0, "total": total, "msg": "", "error": None, "has_errors": False})

    def _run():
        from app.services.asset_service import get_asset_by_ticker as _get
        successes, errors = [], []
        for i, row in enumerate(failed):
            _prices_state["current"] = i + 1
            ticker = row["ticker"]
            try:
                asset = _get(ticker)
                if asset is None:
                    errors.append(f"{ticker}: no encontrado")
                    continue
                svc.update_asset_prices(asset.id)
                successes.append(ticker)
            except Exception as exc:
                errors.append(f"{ticker}: {exc}")
        _prices_state["has_errors"] = bool(errors)
        parts = []
        if successes:
            parts.append(f"{len(successes)} actualizados.")
        if errors:
            parts.append(f"{len(errors)} errores: {', '.join(errors[:5])}")
        _prices_state["msg"] = " ".join(parts)

    if not _launch_locked_bg(_run):
        _prices_state["running"] = False
        return True, {"display": "none"}, _BUSY_PRICES, True, "warning"
    return False, {"display": "block"}, "", False, "info"


@callback(
    Output("prices-redownload-selected-modal", "is_open"),
    Input("prices-btn-redownload-selected", "n_clicks"),
    Input("prices-btn-redownload-selected-confirm", "n_clicks"),
    Input("prices-btn-redownload-selected-cancel", "n_clicks"),
    prevent_initial_call=True,
)
def toggle_redownload_selected_modal(n_open, n_confirm, n_cancel):
    from dash import ctx
    return ctx.triggered_id == "prices-btn-redownload-selected"


@callback(
    Output("prices-redownload-selected-modal", "is_open", allow_duplicate=True),
    Output("prices-interval", "disabled", allow_duplicate=True),
    Output("prices-progress", "style",    allow_duplicate=True),
    Input("prices-btn-redownload-selected-confirm", "n_clicks"),
    State("prices-log-table", "selected_rows"),
    State("prices-log-table", "data"),
    prevent_initial_call=True,
)
def redownload_selected(_, sel_rows, data):
    if not sel_rows:
        return False, True, {"display": "none"}

    from app.services.asset_service import get_asset_by_ticker
    tickers   = [data[i]["ticker"] for i in sel_rows]
    asset_ids = [a.id for a in (get_asset_by_ticker(t) for t in tickers) if a is not None]

    _prices_state.update({"running": True, "current": 0, "total": 0, "msg": "", "error": None, "has_errors": False})

    def _run():
        def _progress(current, total, *_):
            _prices_state["current"] = current
            _prices_state["total"]   = total
        try:
            summary = svc.redownload_prices(asset_ids=asset_ids, progress_cb=_progress)
            _prices_state["has_errors"] = bool(summary["errors"])
            _prices_state["msg"] = (
                f"Redescargar completo (seleccionados): {summary['success']}/{summary['total']} exitosos, "
                f"{len(summary['errors'])} errores."
            )
        except Exception as exc:
            _prices_state["error"] = str(exc)

    if not _launch_locked_bg(_run):
        _prices_state["running"] = False
        _prices_state["error"] = _BUSY_PRICES     # el poll lo muestra como alerta
        return False, False, {"display": "none"}  # cierra modal, sin arrancar
    return False, False, {"display": "block"}     # cierra modal, activa interval


@callback(
    Output("prices-log-table", "data", allow_duplicate=True),
    Input("prices-btn-clear-log", "n_clicks"),
    prevent_initial_call=True,
)
def clear_log(_):
    svc.clear_update_logs()
    return []


@callback(
    Output("prices-interval",      "disabled",  allow_duplicate=True),
    Output("prices-progress",      "style",     allow_duplicate=True),
    Output("prices-btn-indicators", "disabled", allow_duplicate=True),
    Input("prices-btn-indicators", "n_clicks"),
    State("prices-log-table", "selected_rows"),
    State("prices-log-table", "data"),
    prevent_initial_call=True,
)
def recompute_indicators(_, sel_rows, data):
    """Recalculo completo (vigentes + historia, sin atajos) de los
    indicadores técnicos de los activos seleccionados — requiere selección,
    ver price_row_selection."""
    if not sel_rows:
        return no_update, no_update, no_update

    from app.services.technical_service import (
        backfill_asset_history, compute_current_indicators, _save_indicator_log,
    )
    from app.services.asset_service import get_asset_by_ticker
    tickers = [data[i]["ticker"] for i in sel_rows]
    sel_ids = [a.id for a in (get_asset_by_ticker(t) for t in tickers) if a is not None]

    _prices_state.update({"running": True, "current": 0, "total": 0, "msg": "", "error": None, "has_errors": False})

    def _run():
        from app.database import Session as _DbSession

        def _progress(current, total, *_):
            _prices_state["current"] = current
            _prices_state["total"]   = total

        try:
            errs = 0
            for i, aid in enumerate(sel_ids, 1):
                _progress(i, len(sel_ids))
                try:
                    compute_current_indicators(aid)
                    backfill_asset_history(aid)
                    _save_indicator_log(aid, success=True, error=None)
                except Exception as exc:
                    errs += 1
                    _save_indicator_log(aid, success=False, error=str(exc))
            _prices_state["has_errors"] = bool(errs)
            _prices_state["msg"] = (
                f"Indicadores recalculados (vigentes + historia): "
                f"{len(sel_ids) - errs}/{len(sel_ids)} exitosos, {errs} errores."
            )
        except Exception as exc:
            _prices_state["error"] = str(exc)
        finally:
            _DbSession.remove()

    if not _launch_locked_bg(_run):
        _prices_state["running"] = False
        _prices_state["error"] = _BUSY_PRICES     # el poll lo muestra como alerta
        return False, {"display": "none"}, no_update
    return False, {"display": "block"}, True
