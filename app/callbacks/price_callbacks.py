import threading

from dash import Input, Output, State, callback, no_update, html

import app.services.price_service as svc

_prices_state = {"running": False, "current": 0, "total": 0, "summary": None, "error": None, "msg": "", "phase": ""}


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
    Input("prices-log-table", "selected_rows"),
)
def price_row_selection(sel_rows):
    return not bool(sel_rows), not bool(sel_rows)


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
    return svc.get_all_assets_with_log(), msg, True, color


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
        _prices_state["running"] = False

    threading.Thread(target=_run, daemon=True).start()
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
        finally:
            _prices_state["running"] = False

    threading.Thread(target=_run, daemon=True).start()
    return False, False, {"display": "block"}  # cierra modal, activa interval


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
    Output("prices-btn-indicators",  "disabled"),
    Input("prices-btn-indicators", "n_clicks"),
    State("prices-log-table", "selected_rows"),
    State("prices-log-table", "data"),
    prevent_initial_call=True,
)
def recompute_indicators(_, sel_rows, data):
    """Sin selección: valores vigentes de todos los activos.
    Con filas seleccionadas: vigentes + historia completa, solo de esos activos."""
    from app.services.technical_service import (
        backfill_asset_history, compute_current_indicators,
        recompute_current_indicators, _save_indicator_log,
    )
    _prices_state.update({"running": True, "current": 0, "total": 0, "msg": "", "error": None, "has_errors": False})

    sel_ids = []
    if sel_rows:
        from app.services.asset_service import get_asset_by_ticker
        tickers = [data[i]["ticker"] for i in sel_rows]
        sel_ids = [a.id for a in (get_asset_by_ticker(t) for t in tickers) if a is not None]

    def _run():
        from app.database import Session as _DbSession

        def _progress(current, total, *_):
            _prices_state["current"] = current
            _prices_state["total"]   = total

        try:
            if sel_ids:
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
            else:
                result = recompute_current_indicators(progress_cb=_progress)
                n_err = len(result["errors"])
                _prices_state["has_errors"] = bool(n_err)
                _prices_state["msg"] = (
                    f"Indicadores recalculados: {result['total'] - n_err}/{result['total']} exitosos, {n_err} errores."
                )
        except Exception as exc:
            _prices_state["error"] = str(exc)
        finally:
            _prices_state["running"] = False
            _DbSession.remove()

    threading.Thread(target=_run, daemon=True).start()
    return False, {"display": "block"}, True
