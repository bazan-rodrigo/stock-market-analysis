from datetime import date as dt_date

import plotly.graph_objects as go
from dash import Input, Output, State, callback, html, dcc
import dash_bootstrap_components as dbc

import app.services.strategy_service as svc

from app.components.ui_constants import CHART_PALETTE as _PALETTE


# ── Opciones de estrategias ───────────────────────────────────────────────────

@callback(
    Output("sth-strategy-sel", "options"),
    Input("sth-strategy-sel",  "id"),
)
def load_strategy_opts(_):
    from app.services.visibility import current_viewer
    strategies = svc.get_visible_strategies(*current_viewer())
    return [{"label": s.name, "value": s.id} for s in strategies]


# ── Cargar top activos como sugerencia para el selector ───────────────────────

@callback(
    Output("sth-asset-sel",         "options"),
    Output("sth-asset-sel",         "value"),
    Output("sth-asset-picker-row",  "style"),
    Input("sth-btn-load",           "n_clicks"),
    State("sth-strategy-sel",       "value"),
    State("sth-date-to",            "date"),
    prevent_initial_call=True,
)
def load_asset_suggestions(_, strategy_id, date_to_str):
    _hidden  = {"display": "none"}
    _visible = {}

    if not strategy_id:
        return [], [], _hidden

    target_date = dt_date.fromisoformat(date_to_str) if date_to_str else dt_date.today()

    # Usar la fecha más reciente disponible si la indicada no tiene datos
    dates = svc.get_available_dates(strategy_id)
    if not dates:
        return [], [], _hidden

    # Tomar la fecha más próxima al date_to
    best_date = min(dates, key=lambda d: abs((d - target_date).days))
    top_assets = svc.get_top_assets_for_strategy(strategy_id, best_date, limit=30)

    if not top_assets:
        return [], [], _hidden

    opts = [
        {"label": f"{r['ticker']} ({r['score']:+.0f})", "value": r["asset_id"]}
        for r in top_assets
    ]
    # Pre-seleccionar top 10
    default_sel = [r["asset_id"] for r in top_assets[:10]]

    return opts, default_sel, _visible


# ── Renderizar gráfico al cambiar selección de activos o modo ─────────────────

@callback(
    Output("sth-chart-container", "children"),
    Input("sth-btn-view",         "n_clicks"),
    State("sth-strategy-sel",     "value"),
    State("sth-asset-sel",        "value"),
    State("sth-date-from",        "date"),
    State("sth-date-to",          "date"),
    prevent_initial_call=True,
)
def render_chart(_, strategy_id, asset_ids, date_from_str, date_to_str):
    if not strategy_id or not asset_ids:
        return html.P("Seleccioná una estrategia y activos.",
                      className="text-muted", style={"fontSize": "0.82rem"})

    date_from = dt_date.fromisoformat(date_from_str) if date_from_str else None
    date_to   = dt_date.fromisoformat(date_to_str)   if date_to_str   else None

    # Obtener nombres de activos para labels
    from app.database import get_session
    from app.models import Asset
    s = get_session()
    assets_map = {
        a.id: a.ticker
        for a in s.query(Asset).filter(Asset.id.in_(asset_ids)).all()
    }

    history = svc.get_strategy_score_history(
        strategy_id, asset_ids, date_from, date_to
    )

    assets_with_data = [aid for aid in asset_ids if history.get(aid)]
    if not assets_with_data:
        return html.P("Sin datos de estrategia para los activos seleccionados "
                      "en el período indicado.",
                      className="text-muted mt-2", style={"fontSize": "0.82rem"})

    # ── Gráfico (score en el tiempo) ──────────────────────────────────────────
    fig = go.Figure()

    fig.add_hrect(y0=20,   y1=100, fillcolor="#4ade80", opacity=0.04, line_width=0)
    fig.add_hrect(y0=-100, y1=-20, fillcolor="#f87171", opacity=0.04, line_width=0)
    fig.add_hline(y=0,  line_dash="dot", line_color="#374151",   line_width=1)
    # rgba y no hex de 8 dígitos (#RRGGBBAA): el validador de plotly
    # para shapes no acepta hex con alfa
    fig.add_hline(y=20, line_dash="dot", line_color="rgba(74, 222, 128, 0.27)", line_width=1)
    fig.add_hline(y=-20,line_dash="dot", line_color="rgba(248, 113, 113, 0.27)", line_width=1)

    for i, aid in enumerate(assets_with_data):
        pts   = history[aid]
        dates  = [p[0] for p in pts]
        values = [p[1] for p in pts]
        ticker = assets_map.get(aid, str(aid))
        color  = _PALETTE[i % len(_PALETTE)]

        fig.add_trace(go.Scatter(
            x=dates, y=values,
            mode="lines+markers",
            name=ticker,
            line={"color": color, "width": 1.5},
            marker={"size": 4, "color": color},
            hovertemplate=(
                f"<b>{ticker}</b><br>%{{x|%Y-%m-%d}}<br>Score: %{{y:.1f}}<extra></extra>"
            ),
        ))

    yaxis_cfg = {
        "gridcolor": "#1f2937",
        "linecolor": "#374151",
        "zeroline":  False,
        "range":     [-110, 110],
        "tickvals":  [-100, -60, -20, 0, 20, 60, 100],
    }

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
        },
        xaxis={
            "gridcolor": "#1f2937",
            "linecolor": "#374151",
            "tickformat": "%Y-%m-%d",
        },
        yaxis=yaxis_cfg,
        hovermode="x unified",
    )

    return dbc.Card(
        dbc.CardBody(
            dcc.Graph(figure=fig, config={"displayModeBar": False},
                      style={"height": "440px"}),
            style={"padding": "8px"},
        ),
        style={"backgroundColor": "#1f2937", "border": "1px solid #374151"},
    )
