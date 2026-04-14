from dash import Input, Output, State, callback, no_update, html

import app.services.price_service as svc


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
        return svc.get_all_assets_with_log(), msg, True, color
    except Exception as exc:
        return no_update, _error_msg("Error general", exc), True, "danger"


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
    Output("prices-log-table", "data", allow_duplicate=True),
    Output("prices-alert", "children", allow_duplicate=True),
    Output("prices-alert", "is_open", allow_duplicate=True),
    Output("prices-alert", "color", allow_duplicate=True),
    Input("prices-btn-retry", "n_clicks"),
    prevent_initial_call=True,
)
def retry_failed(_):
    from app.services.asset_service import get_asset_by_ticker
    logs = svc.get_all_assets_with_log()
    failed = [r for r in logs if r["result"] == "Error"]
    if not failed:
        return no_update, "No hay activos con error.", True, "info"

    successes, errors = [], []
    for row in failed:
        ticker = row["ticker"]
        try:
            asset = get_asset_by_ticker(ticker)
            if asset is None:
                errors.append(f"{ticker}: no encontrado")
                continue
            svc.update_asset_prices(asset.id)
            successes.append(ticker)
        except Exception as exc:
            errors.append(_error_msg(ticker, exc))

    parts = []
    if successes:
        parts.append(f"{len(successes)} actualizados: {', '.join(successes)}.")
    if errors:
        parts.append("Errores: " + " | ".join(errors))
    color = "success" if not errors else ("warning" if successes else "danger")
    return svc.get_all_assets_with_log(), " ".join(parts), True, color


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
    Output("prices-log-table", "data", allow_duplicate=True),
    Output("prices-alert", "children", allow_duplicate=True),
    Output("prices-alert", "is_open", allow_duplicate=True),
    Output("prices-alert", "color", allow_duplicate=True),
    Input("prices-btn-redownload-confirm", "n_clicks"),
    prevent_initial_call=True,
)
def redownload_all(_):
    from app.services.asset_service import get_assets
    assets = get_assets(only_active=True)
    successes, errors = [], []
    for asset in assets:
        try:
            svc.clear_prices(asset.id)
            svc.update_asset_prices(asset.id)
            successes.append(asset.ticker)
        except Exception as exc:
            errors.append(_error_msg(asset.ticker, exc))

    parts = []
    if successes:
        parts.append(f"{len(successes)} redescargados: {', '.join(successes)}.")
    if errors:
        parts.append(html.Span(["Errores: ", *[html.Span([e, " | "]) for e in errors]]))
    color = "success" if not errors else ("warning" if successes else "danger")
    return svc.get_all_assets_with_log(), html.Span(parts), True, color


@callback(
    Output("prices-log-table", "data", allow_duplicate=True),
    Input("prices-btn-clear-log", "n_clicks"),
    prevent_initial_call=True,
)
def clear_log(_):
    svc.clear_update_logs()
    return []
