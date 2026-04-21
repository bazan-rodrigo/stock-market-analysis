from datetime import date as _date

from dash import Input, Output, State, callback, no_update
import plotly.graph_objects as go

import app.services.pair_analysis_service as svc
from app.services.asset_service import get_assets


# ── Poblar dropdowns ──────────────────────────────────────────────────────────

@callback(
    Output("pair-asset1", "options"),
    Output("pair-asset2", "options"),
    Input("pair-asset1", "id"),
)
def load_options(_):
    opts = [{"label": f"{a.ticker} — {a.name}", "value": a.id} for a in get_assets()]
    return opts, opts


# ── Calcular y renderizar los tres gráficos ───────────────────────────────────

@callback(
    Output("pair-graph-comp",    "figure"),
    Output("pair-graph-ratio",   "figure"),
    Output("pair-graph-scatter", "figure"),
    Output("pair-alert",         "children"),
    Output("pair-alert",         "is_open"),
    Input("pair-btn-analizar",   "n_clicks"),
    State("pair-asset1",         "value"),
    State("pair-asset2",         "value"),
    State("pair-date-from",      "date"),
    State("pair-date-to",        "date"),
    State("pair-log-scale",      "value"),
    prevent_initial_call=True,
)
def update_charts(n_clicks, asset1, asset2, date_from, date_to, log_scale):
    empty = go.Figure()

    if not asset1 or not asset2:
        return empty, empty, empty, "Seleccioná ambos activos antes de analizar.", True

    if asset1 == asset2:
        return empty, empty, empty, "Los dos activos deben ser distintos.", True

    from_date = _date.fromisoformat(date_from) if date_from else None
    to_date   = _date.fromisoformat(date_to)   if date_to   else None

    label1, label2, df1, df2, merged, error = svc.get_pair_data(
        asset1, asset2, from_date, to_date
    )

    if error and merged is None:
        return empty, empty, empty, error, True

    fig_comp    = svc.build_comparison_fig(df1, df2, label1, label2, log_scale)
    fig_ratio   = svc.build_ratio_fig(merged, label1, label2, log_scale) if merged is not None else empty
    fig_scatter = svc.build_scatter_fig(merged, label1, label2)           if merged is not None else empty

    if error:
        return fig_comp, fig_ratio, fig_scatter, error, True

    return fig_comp, fig_ratio, fig_scatter, no_update, False
