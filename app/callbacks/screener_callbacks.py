from dash import Input, Output, State, callback, no_update

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
    Input("scr-btn-apply", "n_clicks"),
    Input("scr-table", "id"),
    State("scr-filter-country", "value"),
    State("scr-filter-market", "value"),
    State("scr-filter-itype", "value"),
    State("scr-filter-sector", "value"),
    State("scr-filter-industry", "value"),
    State("scr-filter-rsi", "value"),
    State("scr-filter-sma20", "value"),
    State("scr-filter-sma50", "value"),
    State("scr-filter-sma200", "value"),
)
def apply_screener(
    n_clicks, _id,
    country_ids, market_ids, itype_ids, sector_ids, industry_ids,
    rsi_range, sma20_val, sma50_val, sma200_val,
):
    def sma_filter(v):
        if v == "above":
            return True
        if v == "below":
            return False
        return None

    rsi_min = rsi_range[0] if rsi_range else None
    rsi_max = rsi_range[1] if rsi_range else None

    rows = scr_svc.get_screener_data(
        country_ids=country_ids or None,
        market_ids=market_ids or None,
        instrument_type_ids=itype_ids or None,
        sector_ids=sector_ids or None,
        industry_ids=industry_ids or None,
        rsi_min=rsi_min,
        rsi_max=rsi_max,
        above_sma20=sma_filter(sma20_val),
        above_sma50=sma_filter(sma50_val),
        above_sma200=sma_filter(sma200_val),
    )
    count_label = f"{len(rows)} resultado{'s' if len(rows) != 1 else ''}"
    return rows, count_label


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
