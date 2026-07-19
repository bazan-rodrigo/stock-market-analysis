"""Callbacks del backtest nivel C (Cartera top-N) — sección en /backtest.

Corre la simulación de cartera (ranking-puro + gated + benchmark EW) en
background (thread + polling, estado propio) y renderiza las dos curvas
superpuestas + drawdown + KPIs. On-demand (sin persistir). Mismo patrón robusto
que nivel B: `@safe_callback` en poll/start (para que el Interval siempre se
apague), chequeo de visibilidad, y la `spec` en el formato de trade_simulator.
"""
import threading

import dash_bootstrap_components as dbc
from dash import Input, Output, State, callback, dcc, html, no_update

from app.components import portfolio_views as pv
from app.utils import safe_callback

_port_state = {"running": False, "current": 0, "total": 0, "phase": "",
               "error": None, "result": None}
_port_lock = threading.Lock()


def _num(v):
    if v in (None, ""):
        return None
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def _build_spec(score, pct, exit_score, sl, tp, ts, maxbars, cooldown, rearm):
    entries = []
    if _num(score) is not None:
        entries.append({"type": "score", "th": _num(score)})
    if _num(pct) is not None:
        entries.append({"type": "pct", "th": _num(pct)})
    score_exits = []
    if _num(exit_score) is not None:
        score_exits.append({"type": "absolute", "x": _num(exit_score)})
    caps = []
    if _num(maxbars) is not None:
        caps.append({"type": "max_bars", "n": max(1, round(_num(maxbars)))})
    if _num(sl) is not None:
        caps.append({"type": "stop_loss", "pct": _num(sl)})
    if _num(ts) is not None:
        caps.append({"type": "trailing_stop", "pct": _num(ts)})
    if _num(tp) is not None:
        caps.append({"type": "take_profit", "pct": _num(tp)})
    cd = max(0, round(_num(cooldown))) if _num(cooldown) is not None else 0
    return {"entries": entries, "score_exits": score_exits, "caps": caps,
            "rearm": bool(rearm), "cooldown": cd}


@callback(
    Output("bt-port-strategy", "options"),
    Input("bt-port-strategy", "id"),
)
def load_port_strategies(_):
    from app.services.strategy_service import get_visible_strategies
    from app.services.visibility import current_viewer
    return [{"label": s.name, "value": s.id}
            for s in get_visible_strategies(*current_viewer())]


@callback(
    Output("bt-port-interval", "disabled"),
    Output("bt-port-progress", "style"),
    Output("bt-port-alert", "children"),
    Output("bt-port-alert", "is_open"),
    Output("bt-port-alert", "color"),
    Input("bt-port-run", "n_clicks"),
    State("bt-port-strategy", "value"),
    State("bt-port-topn", "value"),
    State("bt-port-rebal", "value"),
    State("bt-port-cost", "value"),
    State("bt-port-score", "value"),
    State("bt-port-pct", "value"),
    State("bt-port-exit-score", "value"),
    State("bt-port-sl", "value"),
    State("bt-port-tp", "value"),
    State("bt-port-ts", "value"),
    State("bt-port-maxbars", "value"),
    State("bt-port-cooldown", "value"),
    State("bt-port-rearm", "value"),
    prevent_initial_call=True,
)
@safe_callback(lambda exc: (True, no_update, f"Error: {exc}", True, "danger"))
def start_port_run(_, strategy_id, topn, rebal, cost, score, pct, exit_score,
                   sl, tp, ts, maxbars, cooldown, rearm):
    if not strategy_id:
        return no_update, no_update, "Seleccioná una estrategia.", True, "warning"
    from app.services.strategy_service import get_visible_strategies
    from app.services.visibility import current_viewer
    if int(strategy_id) not in {s.id for s in
                                get_visible_strategies(*current_viewer())}:
        return no_update, no_update, "Estrategia no visible.", True, "warning"

    spec = _build_spec(score, pct, exit_score, sl, tp, ts, maxbars, cooldown,
                       rearm)
    if not spec["entries"]:
        # sin entradas el sub-modo gated nunca toma posición (curva plana)
        return (no_update, no_update,
                "Definí al menos una condición de entrada (Score ≥ o Percentil ≥).",
                True, "warning")
    top_n = max(1, int(_num(topn) or 20))
    rebalance_every = max(1, int(_num(rebal) or 1))
    cost_bps = _num(cost) or 0.0

    if not _port_lock.acquire(blocking=False):
        return (no_update, no_update, "Ya hay una corrida de cartera en curso.",
                True, "warning")

    _port_state.update({"running": True, "current": 0, "total": 0, "phase": "",
                        "error": None, "result": None})

    def _run():
        from app.database import Session
        from app.services.portfolio_backtest_service import run_portfolio_backtest

        def _progress(cur, tot, phase):
            (_port_state["current"], _port_state["total"],
             _port_state["phase"]) = cur, tot, phase

        try:
            _port_state["result"] = run_portfolio_backtest(
                int(strategy_id), spec, top_n=top_n,
                rebalance_every=rebalance_every, cost_bps=cost_bps,
                progress_cb=_progress)
        except Exception as exc:
            _port_state["error"] = str(exc)
        finally:
            _port_state["running"] = False
            _port_lock.release()
            Session.remove()

    threading.Thread(target=_run, daemon=True).start()
    return (False, {"display": "block", "height": "16px", "fontSize": "0.72rem"},
            "Simulando la cartera sobre el universo…", True, "info")


@callback(
    Output("bt-port-progress", "value"),
    Output("bt-port-progress", "label"),
    Output("bt-port-progress", "style", allow_duplicate=True),
    Output("bt-port-interval", "disabled", allow_duplicate=True),
    Output("bt-port-alert", "children", allow_duplicate=True),
    Output("bt-port-alert", "is_open", allow_duplicate=True),
    Output("bt-port-alert", "color", allow_duplicate=True),
    Output("bt-port-results", "children"),
    Input("bt-port-interval", "n_intervals"),
    prevent_initial_call=True,
)
@safe_callback(lambda exc: (0, "", {"display": "none"}, True,
                            f"Error al mostrar resultados: {exc}", True,
                            "danger", no_update))
def poll_port(_):
    hidden = {"display": "none"}
    if _port_state["running"]:
        cur, tot = _port_state["current"], _port_state["total"] or 1
        pct = int(cur / tot * 100)
        label = (f"{_port_state['phase']} {cur}/{_port_state['total']}"
                 if _port_state["total"] else "Iniciando…")
        return pct, label, no_update, False, no_update, True, no_update, no_update
    if _port_state["error"]:
        return (0, "", hidden, True, f"Error: {_port_state['error']}", True,
                "danger", no_update)
    return (100, "Completo", hidden, True, "Cartera: simulación terminada.", True,
            "success", _render_port(_port_state["result"]))


def _render_port(res):
    if not res:
        return None
    dates = res["dates"]
    if not dates:
        return dbc.Alert("Sin datos para el período.", color="secondary",
                         className="small py-2")
    g, rk, bw = res["gated"], res["ranking"], res["benchmark_ew"]

    def idx(eq):
        return [v * 100.0 for v in eq]

    equity_fig = pv.equity_figure([
        {"name": "Con reglas (gated)", "values": idx(g["equity"])},
        {"name": "Ranking puro", "values": idx(rk["equity"])},
        {"name": "EW universo", "values": idx(bw["equity"]), "dash": True},
    ], x=dates)
    dd_fig = pv.drawdown_figure(g["equity"], x=dates)

    tiles = pv.kpi_tiles([
        {"label": "CAGR (gated)", "value": pv.fmt_pct(g["cagr"], signed=True),
         "good": (g["cagr"] or 0) >= 0},
        {"label": "Retorno total", "value": pv.fmt_mult(g["total_return"])},
        {"label": "Sharpe", "value": pv.fmt_ratio(g["sharpe"])},
        {"label": "Máx drawdown", "value": pv.fmt_pct(g["max_drawdown"]),
         "good": False},
    ])

    def row(name, d):
        return html.Tr([
            html.Td(name),
            html.Td(pv.fmt_pct(d["cagr"], signed=True), className="text-end"),
            html.Td(pv.fmt_ratio(d["sharpe"]), className="text-end"),
            html.Td(pv.fmt_pct(d["max_drawdown"]), className="text-end"),
            html.Td(pv.fmt_mult(d["total_return"]), className="text-end"),
        ])
    table = dbc.Table([
        html.Thead(html.Tr([
            html.Th("Sub-modo"), html.Th("CAGR", className="text-end"),
            html.Th("Sharpe", className="text-end"),
            html.Th("Máx DD", className="text-end"),
            html.Th("Ret. total", className="text-end")])),
        html.Tbody([row("Con reglas (gated)", g), row("Ranking puro", rk),
                    row("EW universo", bw)])],
        bordered=False, hover=True, size="sm", className="small")

    return html.Div([
        tiles,
        dcc.Graph(figure=equity_fig, config=pv.graph_config(), className="mt-2"),
        dcc.Graph(figure=dd_fig, config=pv.graph_config()),
        html.H6("Comparación", className="mt-2"),
        table,
    ])


@callback(
    Output("bt-port-promote-alert", "children"),
    Output("bt-port-promote-alert", "is_open"),
    Output("bt-port-promote-alert", "color"),
    Input("bt-port-promote", "n_clicks"),
    State("bt-port-strategy", "value"),
    State("bt-port-topn", "value"),
    State("bt-port-rebal", "value"),
    prevent_initial_call=True,
)
@safe_callback(lambda exc: (f"Error: {exc}", True, "danger"))
def promote_to_seguimiento(_, strategy_id, topn, rebal):
    """Crea una cartera teórica (seguimiento) derivada del top-N de la estrategia
    con la config actual — el 'promover a seguimiento' del rediseño."""
    if not strategy_id:
        return "Elegí una estrategia primero.", True, "warning"
    from app.database import get_session
    from app.services import portfolio_service as ps
    from app.services.strategy_service import get_visible_strategies
    from app.services.visibility import current_viewer

    user_id, _is_admin = current_viewer()
    visible = {st.id: st.name for st in get_visible_strategies(*current_viewer())}
    if int(strategy_id) not in visible:
        return "Estrategia no visible.", True, "warning"

    top_n = max(1, int(_num(topn) or 20))
    rebalance = max(1, int(_num(rebal) or 1))
    name = f"Seguimiento: {visible[int(strategy_id)]} · top-{top_n}"
    ps.create_portfolio(get_session(), name, "seg", owner_id=user_id,
                        composition_method="strategy",
                        strategy_id=int(strategy_id), top_n=top_n,
                        rebalance=rebalance)
    return (f"Cartera de seguimiento «{name}» creada — vela en /carteras.",
            True, "success")
