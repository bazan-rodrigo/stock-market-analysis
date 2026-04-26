from dash import Input, Output, callback
from datetime import datetime

import app.services.reference_service as ref_svc
import app.services.screener_service as scr_svc


def _gs_label(score) -> str | None:
    if score is None:
        return None
    if score >= 50:
        return "Alcista"
    if score >= 20:
        return "Mejorando"
    if score <= -50:
        return "Bajista"
    if score <= -20:
        return "Deteriorando"
    return "Lateral"

_REGIME_ES = {
    "bullish_nascent_strong": "Alcista naciente fuerte",
    "bullish_nascent":        "Alcista naciente",
    "bullish_strong":         "Alcista fuerte",
    "bullish":                "Alcista",
    "lateral_nascent":        "Lateral naciente",
    "lateral":                "Lateral",
    "bearish_nascent_strong": "Bajista naciente fuerte",
    "bearish_nascent":        "Bajista naciente",
    "bearish_strong":         "Bajista fuerte",
    "bearish":                "Bajista",
}

_VOL_ES = {
    f"{vr}_{dr}": f"{vl} | {dl}"
    for vr, vl in [("extrema", "Extrema"), ("alta", "Alta"), ("normal", "Normal"), ("baja", "Baja")]
    for dr, dl in [("larga", "Larga"), ("media", "Media"), ("corta", "Corta")]
}

# Mapeo dim_id → prefijo columna gs_*
_DIM_PREFIX = {
    "sector_id":          "gs_sector",
    "industry_id":        "gs_industry",
    "country_id":         "gs_country",
    "instrument_type_id": "gs_itype",
    "market_id":          "gs_market",
}


@callback(
    Output("scr-filter-country", "options"),
    Output("scr-filter-market", "options"),
    Output("scr-filter-itype", "options"),
    Output("scr-filter-sector", "options"),
    Output("scr-filter-industry", "options"),
    Input("scr-filter-country", "id"),
)
def load_screener_filter_options(_):
    countries  = ref_svc.get_countries()
    markets    = ref_svc.get_markets()
    itypes     = ref_svc.get_instrument_types()
    sectors    = ref_svc.get_sectors()
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
    Output("scr-table", "tooltip_data"),
    Output("scr-result-count", "children"),
    Input("scr-filter-country", "value"),
    Input("scr-filter-market", "value"),
    Input("scr-filter-itype", "value"),
    Input("scr-filter-sector", "value"),
    Input("scr-filter-industry", "value"),
)
def apply_screener(country_ids, market_ids, itype_ids, sector_ids, industry_ids):
    # Cargar todos los activos (sin filtrar) para calcular scores de grupo completos
    all_rows = scr_svc.get_screener_data()
    group_scores = scr_svc.get_screener_group_scores(all_rows)

    # Filtrar en Python manteniendo scores calculados sobre el universo completo
    def _match(row):
        if country_ids and row.get("country_id") not in country_ids:
            return False
        if market_ids and row.get("market_id") not in market_ids:
            return False
        if itype_ids and row.get("instrument_type_id") not in itype_ids:
            return False
        if sector_ids and row.get("sector_id") not in sector_ids:
            return False
        if industry_ids and row.get("industry_id") not in industry_ids:
            return False
        return True

    rows = [r for r in all_rows if _match(r)]

    tooltip_data = []
    for row in rows:
        # Traducir regímenes y volatilidad
        row["regime_d"] = _REGIME_ES.get(row.get("regime_d"), "")
        row["regime_w"] = _REGIME_ES.get(row.get("regime_w"), "")
        row["regime_m"] = _REGIME_ES.get(row.get("regime_m"), "")
        row["vol_d"] = _VOL_ES.get(row.get("vol_d"), "")
        row["vol_w"] = _VOL_ES.get(row.get("vol_w"), "")
        row["vol_m"] = _VOL_ES.get(row.get("vol_m"), "")

        # Enlace ticker → gráfico
        asset_id = row.get("id", "")
        ticker   = row.get("ticker", "")
        row["ticker"] = f"[{ticker}](/chart?asset_id={asset_id})"

        # Desvíos SMA con período entre paréntesis
        for tf in ("d", "w", "m"):
            val  = row.get(f"dist_sma_{tf}")
            best = row.get(f"best_sma_{tf}")
            if val is not None:
                sign = "+" if val > 0 else ""
                period = f" (SMA{best})" if best else ""
                row[f"dist_sma_{tf}"] = f"{sign}{val:.2f}{period}"

        # Scores de grupo → texto de categoría
        for dim_id, prefix in _DIM_PREFIX.items():
            gid = row.get(dim_id)
            for tf in ("d", "w", "m"):
                col   = f"{prefix}_{tf}"
                score = group_scores.get((dim_id, gid, tf)) if gid is not None else None
                row[col] = _gs_label(score)

        # Tooltip con nombre completo (para la columna truncada)
        full_name = row.get("name") or ""
        tooltip_data.append({"name": {"value": full_name, "type": "text"}})

    count_label = f"{len(rows)} resultado{'s' if len(rows) != 1 else ''}"
    return rows, tooltip_data, count_label


_scr_state = {"running": False, "current": 0, "total": 0, "msg": "", "error": None, "has_errors": False}


@callback(
    Output("scr-interval",         "disabled"),
    Output("scr-progress",         "style"),
    Output("scr-btn-recompute",    "disabled"),
    Output("scr-recompute-status", "children"),
    Input("scr-btn-recompute", "n_clicks"),
    prevent_initial_call=True,
)
def recompute_snapshots(_):
    _scr_state.update({"running": True, "current": 0, "total": 0, "msg": "", "error": None, "has_errors": False})

    def _run():
        def _progress(current, total):
            _scr_state["current"] = current
            _scr_state["total"]   = total
        try:
            result = scr_svc.recompute_all_snapshots(progress_cb=_progress)
            n_err = len(result["errors"])
            _scr_state["has_errors"] = bool(n_err)
            _scr_state["msg"] = (
                f"Recalculado a las {datetime.now().strftime('%H:%M:%S')} — "
                f"{result['total'] - n_err}/{result['total']} exitosos"
            )
        except Exception as exc:
            _scr_state["error"] = str(exc)
        finally:
            _scr_state["running"] = False

    import threading
    threading.Thread(target=_run, daemon=True).start()
    return False, {"display": "block"}, True, ""


@callback(
    Output("scr-progress",         "value"),
    Output("scr-progress",         "label"),
    Output("scr-progress",         "style",    allow_duplicate=True),
    Output("scr-interval",         "disabled", allow_duplicate=True),
    Output("scr-btn-recompute",    "disabled", allow_duplicate=True),
    Output("scr-recompute-status", "children", allow_duplicate=True),
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
