from dash import Input, Output, State, callback, no_update
from datetime import datetime

import app.services.reference_service as ref_svc
import app.services.screener_service as scr_svc


@callback(
    Output("scr-filter-country", "options"),
    Output("scr-filter-market", "options"),
    Output("scr-filter-itype", "options"),
    Output("scr-filter-sector", "options"),
    Output("scr-filter-industry", "options"),
    Input("scr-filter-country", "id"),
)
def load_screener_filter_options(_):
    countries = ref_svc.get_countries()
    markets = ref_svc.get_markets()
    itypes = ref_svc.get_instrument_types()
    sectors = ref_svc.get_sectors()
    industries = ref_svc.get_industries()
    return (
        [{"label": c.name, "value": c.id} for c in countries],
        [{"label": m.name, "value": m.id} for m in markets],
        [{"label": it.name, "value": it.id} for it in itypes],
        [{"label": s.name, "value": s.id} for s in sectors],
        [{"label": i.name, "value": i.id} for i in industries],
    )


@callback(
    Output("scr-table", "data"),
    Output("scr-result-count", "children"),
    Input("scr-filter-country", "value"),
    Input("scr-filter-market", "value"),
    Input("scr-filter-itype", "value"),
    Input("scr-filter-sector", "value"),
    Input("scr-filter-industry", "value"),
)
def apply_screener(country_ids, market_ids, itype_ids, sector_ids, industry_ids):
    rows = scr_svc.get_screener_data(
        country_ids=country_ids or None,
        market_ids=market_ids or None,
        instrument_type_ids=itype_ids or None,
        sector_ids=sector_ids or None,
        industry_ids=industry_ids or None,
    )
    count_label = f"{len(rows)} resultado{'s' if len(rows) != 1 else ''}"
    return rows, count_label


_scr_state = {"running": False, "current": 0, "total": 0, "msg": "", "error": None, "has_errors": False}


@callback(
    Output("scr-interval",        "disabled"),
    Output("scr-progress",        "style"),
    Output("scr-btn-recompute",   "disabled"),
    Output("scr-recompute-status","children"),
    Input("scr-btn-recompute", "n_clicks"),
    prevent_initial_call=True,
)
def recompute_snapshots(_):
    import threading
    _scr_state.update({"running": True, "current": 0, "total": 0, "msg": "", "error": None, "has_errors": False})

    def _run():
        def _progress(current, total):
            _scr_state["current"] = current
            _scr_state["total"]   = total
        try:
            result = scr_svc.recompute_all_snapshots(progress_cb=_progress)
            n_err = len(result["errors"])
            _scr_state["has_errors"] = bool(n_err)
            _scr_state["msg"] = f"Recalculado a las {datetime.now().strftime('%H:%M:%S')} — {result['total'] - n_err}/{result['total']} exitosos"
        except Exception as exc:
            _scr_state["error"] = str(exc)
        finally:
            _scr_state["running"] = False

    threading.Thread(target=_run, daemon=True).start()
    return False, {"display": "block"}, True, ""


@callback(
    Output("scr-progress",        "value"),
    Output("scr-progress",        "label"),
    Output("scr-progress",        "style",    allow_duplicate=True),
    Output("scr-interval",        "disabled", allow_duplicate=True),
    Output("scr-btn-recompute",   "disabled", allow_duplicate=True),
    Output("scr-recompute-status","children", allow_duplicate=True),
    Input("scr-interval", "n_intervals"),
    prevent_initial_call=True,
)
def poll_scr_recompute(_):
    if _scr_state["running"]:
        current = _scr_state["current"]
        total   = _scr_state["total"] or 1
        pct     = int(current / total * 100)
        label   = f"{current} / {_scr_state['total']}" if _scr_state["total"] else "Iniciando..."
        return pct, label, {"display": "block"}, False, True, ""

    if _scr_state["error"]:
        return 0, "", {"display": "none"}, True, False, f"Error: {_scr_state['error']}"

    return 100, "Completo", {"display": "none"}, True, False, _scr_state["msg"]


@callback(
    Output("screener-redirect", "href"),
    Input("scr-table", "selected_rows"),
    State("scr-table", "data"),
    prevent_initial_call=True,
)
def screener_open_chart(sel_rows, data):
    if not sel_rows:
        return no_update
    asset_id = data[sel_rows[0]]["id"]
    return f"/chart?asset_id={asset_id}"
