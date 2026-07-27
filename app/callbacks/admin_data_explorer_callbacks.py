"""Callbacks del Explorador de datos (/admin/data-explorer)."""
import dash_ag_grid as dag
import pandas as pd
from dash import (Input, Output, State, callback, dcc,
                  no_update)

import app.services.reference_service as rs
from app.components.grids import (
    DEFAULT_COL_DEF, THEME_CLASS, grid_options, to_column_defs,
)
from app.services import data_explorer_service as des

# combo lógico → id del wrap (Div) en la página
_COMBO_WRAPS = {
    "indicator":  "de-wrap-indicator",
    "signal":     "de-wrap-signal",
    "strategy":   "de-wrap-strategy",
    "group_type": "de-wrap-group-type",
    "group":      "de-wrap-group",
    "asset":      "de-wrap-asset",
}
_WRAP_ORDER = list(_COMBO_WRAPS)  # orden fijo de los Outputs

_COMBO_LABELS = {
    "indicator": "indicador", "signal": "señal", "strategy": "estrategia",
    "group_type": "tipo de grupo", "group": "grupo", "asset": "activo",
}

_GROUP_GETTERS = {
    "sector":          rs.get_sectors,
    "market":          rs.get_markets,
    "industry":        rs.get_industries,
    "country":         rs.get_countries,
    "instrument_type": rs.get_instrument_types,
}


# ── Mostrar/ocultar combos según el conjunto de datos ─────────────────────────

@callback(
    [Output(_COMBO_WRAPS[c], "style") for c in _WRAP_ORDER],
    Input("de-dataset", "value"),
)
def toggle_combos(dataset):
    needed = set(des.DATASETS.get(dataset, {}).get("combos", []))
    return [{"display": "block"} if c in needed else {"display": "none"}
            for c in _WRAP_ORDER]


# ── Poblar el combo de grupo según el tipo de grupo ───────────────────────────

@callback(
    Output("de-group", "options"),
    Output("de-group", "value"),
    Input("de-group-type", "value"),
    prevent_initial_call=True,
)
def load_groups(group_type):
    getter = _GROUP_GETTERS.get(group_type)
    if not getter:
        return [], None
    return [{"label": g.name, "value": g.id} for g in getter()], None


# ── Consulta principal ────────────────────────────────────────────────────────

@callback(
    Output("de-result-container", "children"),
    Output("de-result-info", "children"),
    Output("de-btn-export", "disabled"),
    Output("de-data-store", "data"),
    Input("de-dataset",    "value"),
    Input("de-indicator",  "value"),
    Input("de-signal",     "value"),
    Input("de-strategy",   "value"),
    Input("de-group-type", "value"),
    Input("de-group",      "value"),
    Input("de-asset",      "value"),
)
def run_query(dataset, indicator, signal, strategy, group_type, group, asset):
    if not dataset:
        return None, "Elegí un conjunto de datos.", True, None

    values = {"indicator": indicator, "signal": signal, "strategy": strategy,
              "group_type": group_type, "group": group, "asset": asset}
    needed = des.DATASETS[dataset]["combos"]
    missing = [c for c in needed if values.get(c) in (None, "")]
    if missing:
        faltan = ", ".join(_COMBO_LABELS[c] for c in missing)
        return None, f"Completá: {faltan}.", True, None

    try:
        table, columns, records = des.fetch(dataset, **values)
    except Exception as exc:
        return None, f"⚠ {exc}", True, None

    if not records:
        return (None, f"{table} — 0 filas (sin datos para esa selección).",
                True, None)

    tope = " (tope alcanzado)" if len(records) >= des.MAX_ROWS else ""
    info = f"{table} — {len(records)} filas{tope}"
    dt = dag.AgGrid(
        columnDefs=to_column_defs([{"name": c, "id": c} for c in columns]),
        rowData=records,
        className=THEME_CLASS,
        style={"height": "calc(100vh - 340px)", "width": "100%"},
        defaultColDef=DEFAULT_COL_DEF,
        dashGridOptions=grid_options(),
    )
    store = {"columns": columns, "records": records, "table": table}
    return dt, info, False, store


# ── Exportar CSV ──────────────────────────────────────────────────────────────

@callback(
    Output("de-download", "data"),
    Input("de-btn-export", "n_clicks"),
    State("de-data-store", "data"),
    prevent_initial_call=True,
)
def export_csv(_, store):
    if not store or not store.get("records"):
        return no_update
    df = pd.DataFrame(store["records"], columns=store["columns"])
    return dcc.send_data_frame(df.to_csv, f"{store['table']}.csv", index=False)
