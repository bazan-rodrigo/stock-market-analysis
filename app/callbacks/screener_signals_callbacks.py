from dash import Input, Output, State, callback, html, no_update

import app.services.strategy_service as svc
# Directo del origen y no vía app.pages.screener_signals: importar la página
# dispara su register_page, que exige la app ya instanciada.
from app.components.grids import score_col, text_col, ticker_col
from app.components.ui_constants import COLOR_WARNING


# ── Opciones de estrategias (carga inicial) ───────────────────────────────────

@callback(
    Output("ss-strategy-sel", "options"),
    Input("ss-strategy-sel",  "id"),
)
def load_strategy_opts(_):
    from app.services.visibility import current_viewer
    strategies = svc.get_visible_strategies(*current_viewer())
    return [{"label": s.name, "value": s.id} for s in strategies]


# ── Al elegir estrategia: actualizar fecha más reciente ───────────────────────

@callback(
    Output("ss-date",          "date"),
    Output("ss-sector-filter", "options"),
    Output("ss-market-filter", "options"),
    Input("ss-strategy-sel",   "value"),
    Input("ss-date",           "date"),
    prevent_initial_call=True,
)
def update_filters(strategy_id, current_date):
    if not strategy_id:
        return no_update, [], []

    from datetime import date as dt_date
    from dash import ctx

    new_date = no_update
    if ctx.triggered_id == "ss-strategy-sel":
        dates = svc.get_available_dates(strategy_id)
        new_date = str(dates[0]) if dates else no_update

    target_date_str = new_date if new_date is not no_update else current_date
    if not target_date_str or target_date_str is no_update:
        return new_date, [], []

    target_date = dt_date.fromisoformat(target_date_str)
    opts = svc.get_filter_options(strategy_id, target_date)
    return new_date, opts["sectors"], opts["markets"]


# ── Buscar: guardar resultados en stores ──────────────────────────────────────

def _miles(n: int) -> str:
    """10000 → '10.000' (separador de miles rioplatense)."""
    return f"{n:,}".replace(",", ".")


def _result_label(shown: int, total: int) -> tuple[str, bool]:
    """Texto del contador y si el ranking quedó cortado por el tope."""
    if total > shown:
        return f"{_miles(shown)} de {_miles(total)} activos", True
    return f"{_miles(shown)} activos", False


@callback(
    Output("ss-results-store", "data"),
    Output("ss-comp-meta",     "data"),
    Output("ss-query-store",   "data"),
    Output("ss-result-count",  "children"),
    Output("ss-btn-export",    "disabled"),
    Input("ss-btn-search",     "n_clicks"),
    State("ss-strategy-sel",   "value"),
    State("ss-date",           "date"),
    State("ss-sector-filter",  "value"),
    State("ss-market-filter",  "value"),
    State("ss-limit",          "value"),
    prevent_initial_call=True,
)
def do_search(_, strategy_id, date_str, sector_id, market_id, limit):
    if not strategy_id or not date_str:
        return None, [], None, "", True

    from datetime import date as dt_date
    target_date = dt_date.fromisoformat(date_str)

    rows_data, comp_meta, total = svc.get_strategy_results_with_breakdown(
        strategy_id, target_date,
        sector_id=sector_id or None,
        market_id=market_id or None,
        limit=int(limit or 0) or None,     # "Todos" viaja como 0
    )

    if not rows_data:
        return None, [], None, "0 activos", True

    # La consulta que se mostró, congelada: el export saca de acá y no de los
    # filtros vivos, que el usuario pudo tocar sin volver a buscar.
    query = {"strategy_id": strategy_id, "date": date_str,
             "sector_id": sector_id or None, "market_id": market_id or None}

    label, truncated = _result_label(len(rows_data), total)
    count = html.Span(label, style={"color": COLOR_WARNING} if truncated else None)
    return rows_data, comp_meta, query, count, False


# ── Armar la grilla (columnas + filas) ────────────────────────────────────────

def _maximos(rows_data: list[dict]) -> tuple[float, dict[str, float]]:
    """Mayor valor absoluto del score total y de cada componente, en una sola
    pasada. Es contra esto que se normaliza cada barra, así que la barra queda
    relativa a lo que estás viendo (y las de una columna, comparables entre sí).
    """
    max_total = 1.0
    por_comp: dict[str, float] = {}
    for r in rows_data:
        if r.get("score") is not None:
            max_total = max(max_total, abs(r["score"]))
        for key, sc in (r.get("comp_scores") or {}).items():
            if sc is not None:
                por_comp[key] = max(por_comp.get(key, 0.0), abs(sc))
    return max_total, por_comp


def _column_defs(comp_meta: list[dict], max_total: float,
                 comp_max: dict[str, float]) -> list[dict]:
    """Columnas fijas + una por señal de la estrategia. El peso va en la
    cabecera (×2) como antes, y también en el tooltip para cuando el nombre de
    la señal no entra."""
    cols = [
        ticker_col("/activo?asset_id={id}", "/historial-senales?asset_id={id}"),
        text_col("name", "Nombre", width=190, muted=True),
        score_col("score", "Score", max_abs=max_total, width=120),
        score_col("delta_score", "Δ", max_abs=None, pos_th=0.5, neg_th=-0.5,
                  plus_sign=True, width=80,
                  header_tooltip="Variación del score contra la fecha anterior"),
    ]
    for c in (comp_meta or []):
        key = c["signal_key"]
        cols.append(score_col(
            key, f"{c['signal_name']}\n×{c['weight']:g}",
            max_abs=comp_max.get(key) or None, width=110,
            header_tooltip=f"{c['signal_name']} — peso ×{c['weight']:g}",
        ))
    return cols


def _row_data(rows_data: list[dict], comp_meta: list[dict]) -> list[dict]:
    """Filas planas: la grilla necesita una clave por columna, mientras que el
    servicio devuelve los componentes anidados en comp_scores."""
    keys = [c["signal_key"] for c in (comp_meta or [])]
    filas = []
    for r in rows_data:
        comp = r.get("comp_scores") or {}
        fila = {
            "asset_id":    r["asset_id"],
            "ticker":      r["ticker"],
            "name":        r["name"],
            "score":       r.get("score"),
            "delta_score": r.get("delta_score"),
        }
        for k in keys:
            fila[k] = comp.get(k)
        filas.append(fila)
    return filas


@callback(
    Output("ss-grid", "columnDefs"),
    Output("ss-grid", "rowData"),
    Input("ss-results-store",    "data"),
    Input("ss-comp-meta",        "data"),
)
def render_grid(rows_data, comp_meta):
    if not rows_data:
        return [], []

    max_total, comp_max = _maximos(rows_data)
    return (_column_defs(comp_meta or [], max_total, comp_max),
            _row_data(rows_data, comp_meta or []))


# ── Exportar a Excel ──────────────────────────────────────────────────────────

@callback(
    Output("ss-download",      "data"),
    Input("ss-btn-export",     "n_clicks"),
    State("ss-query-store",    "data"),
    State("ss-comp-meta",      "data"),
    prevent_initial_call=True,
)
def export_excel(_, query, comp_meta):
    if not query:
        return no_update

    # El Excel lleva el ranking COMPLETO: el tope es de la pantalla (para no
    # colgar el navegador), no del archivo.
    from datetime import date as dt_date
    rows_data, _meta, _total = svc.get_strategy_results_with_breakdown(
        query["strategy_id"], dt_date.fromisoformat(query["date"]),
        sector_id=query.get("sector_id"),
        market_id=query.get("market_id"),
    )
    if not rows_data:
        return no_update

    import io
    import openpyxl
    from dash import dcc as _dcc

    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "Resultados"

    comp_keys  = [c["signal_key"]  for c in (comp_meta or [])]
    comp_names = [c["signal_name"] for c in (comp_meta or [])]

    ws.append(["Ticker", "Nombre", "Score", "Δ Score"] + comp_names)

    for r in rows_data:
        comp_vals = [(r.get("comp_scores") or {}).get(k) for k in comp_keys]
        ws.append([
            r["ticker"], r["name"], r["score"], r.get("delta_score"),
        ] + comp_vals)

    buf = io.BytesIO()
    wb.save(buf)
    buf.seek(0)

    return _dcc.send_bytes(buf.read(), filename="screener_senales.xlsx")
