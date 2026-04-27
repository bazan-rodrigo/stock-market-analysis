from dash import Input, Output, callback, html, no_update
import dash_bootstrap_components as dbc

import app.services.strategy_service as svc
from app.pages.screener_signals import _th, _td


# ── Cargar opciones de estrategias ────────────────────────────────────────────

@callback(
    Output("ss-strategy-sel", "options"),
    Input("ss-strategy-sel",  "id"),   # dispara en carga inicial
)
def load_strategy_opts(_):
    strategies = svc.get_all_strategies()
    return [{"label": s.name, "value": s.id} for s in strategies]


# ── Cargar fechas disponibles al elegir estrategia ────────────────────────────

@callback(
    Output("ss-date", "date"),
    Input("ss-strategy-sel", "value"),
)
def update_date(strategy_id):
    if not strategy_id:
        return no_update
    dates = svc.get_available_dates(strategy_id)
    return str(dates[0]) if dates else no_update


# ── Buscar resultados ─────────────────────────────────────────────────────────

@callback(
    Output("ss-table-container", "children"),
    Output("ss-result-count",    "children"),
    Input("ss-btn-search",       "n_clicks"),
    Input("ss-strategy-sel",     "value"),
    Input("ss-date",             "date"),
)
def search_results(_, strategy_id, date_str):
    if not strategy_id or not date_str:
        return html.Div(), ""

    from datetime import date as dt_date
    snap_date = dt_date.fromisoformat(date_str)

    rows_data = svc.get_strategy_results(strategy_id, snap_date)

    if not rows_data:
        return (
            html.P(f"Sin resultados para esta estrategia en {snap_date}.",
                   className="text-muted mt-2", style={"fontSize": "0.82rem"}),
            "0 activos",
        )

    # Rango de scores para normalizar la barra
    scores = [r["score"] for r in rows_data if r["score"] is not None]
    max_abs = max((abs(s) for s in scores), default=1) or 1

    rows = []
    for r in rows_data:
        score = r["score"]
        pct   = int((score / max_abs) * 50 + 50) if score is not None else 50
        bar_color = (
            "#4ade80" if score is not None and score >= 20 else
            "#f87171" if score is not None and score <= -20 else
            "#94a3b8"
        )
        bar = html.Div(
            html.Div(style={
                "width": f"{pct}%",
                "height": "100%",
                "backgroundColor": bar_color,
                "borderRadius": "2px",
                "transition": "width 0.2s",
            }),
            style={
                "width": "100%", "height": "12px",
                "backgroundColor": "#1f2937",
                "borderRadius": "2px", "overflow": "hidden",
            },
        )

        rows.append(html.Tr([
            html.Td(
                dbc.Badge(str(r["rank"]), color="secondary"),
                style={**_td, "width": "48px", "textAlign": "center"},
            ),
            html.Td(html.Strong(r["ticker"]), style=_td),
            html.Td(r["name"] or "—",
                    style={**_td, "color": "#9ca3af", "fontSize": "0.78rem",
                           "maxWidth": "240px", "overflow": "hidden",
                           "textOverflow": "ellipsis", "whiteSpace": "nowrap"}),
            html.Td(
                html.Div([
                    bar,
                    html.Span(
                        f"{score:.1f}" if score is not None else "—",
                        style={"fontSize": "0.76rem", "color": "#9ca3af",
                               "marginLeft": "6px", "fontFamily": "monospace"},
                    ),
                ], style={"display": "flex", "alignItems": "center", "gap": "4px"}),
                style={**_td, "minWidth": "180px"},
            ),
        ]))

    table = html.Table([
        html.Thead(html.Tr([
            html.Th("Rank",    style={**_th, "width": "48px"}),
            html.Th("Ticker",  style=_th),
            html.Th("Nombre",  style=_th),
            html.Th("Score",   style={**_th, "minWidth": "180px"}),
        ])),
        html.Tbody(rows),
    ], style={"width": "100%", "borderCollapse": "collapse"})

    return table, f"{len(rows_data)} activos"
