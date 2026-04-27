import plotly.graph_objects as go
from dash import Input, Output, State, callback, html, no_update
import dash_bootstrap_components as dbc
from dash import dcc

import app.services.strategy_service as svc


# ── Opciones iniciales ────────────────────────────────────────────────────────

@callback(
    Output("hm-strategy-sel", "options"),
    Input("hm-strategy-sel",  "id"),
)
def load_strategy_opts(_):
    strategies = svc.get_all_strategies()
    return [{"label": s.name, "value": s.id} for s in strategies]


# ── Al elegir estrategia: auto-fecha y opciones de filtro ─────────────────────

@callback(
    Output("hm-date",          "date"),
    Output("hm-sector-filter", "options"),
    Output("hm-market-filter", "options"),
    Input("hm-strategy-sel",   "value"),
    Input("hm-date",           "date"),
    prevent_initial_call=True,
)
def update_filters(strategy_id, current_date):
    if not strategy_id:
        return no_update, [], []

    from datetime import date as dt_date
    from dash import ctx

    new_date = no_update
    if ctx.triggered_id == "hm-strategy-sel":
        dates = svc.get_available_dates(strategy_id)
        new_date = str(dates[0]) if dates else no_update

    snap_date_str = new_date if new_date is not no_update else current_date
    if not snap_date_str or snap_date_str is no_update:
        return new_date, [], []

    snap_date = dt_date.fromisoformat(snap_date_str)
    opts = svc.get_filter_options(strategy_id, snap_date)
    return new_date, opts["sectors"], opts["markets"]


# ── Renderizar heatmap ────────────────────────────────────────────────────────

@callback(
    Output("hm-chart-container", "children"),
    Output("hm-result-count",    "children"),
    Input("hm-btn-view",         "n_clicks"),
    State("hm-strategy-sel",     "value"),
    State("hm-date",             "date"),
    State("hm-sector-filter",    "value"),
    State("hm-market-filter",    "value"),
    State("hm-top-n",            "value"),
    prevent_initial_call=True,
)
def render_heatmap(_, strategy_id, date_str, sector_id, market_id, top_n):
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

    # Limitar a top N
    if top_n and top_n > 0:
        rows_data = rows_data[:top_n]

    total_shown = len(rows_data)

    # Señales (columnas)
    sig_keys  = [c["signal_key"]  for c in comp_meta]
    sig_names = [c["signal_name"] for c in comp_meta]

    # Activos (filas) — ya vienen ordenados por rank (mejor arriba)
    tickers   = [r["ticker"] for r in rows_data]
    # Añadimos score total al label del eje Y para contexto
    y_labels  = [
        f"{r['ticker']} ({r['score']:+.0f})" if r["score"] is not None
        else r["ticker"]
        for r in rows_data
    ]

    # Matriz de scores
    z    = []
    text = []
    for r in rows_data:
        cs = r.get("comp_scores") or {}
        row_z    = []
        row_text = []
        for key in sig_keys:
            sc = cs.get(key)
            row_z.append(sc)
            row_text.append(f"{sc:.0f}" if sc is not None else "—")
        z.append(row_z)
        text.append(row_text)

    # ── Plotly Heatmap ────────────────────────────────────────────────────────
    cell_h   = max(18, min(36, 900 // max(total_shown, 1)))
    chart_h  = max(320, total_shown * cell_h + 120)

    fig = go.Figure(go.Heatmap(
        z=z,
        x=sig_names,
        y=y_labels,
        text=text,
        texttemplate="%{text}",
        textfont={"size": 10},
        colorscale=[
            [0.0,  "#b91c1c"],   # -100  rojo oscuro
            [0.25, "#ef4444"],   # -50
            [0.45, "#374151"],   # -10  gris neutro
            [0.5,  "#4b5563"],   # 0    gris
            [0.55, "#374151"],   # +10
            [0.75, "#22c55e"],   # +50
            [1.0,  "#166534"],   # +100 verde oscuro
        ],
        zmin=-100,
        zmax=100,
        hoverongaps=False,
        hovertemplate=(
            "<b>%{y}</b><br>"
            "Señal: %{x}<br>"
            "Score: %{z:.1f}<extra></extra>"
        ),
    ))

    fig.update_layout(
        paper_bgcolor="#111827",
        plot_bgcolor="#111827",
        font={"color": "#d1d5db", "size": 11},
        margin={"l": 120, "r": 16, "t": 32, "b": 120},
        xaxis={
            "side": "top",
            "tickangle": -40,
            "tickfont": {"size": 10},
            "linecolor": "#374151",
        },
        yaxis={
            "autorange": "reversed",
            "tickfont": {"size": 10},
            "linecolor": "#374151",
        },
        coloraxis_showscale=True,
    )

    # Línea de score total (barra lateral derecha con texto)
    chart = dbc.Card(
        dbc.CardBody(
            dcc.Graph(
                figure=fig,
                config={"displayModeBar": False},
                style={"height": f"{chart_h}px"},
            ),
            style={"padding": "8px"},
        ),
        style={"backgroundColor": "#1f2937", "border": "1px solid #374151"},
    )

    count_str = (
        f"{total_shown} activos"
        + (f" (top {top_n})" if top_n and top_n > 0 and total_shown == top_n else "")
    )
    return chart, count_str
