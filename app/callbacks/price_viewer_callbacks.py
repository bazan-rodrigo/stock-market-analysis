from datetime import date

from dash import Input, Output, State, callback, no_update

from app.services.asset_service import get_assets
from app.services.price_service import get_prices_df, get_latest_prices_all


@callback(
    Output("pv-asset-select", "options"),
    Input("pv-asset-select", "id"),
)
def load_pv_assets(_):
    assets = get_assets(only_active=True)
    return [{"label": f"{a.ticker} — {a.name}", "value": a.id} for a in assets]


@callback(
    Output("pv-history-controls", "style"),
    Output("pv-history-table-container", "style"),
    Output("pv-latest-table-container", "style"),
    Output("pv-latest-table", "data"),
    Output("pv-result-info", "children"),
    Input("pv-mode", "value"),
)
def switch_mode(mode):
    if mode == "latest":
        rows = get_latest_prices_all()
        info = f"{len(rows)} instrumentos con precio disponible."
        return (
            {"display": "none"},
            {"display": "none"},
            {"display": "block"},
            rows,
            info,
        )
    return (
        {"display": "block"},
        {"display": "block"},
        {"display": "none"},
        [],
        "",
    )


@callback(
    Output("pv-history-table", "data"),
    Output("pv-alert", "children"),
    Output("pv-alert", "is_open"),
    Output("pv-result-info", "children", allow_duplicate=True),
    Input("pv-btn-query", "n_clicks"),
    State("pv-asset-select", "value"),
    State("pv-date-from", "value"),
    State("pv-date-to", "value"),
    prevent_initial_call=True,
)
def query_history(_, asset_id, date_from, date_to):
    if not asset_id:
        return no_update, "Seleccioná un instrumento.", True, no_update

    df = get_prices_df(int(asset_id))
    if df.empty:
        return [], "No hay precios descargados para este instrumento.", True, ""

    if date_from:
        df = df[df["date"] >= date.fromisoformat(date_from)]
    if date_to:
        df = df[df["date"] <= date.fromisoformat(date_to)]

    if df.empty:
        return [], "Sin datos en el rango seleccionado.", True, ""

    rows = df.assign(date=df["date"].astype(str)).to_dict("records")
    info = f"{len(rows)} registros — {rows[0]['date']} → {rows[-1]['date']}"
    return rows, "", False, info
