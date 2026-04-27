import json

from dash import Input, Output, State, callback, html, no_update
import dash_bootstrap_components as dbc

import app.services.strategy_service as svc
from app.pages.screener_signals import _th, _td


# ── Opciones de estrategias (carga inicial) ───────────────────────────────────

@callback(
    Output("ss-strategy-sel", "options"),
    Input("ss-strategy-sel",  "id"),
)
def load_strategy_opts(_):
    strategies = svc.get_all_strategies()
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

    snap_date_str = new_date if new_date is not no_update else current_date
    if not snap_date_str or snap_date_str is no_update:
        return new_date, [], []

    snap_date = dt_date.fromisoformat(snap_date_str)
    opts = svc.get_filter_options(strategy_id, snap_date)
    return new_date, opts["sectors"], opts["markets"]


# ── Buscar: guardar resultados en stores ──────────────────────────────────────

@callback(
    Output("ss-results-store", "data"),
    Output("ss-comp-meta",     "data"),
    Output("ss-result-count",  "children"),
    Output("ss-btn-export",    "disabled"),
    Input("ss-btn-search",     "n_clicks"),
    State("ss-strategy-sel",   "value"),
    State("ss-date",           "date"),
    State("ss-sector-filter",  "value"),
    State("ss-market-filter",  "value"),
    prevent_initial_call=True,
)
def do_search(_, strategy_id, date_str, sector_id, market_id):
    if not strategy_id or not date_str:
        return None, [], "", True

    from datetime import date as dt_date
    snap_date = dt_date.fromisoformat(date_str)

    rows_data, comp_meta = svc.get_strategy_results_with_breakdown(
        strategy_id, snap_date,
        sector_id=sector_id or None,
        market_id=market_id or None,
    )

    if not rows_data:
        return None, [], f"0 activos", True

    return rows_data, comp_meta, f"{len(rows_data)} activos", False


# ── Renderizar tabla (desde store + orden) ────────────────────────────────────

def _score_cell(score: float | None, max_abs: float) -> html.Td:
    """Celda de score con mini-barra y valor numérico."""
    if score is None:
        return html.Td("—", style={**_td, "color": "#4b5563", "textAlign": "center"})

    pct = int((score / max_abs) * 50 + 50) if max_abs else 50
    color = (
        "#4ade80" if score >= 20 else
        "#f87171" if score <= -20 else
        "#94a3b8"
    )
    return html.Td(
        html.Div([
            html.Div(
                html.Div(style={"width": f"{pct}%", "height": "100%",
                                "backgroundColor": color, "borderRadius": "2px"}),
                style={"width": "40px", "height": "8px", "backgroundColor": "#1f2937",
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
    elif sort_col == "score":
        rows_data = sorted(rows_data, key=lambda r: (r["score"] or 0), reverse=True)
    # default "rank": ya viene ordenado

    # Rango de scores para normalizar barras
    scores = [r["score"] for r in rows_data if r["score"] is not None]
    max_abs_total = max((abs(s) for s in scores), default=1) or 1

    comp_max: dict[str, float] = {}
    for r in rows_data:
        for key, sc in (r.get("comp_scores") or {}).items():
            if sc is not None:
                comp_max[key] = max(comp_max.get(key, 0), abs(sc))

    # Cabecera
    comp_ths = [
        html.Th(
            html.Div([
                html.Div(c["signal_name"],
                         style={"maxWidth": "90px", "overflow": "hidden",
                                "textOverflow": "ellipsis", "whiteSpace": "nowrap",
                                "fontSize": "0.71rem"}),
                html.Div(f"×{c['weight']:g}",
                         style={"fontSize": "0.68rem", "color": "#6b7280"}),
            ]),
            style=_th,
        )
        for c in (comp_meta or [])
    ]
    header = html.Thead(html.Tr([
        html.Th("Rank",   style={**_th, "width": "44px"}),
        html.Th("Ticker", style=_th),
        html.Th("Nombre", style={**_th, "minWidth": "120px"}),
        html.Th("Score",  style={**_th, "minWidth": "110px"}),
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
                dbc.Badge(str(r["rank"]), color="secondary"),
                style={**_td, "textAlign": "center"},
            ),
            html.Td(
                html.Span([
                    html.A(
                        html.Strong(r["ticker"]),
                        href=f"/chart?asset_id={r['asset_id']}",
                        target="_blank",
                        style={"color": "#93c5fd", "textDecoration": "none"},
                    ),
                    html.A(
                        " hist.",
                        href=f"/historial-senales?asset_id={r['asset_id']}",
                        target="_blank",
                        style={"fontSize": "0.68rem", "color": "#6b7280",
                               "textDecoration": "none", "marginLeft": "4px"},
                    ),
                ]),
                style=_td,
            ),
            html.Td(r["name"],
                    style={**_td, "color": "#9ca3af", "fontSize": "0.76rem",
                           "maxWidth": "180px", "overflow": "hidden",
                           "textOverflow": "ellipsis", "whiteSpace": "nowrap"}),
            _score_cell(r["score"], max_abs_total),
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
    State("ss-results-store",  "data"),
    State("ss-comp-meta",      "data"),
    prevent_initial_call=True,
)
def export_excel(_, rows_data, comp_meta):
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

    ws.append(["Rank", "Ticker", "Nombre", "Score"] + comp_names)

    for r in rows_data:
        comp_vals = [(r.get("comp_scores") or {}).get(k) for k in comp_keys]
        ws.append([r["rank"], r["ticker"], r["name"], r["score"]] + comp_vals)

    buf = io.BytesIO()
    wb.save(buf)
    buf.seek(0)

    return _dcc.send_bytes(buf.read(), filename="screener_senales.xlsx")
