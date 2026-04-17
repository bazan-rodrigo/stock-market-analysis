import threading

from dash import Input, Output, State, callback, no_update, html

import app.services.price_service as svc

_prices_state = {"running": False, "current": 0, "total": 0, "summary": None, "error": None, "msg": ""}


def _error_msg(ticker: str, exc: Exception):
    """Mensaje de error con detalle técnico en dos líneas."""
    friendly = str(exc)
    tech = f"{type(exc).__name__}: {exc}"
    if friendly == tech:
        return f"{ticker}: {friendly}"
    return html.Span([
        f"{ticker}: {friendly}",
        html.Br(),
        html.Small(tech, style={"opacity": "0.7", "fontFamily": "monospace"}),
    ])


def _logs_to_rows(logs) -> list[dict]:
    return [
        {
            "ticker": l.asset.ticker,
            "asset_name": l.asset.name,
            "last_attempt_at": str(l.last_attempt_at)[:19],
            "result": "Éxito" if l.success else "Error",
            "error_detail": l.error_detail or "",
        }
        for l in logs
    ]


@callback(
    Output("prices-log-table", "data"),
    Input("prices-log-table", "id"),
)
def load_price_logs(_):
    return svc.get_all_assets_with_log()


@callback(
    Output("prices-btn-one", "disabled"),
    Input("prices-log-table", "selected_rows"),
)
def price_row_selection(sel_rows):
    return not bool(sel_rows)


@callback(
    Output("prices-interval", "disabled"),
    Output("prices-progress", "style"),
    Output("prices-btn-all", "disabled"),
    Input("prices-btn-all", "n_clicks"),
    prevent_initial_call=True,
)
def update_all(_):
    _prices_state.update({"running": True, "current": 0, "total": 0, "summary": None, "error": None})

    def _run():
        def _progress(current, total):
            _prices_state["current"] = current
            _prices_state["total"]   = total
        try:
            summary = svc.update_all_active_assets(progress_cb=_progress)
            _prices_state["has_errors"] = bool(summary["errors"])
            _prices_state["msg"] = (
                f"Actualización completa: {summary['success']}/{summary['total']} exitosos, "
                f"{len(summary['errors'])} errores."
            )
        except Exception as exc:
            _prices_state["error"] = str(exc)
        finally:
            _prices_state["running"] = False

    threading.Thread(target=_run, daemon=True).start()
    return False, {"display": "block"}, True


@callback(
    Output("prices-progress", "value"),
    Output("prices-progress", "label"),
    Output("prices-progress", "style",    allow_duplicate=True),
    Output("prices-interval", "disabled", allow_duplicate=True),
    Output("prices-log-table", "data",     allow_duplicate=True),
    Output("prices-alert",     "children", allow_duplicate=True),
    Output("prices-alert",     "is_open",  allow_duplicate=True),
    Output("prices-alert",     "color",    allow_duplicate=True),
    Output("prices-btn-all",   "disabled", allow_duplicate=True),
    Input("prices-interval", "n_intervals"),
    prevent_initial_call=True,
)
def poll_prices(_):
    if _prices_state["running"]:
        current = _prices_state["current"]
        total   = _prices_state["total"] or 1
        pct     = int(current / total * 100)
        label   = f"{current} / {_prices_state['total']}" if _prices_state["total"] else "Iniciando..."
        return pct, label, {"display": "block"}, False, no_update, no_update, no_update, no_update, True

    if _prices_state["error"]:
        return 0, "", {"display": "none"}, True, no_update, _prices_state["error"], True, "danger", False

    msg   = _prices_state["msg"]
    color = "success" if "error" not in msg.lower() and not _prices_state.get("has_errors") else "warning"
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
    ticker = data[sel_rows[0]]["ticker"]
    try:
        from app.services.asset_service import get_asset_by_ticker
        asset = get_asset_by_ticker(ticker)
        if asset is None:
            return no_update, f"Activo {ticker} no encontrado.", True, "danger"
        svc.update_asset_prices(asset.id)
        return svc.get_all_assets_with_log(), f"{ticker}: actualizado correctamente.", True, "success"
    except Exception as exc:
        return svc.get_all_assets_with_log(), _error_msg(ticker, exc), True, "danger"


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
    from app.services.asset_service import get_asset_by_ticker
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
    Output("prices-redownload-modal", "is_open"),
    Input("prices-btn-redownload", "n_clicks"),
    Input("prices-btn-redownload-confirm", "n_clicks"),
    Input("prices-btn-redownload-cancel", "n_clicks"),
    prevent_initial_call=True,
)
def toggle_redownload_modal(n_open, n_confirm, n_cancel):
    from dash import ctx
    return ctx.triggered_id == "prices-btn-redownload"


@callback(
    Output("prices-redownload-modal", "is_open", allow_duplicate=True),
    Output("prices-interval", "disabled", allow_duplicate=True),
    Output("prices-progress", "style",    allow_duplicate=True),
    Output("prices-btn-all",  "disabled", allow_duplicate=True),
    Input("prices-btn-redownload-confirm", "n_clicks"),
    prevent_initial_call=True,
)
def redownload_all(_):
    from app.services.asset_service import get_assets
    assets = get_assets(only_active=True)
    total  = len(assets)
    _prices_state.update({"running": True, "current": 0, "total": total, "msg": "", "error": None, "has_errors": False})

    def _run():
        successes, errors = [], []
        for i, asset in enumerate(assets):
            _prices_state["current"] = i + 1
            try:
                svc.clear_prices(asset.id)
                svc.update_asset_prices(asset.id)
                successes.append(asset.ticker)
            except Exception as exc:
                errors.append(f"{asset.ticker}: {exc}")
        _prices_state["has_errors"] = bool(errors)
        _prices_state["msg"] = (
            f"Redescargar completo: {len(successes)} exitosos, {len(errors)} errores."
        )
        _prices_state["running"] = False

    threading.Thread(target=_run, daemon=True).start()
    return False, False, {"display": "block"}, True  # cierra modal, activa interval


@callback(
    Output("prices-log-table", "data", allow_duplicate=True),
    Input("prices-btn-clear-log", "n_clicks"),
    prevent_initial_call=True,
)
def clear_log(_):
    svc.clear_update_logs()
    return []
