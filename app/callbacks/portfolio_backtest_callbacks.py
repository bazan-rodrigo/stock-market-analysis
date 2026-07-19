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

_wf_state = {"running": False, "current": 0, "total": 0, "phase": "",
             "error": None, "result": None}
_wf_lock = threading.Lock()


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
    user_id, is_admin = current_viewer()
    visible = {st.id: st.name
               for st in get_visible_strategies(user_id, is_admin)}
    if int(strategy_id) not in visible:
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
                        "error": None, "result": None, "owner_id": user_id,
                        "strategy_id": int(strategy_id),
                        "strategy_name": visible[int(strategy_id)],
                        "config": {"top_n": top_n, "rebalance": rebalance_every,
                                   "cost_bps": cost_bps, "spec": spec}})

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

    heat = (dcc.Graph(figure=pv.monthly_heatmap_figure(
        g["monthly_returns"], title="Retornos mensuales (gated)"),
        config=pv.graph_config()) if g.get("monthly_returns") else html.Div())

    return html.Div([
        tiles,
        dcc.Graph(figure=equity_fig, config=pv.graph_config(), className="mt-2"),
        dcc.Graph(figure=dd_fig, config=pv.graph_config()),
        heat,
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
    prevent_initial_call=True,
)
@safe_callback(lambda exc: (f"Error: {exc}", True, "danger"))
def promote_to_seguimiento(_, strategy_id, topn):
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
    name = f"Seguimiento: {visible[int(strategy_id)]} · top-{top_n}"
    ps.create_portfolio(get_session(), name, "seg", owner_id=user_id,
                        composition_method="strategy",
                        strategy_id=int(strategy_id), top_n=top_n)
    return (f"Cartera de seguimiento «{name}» creada — vela en /carteras.",
            True, "success")


# ── Nivel D: guardar corrida + comparar ───────────────────────────────────────

@callback(
    Output("bt-port-promote-alert", "children", allow_duplicate=True),
    Output("bt-port-promote-alert", "is_open", allow_duplicate=True),
    Output("bt-port-promote-alert", "color", allow_duplicate=True),
    Output("bt-cmp-reload", "data"),
    Input("bt-port-save", "n_clicks"),
    State("bt-cmp-reload", "data"),
    prevent_initial_call=True,
)
@safe_callback(lambda exc: (f"Error: {exc}", True, "danger", no_update))
def save_port_run(_, reload):
    if not _port_state.get("result"):
        return ("Corré una simulación antes de guardar.", True, "warning",
                no_update)
    from app.database import get_session
    from app.services import portfolio_backtest_service as pbs
    from app.services.visibility import current_viewer

    user_id, _is_admin = current_viewer()
    # El estado de corrida es global al proceso: sólo puede guardar quien la
    # produjo (evita persistir la corrida de otro usuario/sesión bajo tu owner).
    if _port_state.get("owner_id") != user_id:
        return ("La última simulación no la corriste vos en esta sesión — corré "
                "una antes de guardar.", True, "warning", no_update)
    cfg = _port_state.get("config", {})
    name = (f"{_port_state.get('strategy_name', '?')} · top-{cfg.get('top_n')} "
            f"· rebal {cfg.get('rebalance')} · {cfg.get('cost_bps')}bps")
    pbs.save_portfolio_run(get_session(), owner_id=user_id,
                           strategy_id=_port_state.get("strategy_id"),
                           name=name, config=cfg, result=_port_state["result"])
    _port_state["result"] = None      # ya guardada: no re-persistir la misma
    return (f"Corrida guardada «{name}» — compará en el tab Comparar.", True,
            "success", (reload or 0) + 1)


@callback(
    Output("bt-cmp-runs", "options"),
    Input("bt-cmp-reload", "data"),
)
@safe_callback(lambda exc: [])
def load_cmp_options(_reload):
    from app.database import get_session
    from app.services import portfolio_backtest_service as pbs
    from app.services.visibility import current_viewer
    runs = pbs.list_portfolio_runs(get_session(), *current_viewer())
    return [{"label": f"#{r.id} · {r.name} · {r.created_at:%Y-%m-%d %H:%M}",
             "value": r.id} for r in runs]


@callback(
    Output("bt-cmp-results", "children"),
    Input("bt-cmp-runs", "value"),
)
@safe_callback(lambda exc: dbc.Alert(f"Error: {exc}", color="danger",
                                     className="small py-2"))
def render_compare(run_ids):
    if not run_ids:
        return None
    from app.database import get_session
    from app.services import portfolio_backtest_service as pbs
    from app.services.visibility import current_viewer

    user_id, is_admin = current_viewer()
    s = get_session()
    series, rows = [], []
    for rid in run_ids:
        got = pbs.get_portfolio_run(s, rid)
        if not got:
            continue
        if not is_admin and got["run"].owner_id != user_id:
            continue                      # corrida no visible para el usuario
        gated = got["series"].get("gated")
        if gated and gated["dates"]:
            series.append({"name": got["run"].name,
                           "values": [v * 100 for v in gated["equity"]],
                           "x": gated["dates"]})
        sm = got["summary"].get("gated", {})
        rows.append(html.Tr([
            html.Td(got["run"].name),
            html.Td(pv.fmt_pct(sm.get("cagr"), signed=True), className="text-end"),
            html.Td(pv.fmt_ratio(sm.get("sharpe")), className="text-end"),
            html.Td(pv.fmt_pct(sm.get("max_drawdown")), className="text-end"),
            html.Td(pv.fmt_mult(sm.get("total_return")), className="text-end"),
        ]))
    chart = (dcc.Graph(figure=pv.equity_figure(series), config=pv.graph_config())
             if series else html.Small("Sin curvas para mostrar.",
                                       className="text-muted"))
    table = dbc.Table([
        html.Thead(html.Tr([
            html.Th("Corrida"), html.Th("CAGR", className="text-end"),
            html.Th("Sharpe", className="text-end"),
            html.Th("Máx DD", className="text-end"),
            html.Th("Ret. total", className="text-end")])),
        html.Tbody(rows)], bordered=False, hover=True, size="sm", className="small")
    return html.Div([chart, html.H6("KPIs (gated)", className="mt-2"), table])


# ── Walk-forward (optimización robusta out-of-sample) ─────────────────────────

@callback(
    Output("bt-wf-strategy", "options"),
    Input("bt-wf-strategy", "id"),
)
@safe_callback(lambda exc: [])
def load_wf_strategies(_):
    from app.services.strategy_service import get_visible_strategies
    from app.services.visibility import current_viewer
    return [{"label": s.name, "value": s.id}
            for s in get_visible_strategies(*current_viewer())]


@callback(
    Output("bt-wf-interval", "disabled"),
    Output("bt-wf-progress", "style"),
    Output("bt-wf-alert", "children"),
    Output("bt-wf-alert", "is_open"),
    Output("bt-wf-alert", "color"),
    Input("bt-wf-run", "n_clicks"),
    State("bt-wf-strategy", "value"),
    State("bt-wf-entry", "value"),
    State("bt-wf-nwin", "value"),
    State("bt-wf-cost", "value"),
    prevent_initial_call=True,
)
@safe_callback(lambda exc: (True, no_update, f"Error: {exc}", True, "danger"))
def start_wf_run(_, strategy_id, entry, nwin, cost):
    if not strategy_id:
        return no_update, no_update, "Seleccioná una estrategia.", True, "warning"
    from app.services.strategy_service import get_visible_strategies
    from app.services.visibility import current_viewer
    visible = {st.id for st in get_visible_strategies(*current_viewer())}
    if int(strategy_id) not in visible:
        return no_update, no_update, "Estrategia no visible.", True, "warning"
    entry_th = _num(entry)
    if entry_th is None:
        return (no_update, no_update, "Definí el score de entrada (score ≥).",
                True, "warning")
    base_spec = {"entries": [{"type": "score", "th": entry_th}],
                 "score_exits": [], "caps": [], "rearm": False, "cooldown": 0}
    n_windows = max(2, min(8, int(_num(nwin) or 4)))
    cost_bps = _num(cost) or 0.0

    if not _wf_lock.acquire(blocking=False):
        return (no_update, no_update, "Ya hay un walk-forward en curso.", True,
                "warning")
    _wf_state.update({"running": True, "current": 0, "total": 0, "phase": "",
                      "error": None, "result": None})

    def _run():
        from app.database import Session
        from app.services import portfolio_backtest_service as pbs

        def _progress(cur, tot, phase):
            (_wf_state["current"], _wf_state["total"],
             _wf_state["phase"]) = cur, tot, phase

        try:
            _wf_state["result"] = pbs.walk_forward(
                Session(), int(strategy_id), base_spec, n_windows=n_windows,
                cost_bps=cost_bps, progress_cb=_progress)
        except Exception as exc:
            _wf_state["error"] = str(exc)
        finally:
            _wf_state["running"] = False
            _wf_lock.release()
            Session.remove()

    try:
        threading.Thread(target=_run, daemon=True).start()
    except Exception as exc:      # si no arranca el thread, no dejar el lock tomado
        _wf_state["running"] = False
        _wf_lock.release()
        return (True, {"display": "none"}, f"No se pudo iniciar: {exc}", True,
                "danger")
    return (False, {"display": "block", "height": "16px", "fontSize": "0.72rem"},
            "Corriendo walk-forward (optimiza ventana por ventana)…", True,
            "info")


@callback(
    Output("bt-wf-progress", "value"),
    Output("bt-wf-progress", "label"),
    Output("bt-wf-progress", "style", allow_duplicate=True),
    Output("bt-wf-interval", "disabled", allow_duplicate=True),
    Output("bt-wf-alert", "children", allow_duplicate=True),
    Output("bt-wf-alert", "is_open", allow_duplicate=True),
    Output("bt-wf-alert", "color", allow_duplicate=True),
    Output("bt-wf-results", "children"),
    Input("bt-wf-interval", "n_intervals"),
    prevent_initial_call=True,
)
@safe_callback(lambda exc: (0, "", {"display": "none"}, True,
                            f"Error al mostrar resultados: {exc}", True,
                            "danger", no_update))
def poll_wf(_):
    hidden = {"display": "none"}
    if _wf_state["running"]:
        cur, tot = _wf_state["current"], _wf_state["total"] or 1
        pct = int(cur / tot * 100)
        label = (f"{_wf_state['phase']} {cur}/{_wf_state['total']}"
                 if _wf_state["total"] else "Iniciando…")
        return pct, label, no_update, False, no_update, True, no_update, no_update
    if _wf_state["error"]:
        return (0, "", hidden, True, f"Error: {_wf_state['error']}", True,
                "danger", no_update)
    return (100, "Completo", hidden, True, "Walk-forward terminado.", True,
            "success", _render_wf(_wf_state["result"]))


def _render_wf(res):
    if not res:
        return None
    if not res.get("oos_dates"):
        return dbc.Alert("Sin datos out-of-sample para el período (historia "
                         "insuficiente para las ventanas).", color="secondary",
                         className="small py-2")
    oos_fig = pv.equity_figure(
        [{"name": "Out-of-sample (concatenado)",
          "values": [v * 100 for v in res["oos_equity"]],
          "x": res["oos_dates"]}])
    tiles = pv.kpi_tiles([
        {"label": "CAGR OOS", "value": pv.fmt_pct(res.get("cagr"), signed=True),
         "good": (res.get("cagr") or 0) >= 0},
        {"label": "Retorno total OOS",
         "value": pv.fmt_mult(res.get("total_return"))},
        {"label": "Sharpe OOS", "value": pv.fmt_ratio(res.get("sharpe"))},
        {"label": "Máx drawdown OOS", "value": pv.fmt_pct(res.get("max_drawdown")),
         "good": False},
    ])
    rows = []
    for i, w in enumerate(res["windows"], 1):
        rows.append(html.Tr([
            html.Td(f"#{i}"),
            html.Td(f"{w['test'][0]:%Y-%m} … {w['test'][1]:%Y-%m}",
                    className="small"),
            html.Td(f"top-{w['top_n']} · trail {w['trailing']:g}%",
                    className="small"),
            html.Td(pv.fmt_pct(w["train_cagr"], signed=True),
                    className="text-end"),
            html.Td(pv.fmt_pct(w["test_cagr"], signed=True), className="text-end"),
        ]))
    table = dbc.Table([
        html.Thead(html.Tr([
            html.Th("Ventana"), html.Th("Período test"),
            html.Th("Mejor config (train)"),
            html.Th("CAGR train", className="text-end"),
            html.Th("CAGR test", className="text-end")])),
        html.Tbody(rows)], bordered=False, hover=True, size="sm", className="small")
    return html.Div([
        tiles,
        dcc.Graph(figure=oos_fig, config=pv.graph_config(), className="mt-2"),
        html.H6("Ventanas: config elegida en train vs resultado en test",
                className="mt-2"),
        table,
        html.Small("La config se elige por mejor Sharpe en el train; la tabla "
                   "muestra CAGR anualizada para comparar tramos de largo "
                   "distinto. Si la CAGR de test es consistentemente menor que "
                   "la de train, parte de la ventaja es sobreajuste.",
                   className="text-muted"),
    ])
