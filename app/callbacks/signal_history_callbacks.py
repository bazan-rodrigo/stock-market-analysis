from datetime import date as dt_date

import plotly.graph_objects as go
from dash import Input, Output, State, callback, html, no_update
import dash_bootstrap_components as dbc

import app.services.signal_history_service as svc
from app.services.asset_service import get_assets
from app.services.strategy_service import get_all_strategies
from app.pages.signal_history import _th, _td

_PALETTE = [
    "#60a5fa", "#34d399", "#fbbf24", "#f87171", "#a78bfa",
    "#fb923c", "#38bdf8", "#4ade80", "#e879f9", "#facc15",
]


# ── Opciones de activos ───────────────────────────────────────────────────────

@callback(
    Output("sh-asset-sel",    "options"),
    Output("sh-strategy-sel", "options"),
    Input("sh-asset-sel",     "id"),
)
def load_opts(_):
    assets = get_assets()
    asset_opts = [
        {"label": f"{a.ticker} — {a.name or a.ticker}", "value": a.id}
        for a in assets
    ]
    strats = get_all_strategies()
    strat_opts = [{"label": s.name, "value": s.id} for s in strats]
    return asset_opts, strat_opts


# ── Pre-seleccionar activo desde URL (?asset_id=...) ─────────────────────────

@callback(
    Output("sh-asset-sel", "value"),
    Input("sh-url",        "search"),
    prevent_initial_call=True,
)
def preselect_from_url(search):
    if not search:
        return no_update
    from urllib.parse import parse_qs
    params = parse_qs(search.lstrip("?"))
    ids = params.get("asset_id", [])
    if not ids:
        return no_update
    try:
        return int(ids[0])
    except (ValueError, IndexError):
        return no_update


# ── Renderizar gráfico + tabla ────────────────────────────────────────────────

@callback(
    Output("sh-chart-container", "children"),
    Output("sh-table-container", "children"),
    Input("sh-btn-view",         "n_clicks"),
    State("sh-asset-sel",        "value"),
    State("sh-strategy-sel",     "value"),
    State("sh-date-from",        "date"),
    State("sh-date-to",          "date"),
    prevent_initial_call=True,
)
def render(_, asset_id, strategy_id, date_from_str, date_to_str):
    if not asset_id:
        return html.P("Seleccioná un activo.", className="text-muted",
                      style={"fontSize": "0.82rem"}), html.Div()

    date_from = dt_date.fromisoformat(date_from_str) if date_from_str else None
    date_to   = dt_date.fromisoformat(date_to_str)   if date_to_str   else None

    # Señales a mostrar
    if strategy_id:
        signals = svc.get_signals_for_strategy(strategy_id)
    else:
        signals = svc.get_all_signals_flat()

    if not signals:
        return html.P("Sin señales disponibles.", className="text-muted",
                      style={"fontSize": "0.82rem"}), html.Div()

    sig_ids = [s.id for s in signals]
    sig_by_id = {s.id: s for s in signals}

    history = svc.get_asset_signal_history(asset_id, sig_ids, date_from, date_to)

    # Filtrar señales sin datos
    signals_with_data = [s for s in signals if history.get(s.id)]
    if not signals_with_data:
        return html.P("Sin datos de señales para este activo en el período seleccionado.",
                      className="text-muted mt-2", style={"fontSize": "0.82rem"}), html.Div()

    # ── Gráfico ───────────────────────────────────────────────────────────────
    fig = go.Figure()

    # Bandas de referencia
    fig.add_hrect(y0=20,  y1=100, fillcolor="#4ade80", opacity=0.04, line_width=0)
    fig.add_hrect(y0=-100, y1=-20, fillcolor="#f87171", opacity=0.04, line_width=0)
    fig.add_hline(y=0,  line_dash="dot", line_color="#374151", line_width=1)
    fig.add_hline(y=20, line_dash="dot", line_color="#4ade8044", line_width=1)
    fig.add_hline(y=-20,line_dash="dot", line_color="#f8717144", line_width=1)

    for i, sig in enumerate(signals_with_data):
        pts = history[sig.id]
        dates  = [p[0] for p in pts]
        scores = [p[1] for p in pts]
        color  = _PALETTE[i % len(_PALETTE)]
        fig.add_trace(go.Scatter(
            x=dates, y=scores,
            mode="lines+markers",
            name=sig.name,
            line={"color": color, "width": 1.5},
            marker={"size": 4, "color": color},
            hovertemplate=f"<b>{sig.name}</b><br>%{{x|%Y-%m-%d}}<br>Score: %{{y:.1f}}<extra></extra>",
        ))

    fig.update_layout(
        paper_bgcolor="#111827",
        plot_bgcolor="#111827",
        font={"color": "#d1d5db", "size": 11},
        margin={"l": 48, "r": 16, "t": 24, "b": 40},
        legend={
            "bgcolor": "#1f2937",
            "bordercolor": "#374151",
            "borderwidth": 1,
            "font": {"size": 10},
            "orientation": "v",
        },
        xaxis={
            "gridcolor": "#1f2937",
            "linecolor": "#374151",
            "tickformat": "%Y-%m-%d",
        },
        yaxis={
            "gridcolor": "#1f2937",
            "linecolor": "#374151",
            "range": [-110, 110],
            "tickvals": [-100, -60, -20, 0, 20, 60, 100],
            "zeroline": False,
        },
        hovermode="x unified",
    )

    chart = dbc.Card(
        dbc.CardBody(
            dcc.Graph(figure=fig, config={"displayModeBar": False},
                      style={"height": "420px"}),
            style={"padding": "8px"},
        ),
        style={"backgroundColor": "#1f2937", "border": "1px solid #374151"},
    )

    # ── Tabla resumen (último valor disponible por señal) ─────────────────────
    table_rows = []
    for sig in signals_with_data:
        pts   = history[sig.id]
        last_dt, last_score = pts[-1]
        color = (
            "#4ade80" if last_score >= 20 else
            "#f87171" if last_score <= -20 else
            "#94a3b8"
        )
        table_rows.append(html.Tr([
            html.Td(html.Code(sig.key,
                              style={"fontSize": "0.76rem", "color": "#6b7280"}),
                    style=_td),
            html.Td(sig.name, style=_td),
            html.Td(str(last_dt), style={**_td, "color": "#9ca3af"}),
            html.Td(
                html.Strong(f"{last_score:.1f}", style={"color": color, "fontFamily": "monospace"}),
                style=_td,
            ),
        ]))

    summary = html.Table([
        html.Thead(html.Tr([
            html.Th("Key",           style=_th),
            html.Th("Señal",         style=_th),
            html.Th("Última fecha",  style=_th),
            html.Th("Último score",  style=_th),
        ])),
        html.Tbody(table_rows),
    ], style={"width": "100%", "borderCollapse": "collapse"})

    return chart, summary
