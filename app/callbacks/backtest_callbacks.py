import json
import threading

import dash_bootstrap_components as dbc
import plotly.graph_objects as go
from dash import Input, Output, State, callback, dcc, html, no_update

from app.utils import safe_callback

_BG = "#111827"
_GRID = "#1f2937"
_H_COLORS = ["#38bdf8", "#4ade80", "#fbbf24", "#f472b6", "#a78bfa",
             "#34d399", "#fb923c"]

# Estado del run en curso (thread daemon + polling, mismo patrón que
# Centro de Datos / sincronización de divisas).
_state = {"running": False, "current": 0, "total": 0, "phase": "",
          "error": None, "run_id": None}
_lock = threading.Lock()


def _visible_strategy_ids():
    from app.services.strategy_service import get_visible_strategies
    from app.services.visibility import current_viewer
    return {s.id: s.name for s in get_visible_strategies(*current_viewer())}


def _run_options():
    from app.services.backtest_service import list_runs
    vis = _visible_strategy_ids()
    out = []
    for r in list_runs(list(vis)):
        cfg = json.loads(r.config)
        label = (f"#{r.id} · {vis.get(r.strategy_id, '?')} · "
                 f"{r.created_at:%Y-%m-%d %H:%M} · "
                 f"{'/'.join(str(h) for h in cfg['horizons'])}r · "
                 f"q{cfg['n_quantiles']}")
        if r.status == "done":
            label += f" · {r.n_dates} fechas"
        else:
            label += f" · {r.status.upper()}"
        out.append({"label": label, "value": r.id,
                    "disabled": r.status != "done"})
    return out


# ── Carga inicial ─────────────────────────────────────────────────────────────

@callback(
    Output("bt-strategy-sel", "options"),
    Output("bt-run-sel", "options"),
    Input("bt-strategy-sel", "id"),
)
def load_page(_):
    vis = _visible_strategy_ids()
    return ([{"label": n, "value": i} for i, n in vis.items()],
            _run_options())


# ── Ejecutar run ──────────────────────────────────────────────────────────────

@callback(
    Output("bt-interval", "disabled"),
    Output("bt-progress", "style"),
    Output("bt-alert", "children"),
    Output("bt-alert", "is_open"),
    Output("bt-alert", "color"),
    Input("bt-btn-run", "n_clicks"),
    State("bt-strategy-sel", "value"),
    State("bt-horizons", "value"),
    State("bt-quantiles", "value"),
    State("bt-min-assets", "value"),
    State("bt-date-from", "date"),
    prevent_initial_call=True,
)
@safe_callback(lambda exc: (True, no_update, f"Error: {exc}", True, "danger"))
def start_run(_, strategy_id, horizons, n_quantiles, min_assets, date_from):
    if not strategy_id:
        return no_update, no_update, "Seleccioná una estrategia.", True, "warning"
    if not horizons:
        return no_update, no_update, "Elegí al menos un horizonte.", True, "warning"
    if not _lock.acquire(blocking=False):
        return no_update, no_update, "Ya hay un backtest en curso.", True, "warning"

    try:
        from app.services.backtest_service import normalize_config
        from app.services.visibility import current_viewer
        config = normalize_config({
            "horizons": horizons, "n_quantiles": n_quantiles or 10,
            "min_assets": min_assets or 20, "date_from": date_from,
        })
        owner_id, _is_admin = current_viewer()
    except BaseException:
        _lock.release()
        raise

    _state.update({"running": True, "current": 0, "total": 0,
                   "phase": "", "error": None, "run_id": None})

    def _run():
        from app.database import Session
        from app.services.backtest_service import run_backtest

        def _progress(cur, tot, phase):
            _state["current"], _state["total"], _state["phase"] = cur, tot, phase

        try:
            _state["run_id"] = run_backtest(int(strategy_id), config,
                                            owner_id=owner_id)
        except Exception as exc:
            _state["error"] = str(exc)
        finally:
            _state["running"] = False
            _lock.release()
            Session.remove()

    threading.Thread(target=_run, daemon=True).start()
    return (False, {"display": "block", "height": "16px", "fontSize": "0.72rem"},
            "Ejecutando backtest…", True, "info")


# ── Polling ───────────────────────────────────────────────────────────────────

@callback(
    Output("bt-progress", "value"),
    Output("bt-progress", "label"),
    Output("bt-progress", "style", allow_duplicate=True),
    Output("bt-interval", "disabled", allow_duplicate=True),
    Output("bt-alert", "children", allow_duplicate=True),
    Output("bt-alert", "is_open", allow_duplicate=True),
    Output("bt-alert", "color", allow_duplicate=True),
    Output("bt-run-sel", "options", allow_duplicate=True),
    Output("bt-run-sel", "value"),
    Input("bt-interval", "n_intervals"),
    prevent_initial_call=True,
)
def poll_run(_):
    _hidden = {"display": "none"}
    if _state["running"]:
        cur, tot = _state["current"], _state["total"] or 1
        pct = int(cur / tot * 100)
        label = f"{_state['phase']} {cur}/{_state['total']}" if _state["total"] else "Iniciando…"
        return (pct, label, no_update, False,
                no_update, True, no_update, no_update, no_update)
    if _state["error"]:
        return (0, "", _hidden, True, f"Error: {_state['error']}", True,
                "danger", _run_options(), no_update)
    return (100, "Completo", _hidden, True, "Backtest terminado.", True,
            "success", _run_options(), _state["run_id"])


# ── Resultados ────────────────────────────────────────────────────────────────

def _fig_layout(fig, title, ytitle, ysuffix=""):
    fig.update_layout(
        title=dict(text=title, font=dict(size=13, color="#dee2e6")),
        plot_bgcolor=_BG, paper_bgcolor=_BG,
        font=dict(color="#dee2e6", size=11),
        margin=dict(l=50, r=20, t=40, b=40),
        xaxis=dict(gridcolor=_GRID),
        yaxis=dict(title=ytitle, gridcolor=_GRID, ticksuffix=ysuffix),
        legend=dict(orientation="h", y=1.12, font=dict(size=10)),
        height=340,
    )
    return fig


def _rolling_mean(values, window=60):
    out, acc = [], []
    for v in values:
        acc.append(v)
        if len(acc) > window:
            acc.pop(0)
        out.append(sum(acc) / len(acc))
    return out


@callback(
    Output("bt-results", "children"),
    Input("bt-run-sel", "value"),
    prevent_initial_call=True,
)
@safe_callback(lambda exc: dbc.Alert(f"Error: {exc}", color="danger"))
def show_results(run_id):
    if not run_id:
        return None
    from app.services.backtest_service import get_run_results
    res = get_run_results(int(run_id))
    if res is None or res["run"].strategy_id not in _visible_strategy_ids():
        return dbc.Alert("Corrida no encontrada.", color="warning")

    run, cfg = res["run"], res["config"]
    horizons = cfg["horizons"]

    # ── Tarjetas resumen por horizonte ────────────────────────────────────
    cards = []
    for h in horizons:
        ic = res["ic_summary"].get(h)
        body = [html.Div(f"Horizonte {h} ruedas", className="fw-semibold mb-1",
                         style={"fontSize": "0.8rem"})]
        if ic:
            body += [
                html.Div(f"IC medio: {ic['mean']:.3f}"
                         + (f"  (t={ic['t']:.1f})" if ic["t"] else ""),
                         style={"fontSize": "0.78rem"}),
                html.Div(f"IC > 0: {ic['pct_pos']*100:.0f}% de las fechas",
                         style={"fontSize": "0.78rem"}),
            ]
        else:
            body.append(html.Div("IC no computable (universo chico)",
                                 style={"fontSize": "0.78rem", "color": "#9ca3af"}))
        cards.append(dbc.Col(dbc.Card(dbc.CardBody(body), style={
            "backgroundColor": "#1f2937", "border": "1px solid #374151"}),
            md=3, className="mb-2"))

    # ── Barras: retorno medio por cuantil ─────────────────────────────────
    fig_q = go.Figure()
    for i, h in enumerate(horizons):
        qs = [st for st in res["quantile_stats"] if st.horizon == h]
        fig_q.add_bar(
            x=[st.quantile for st in qs],
            y=[(st.mean_ret or 0) * 100 for st in qs],
            name=f"{h}r", marker_color=_H_COLORS[i % len(_H_COLORS)])
    _fig_layout(fig_q, "Retorno medio por cuantil (equal-weight por fecha; "
                       f"cuantil {cfg['n_quantiles']} = mejor score)",
                "Retorno medio", "%")
    fig_q.update_layout(barmode="group",
                        xaxis=dict(title="Cuantil", dtick=1, gridcolor=_GRID))

    # ── Series: IC rolling y spread rolling ───────────────────────────────
    fig_ic, fig_sp = go.Figure(), go.Figure()
    for i, h in enumerate(horizons):
        pts = [p for p in res["ic_points"] if p.horizon == h]
        color = _H_COLORS[i % len(_H_COLORS)]
        ics = [(p.date, p.ic) for p in pts if p.ic is not None]
        if ics:
            fig_ic.add_scatter(
                x=[d for d, _ in ics],
                y=_rolling_mean([v for _, v in ics]),
                mode="lines", name=f"{h}r", line=dict(color=color, width=1.5))
        sps = [(p.date, p.spread) for p in pts if p.spread is not None]
        if sps:
            fig_sp.add_scatter(
                x=[d for d, _ in sps],
                y=[v * 100 for v in _rolling_mean([v for _, v in sps])],
                mode="lines", name=f"{h}r", line=dict(color=color, width=1.5))
    _fig_layout(fig_ic, "IC (Spearman) — media móvil 60 fechas", "IC")
    fig_ic.add_hline(y=0, line_color="#6b7280", line_width=1)
    _fig_layout(fig_sp, "Spread top − bottom — media móvil 60 fechas",
                "Spread", "%")
    fig_sp.add_hline(y=0, line_color="#6b7280", line_width=1)

    meta = (f"Run #{run.id} · {run.date_from} → {run.date_to} · "
            f"{run.n_dates} fechas · lag {cfg['lag']} · "
            f"mín. {cfg['min_assets']} activos/fecha"
            + (f" · {run.duration_seconds:.1f}s" if run.duration_seconds else ""))

    return html.Div([
        html.Div(meta, className="text-muted mb-2", style={"fontSize": "0.75rem"}),
        dbc.Row(cards, className="g-2"),
        dcc.Graph(figure=fig_q, config={"displayModeBar": False}),
        dcc.Graph(figure=fig_ic, config={"displayModeBar": False}),
        dcc.Graph(figure=fig_sp, config={"displayModeBar": False}),
    ])
