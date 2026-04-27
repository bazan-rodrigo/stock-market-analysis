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

    # Al cambiar de estrategia, traer fecha más reciente y opciones de filtro
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


# ── Buscar resultados ─────────────────────────────────────────────────────────

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
    Output("ss-result-count",    "children"),
    Input("ss-btn-search",       "n_clicks"),
    State("ss-strategy-sel",     "value"),
    State("ss-date",             "date"),
    State("ss-sector-filter",    "value"),
    State("ss-market-filter",    "value"),
    prevent_initial_call=True,
)
def search_results(_, strategy_id, date_str, sector_id, market_id):
    if not strategy_id or not date_str:
        return html.Div(), ""

    from datetime import date as dt_date
    snap_date = dt_date.fromisoformat(date_str)

    rows_data, comp_meta = svc.get_strategy_results_with_breakdown(
        strategy_id, snap_date,
        sector_id=sector_id or None,
        market_id=market_id or None,
    )

    if not rows_data:
        return (
            html.P(f"Sin resultados para esta estrategia en {snap_date}.",
                   className="text-muted mt-2", style={"fontSize": "0.82rem"}),
            "0 activos",
        )

    # Rango de scores para normalizar barras
    scores = [r["score"] for r in rows_data if r["score"] is not None]
    max_abs_total = max((abs(s) for s in scores), default=1) or 1

    # Scores por componente (para normalizar sus barras individualmente)
    comp_max: dict[str, float] = {}
    for r in rows_data:
        for key, sc in (r["comp_scores"] or {}).items():
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
        for c in comp_meta
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
                r["comp_scores"].get(c["signal_key"]),
                comp_max.get(c["signal_key"], 1) or 1,
            )
            for c in comp_meta
        ]
        rows.append(html.Tr([
            html.Td(
                dbc.Badge(str(r["rank"]), color="secondary"),
                style={**_td, "textAlign": "center"},
            ),
            html.Td(html.Strong(r["ticker"]), style=_td),
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
    return table, f"{len(rows_data)} activos"
