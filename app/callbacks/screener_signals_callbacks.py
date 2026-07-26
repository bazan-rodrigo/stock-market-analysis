from dash import Input, Output, State, callback, html, no_update

import app.services.strategy_service as svc
# Directo del origen y no vía app.pages.screener_signals: importar la página
# dispara su register_page, que exige la app ya instanciada.
from app.components.ui_constants import (
    BG_CARD, COLOR_NEGATIVE, COLOR_NEUTRAL, COLOR_POSITIVE, TD as _td, TEXT_DIM,
    TEXT_FAINT, TEXT_MUTED, TH_NOWRAP as _th
)


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
    count = html.Span(label, style={"color": "#f59e0b"} if truncated else None)
    return rows_data, comp_meta, query, count, False


# ── Renderizar tabla (desde store + orden) ────────────────────────────────────

def _score_cell(score: float | None, max_abs: float) -> html.Td:
    """Celda de score con mini-barra y valor numérico."""
    if score is None:
        return html.Td("—", style={**_td, "color": TEXT_FAINT, "textAlign": "center"})

    pct = int((score / max_abs) * 50 + 50) if max_abs else 50
    color = (
        COLOR_POSITIVE if score >= 20 else
        COLOR_NEGATIVE if score <= -20 else
        COLOR_NEUTRAL
    )
    return html.Td(
        html.Div([
            html.Div(
                html.Div(style={"width": f"{pct}%", "height": "100%",
                                "backgroundColor": color, "borderRadius": "2px"}),
                style={"width": "40px", "height": "8px", "backgroundColor": BG_CARD,
                       "borderRadius": "2px", "overflow": "hidden", "display": "inline-block",
                       "verticalAlign": "middle"},
            ),
            html.Span(f"{score:.1f}",
                      style={"fontSize": "0.74rem", "color": color,
                             "marginLeft": "4px", "fontFamily": "monospace",
                             "verticalAlign": "middle"}),
        ]),
        style={**_td, "whiteSpace": "nowrap"},
    )


def _delta_cell(delta_score: float | None) -> html.Td:
    """Celda compacta de variación del score respecto de la fecha anterior."""
    if delta_score is None:
        return html.Td("—", style={**_td, "color": TEXT_FAINT, "textAlign": "center"})

    color  = COLOR_POSITIVE if delta_score > 0.5 else COLOR_NEGATIVE if delta_score < -0.5 else COLOR_NEUTRAL
    prefix = "+" if delta_score > 0 else ""

    return html.Td(
        html.Span(f"{prefix}{delta_score:.1f}",
                  style={"fontSize": "0.74rem", "color": color, "fontFamily": "monospace"}),
        style={**_td, "textAlign": "center", "whiteSpace": "nowrap"},
    )


@callback(
    Output("ss-table-container", "children"),
    Input("ss-results-store",    "data"),
    Input("ss-comp-meta",        "data"),
    Input("ss-sort-col",         "value"),
)
def render_table(rows_data, comp_meta, sort_col):
    if not rows_data:
        return html.Div()

    # Ordenar
    if sort_col == "ticker":
        rows_data = sorted(rows_data, key=lambda r: r["ticker"])
    elif sort_col == "delta_score":
        rows_data = sorted(rows_data,
                           key=lambda r: (r.get("delta_score") is None, -(r.get("delta_score") or 0)))
    # default "score": ya viene ordenado por score desc desde el servicio

    # Rango de scores (pasada única para max_abs_total y comp_max)
    max_abs_total = 1
    comp_max: dict[str, float] = {}
    for r in rows_data:
        if r["score"] is not None:
            max_abs_total = max(max_abs_total, abs(r["score"]))
        for key, sc in (r.get("comp_scores") or {}).items():
            if sc is not None:
                comp_max[key] = max(comp_max.get(key, 0), abs(sc))
    max_abs_total = max_abs_total or 1

    # Cabecera
    comp_ths = [
        html.Th(
            html.Div([
                html.Div(c["signal_name"],
                         style={"maxWidth": "90px", "overflow": "hidden",
                                "textOverflow": "ellipsis", "whiteSpace": "nowrap",
                                "fontSize": "0.71rem"}),
                html.Div(f"×{c['weight']:g}",
                         style={"fontSize": "0.68rem", "color": TEXT_DIM}),
            ]),
            style=_th,
        )
        for c in (comp_meta or [])
    ]
    header = html.Thead(html.Tr([
        html.Th("Ticker", style=_th),
        html.Th("Nombre", style={**_th, "minWidth": "120px"}),
        html.Th("Score",  style={**_th, "minWidth": "110px"}),
        html.Th("Δ",      style={**_th, "minWidth": "60px", "textAlign": "center"}),
        *comp_ths,
    ]))

    # Filas
    rows = []
    for r in rows_data:
        comp_tds = [
            _score_cell(
                (r.get("comp_scores") or {}).get(c["signal_key"]),
                comp_max.get(c["signal_key"], 1) or 1,
            )
            for c in (comp_meta or [])
        ]
        rows.append(html.Tr([
            html.Td(
                html.Span([
                    html.A(
                        html.Strong(r["ticker"]),
                        href=f"/activo?asset_id={r['asset_id']}",
                        target="_blank",
                        style={"color": "#93c5fd", "textDecoration": "none"},
                    ),
                    html.A(
                        " hist.",
                        href=f"/historial-senales?asset_id={r['asset_id']}",
                        target="_blank",
                        style={"fontSize": "0.68rem", "color": TEXT_DIM,
                               "textDecoration": "none", "marginLeft": "4px"},
                    ),
                ]),
                style=_td,
            ),
            html.Td(r["name"],
                    style={**_td, "color": TEXT_MUTED, "fontSize": "0.76rem",
                           "maxWidth": "180px", "overflow": "hidden",
                           "textOverflow": "ellipsis", "whiteSpace": "nowrap"}),
            _score_cell(r["score"], max_abs_total),
            _delta_cell(r.get("delta_score")),
            *comp_tds,
        ]))

    table = html.Table(
        [header, html.Tbody(rows)],
        style={"width": "100%", "borderCollapse": "collapse"},
    )
    return table


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
