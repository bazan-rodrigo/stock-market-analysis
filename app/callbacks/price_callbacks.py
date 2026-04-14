from dash import Input, Output, State, callback, no_update

import app.services.price_service as svc


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
    return _logs_to_rows(svc.get_update_logs())


@callback(
    Output("prices-btn-one", "disabled"),
    Output("prices-btn-retry", "disabled"),
    Output("prices-btn-redownload", "disabled"),
    Input("prices-log-table", "selected_rows"),
    State("prices-log-table", "data"),
)
def price_row_selection(sel_rows, data):
    if not sel_rows:
        return True, True, True
    row = data[sel_rows[0]]
    is_error = row["result"] == "Error"
    return False, not is_error, False


@callback(
    Output("prices-log-table", "data", allow_duplicate=True),
    Output("prices-alert", "children"),
    Output("prices-alert", "is_open"),
    Output("prices-alert", "color"),
    Input("prices-btn-all", "n_clicks"),
    prevent_initial_call=True,
)
def update_all(_):
    try:
        summary = svc.update_all_active_assets()
        msg = (
            f"Actualización completa: {summary['success']}/{summary['total']} exitosos, "
            f"{len(summary['errors'])} errores."
        )
        color = "success" if not summary["errors"] else "warning"
        return _logs_to_rows(svc.get_update_logs()), msg, True, color
    except Exception as exc:
        return no_update, str(exc), True, "danger"


@callback(
    Output("prices-log-table", "data", allow_duplicate=True),
    Output("prices-alert", "children", allow_duplicate=True),
    Output("prices-alert", "is_open", allow_duplicate=True),
    Output("prices-alert", "color", allow_duplicate=True),
    Input("prices-btn-one", "n_clicks"),
    Input("prices-btn-retry", "n_clicks"),
    State("prices-log-table", "selected_rows"),
    State("prices-log-table", "data"),
    prevent_initial_call=True,
)
def update_one(n_one, n_retry, sel_rows, data):
    if not sel_rows:
        return no_update, no_update, no_update, no_update
    ticker = data[sel_rows[0]]["ticker"]
    try:
        from app.services.asset_service import get_asset_by_ticker
        asset = get_asset_by_ticker(ticker)
        if asset is None:
            return no_update, f"Activo {ticker} no encontrado.", True, "danger"
        svc.update_asset_prices(asset.id)
        return _logs_to_rows(svc.get_update_logs()), f"{ticker}: actualizado correctamente.", True, "success"
    except Exception as exc:
        return _logs_to_rows(svc.get_update_logs()), f"{ticker}: {exc}", True, "danger"


@callback(
    Output("prices-log-table", "data", allow_duplicate=True),
    Output("prices-alert", "children", allow_duplicate=True),
    Output("prices-alert", "is_open", allow_duplicate=True),
    Output("prices-alert", "color", allow_duplicate=True),
    Input("prices-btn-redownload", "n_clicks"),
    State("prices-log-table", "selected_rows"),
    State("prices-log-table", "data"),
    prevent_initial_call=True,
)
def redownload(_, sel_rows, data):
    if not sel_rows:
        return no_update, no_update, no_update, no_update
    ticker = data[sel_rows[0]]["ticker"]
    try:
        from app.services.asset_service import get_asset_by_ticker
        asset = get_asset_by_ticker(ticker)
        if asset is None:
            return no_update, f"Activo {ticker} no encontrado.", True, "danger"
        svc.clear_prices(asset.id)
        svc.update_asset_prices(asset.id)
        return _logs_to_rows(svc.get_update_logs()), f"{ticker}: historia borrada y redescargada.", True, "success"
    except Exception as exc:
        return _logs_to_rows(svc.get_update_logs()), f"{ticker}: {exc}", True, "danger"


@callback(
    Output("prices-log-table", "data", allow_duplicate=True),
    Input("prices-btn-clear-log", "n_clicks"),
    prevent_initial_call=True,
)
def clear_log(_):
    svc.clear_update_logs()
    return []
