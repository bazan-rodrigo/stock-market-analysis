"""Callbacks del backtest nivel B (Reglas) — sección en /backtest.

Corre el fan-out del simulador sobre el universo de la estrategia (thread daemon
+ polling, mismo patrón que el nivel A) y renderiza KPIs, salidas por motivo,
distribución y ranking. Estado propio (_rules_state / _rules_lock) para no
interferir con el nivel A. La `spec` se arma con el formato exacto que consume
trade_simulator (no toca el contrato homologado).
"""
import threading

import dash_bootstrap_components as dbc
from dash import Input, Output, State, callback, dcc, html, no_update

from app.components import portfolio_views as pv
from app.utils import safe_callback

_rules_state = {"running": False, "current": 0, "total": 0, "phase": "",
                "error": None, "result": None}
_rules_lock = threading.Lock()

_LBL = {"fontSize": "0.8rem"}


def _num(v):
    if v in (None, ""):
        return None
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def _build_spec(score, pct, exit_score, sl, tp, ts, maxbars, cooldown, rearm):
    """Arma la spec en el formato de trade_simulator a partir de los controles."""
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
    Output("bt-rules-strategy", "options"),
    Input("bt-rules-strategy", "id"),
)
def load_rules_strategies(_):
    from app.services.strategy_service import get_visible_strategies
    from app.services.visibility import current_viewer
    return [{"label": s.name, "value": s.id}
            for s in get_visible_strategies(*current_viewer())]


@callback(
    Output("bt-rules-interval", "disabled"),
    Output("bt-rules-progress", "style"),
    Output("bt-rules-alert", "children"),
    Output("bt-rules-alert", "is_open"),
    Output("bt-rules-alert", "color"),
    Input("bt-rules-run", "n_clicks"),
    State("bt-rules-strategy", "value"),
    State("bt-rules-score", "value"),
    State("bt-rules-pct", "value"),
    State("bt-rules-exit-score", "value"),
    State("bt-rules-sl", "value"),
    State("bt-rules-tp", "value"),
    State("bt-rules-ts", "value"),
    State("bt-rules-maxbars", "value"),
    State("bt-rules-cooldown", "value"),
    State("bt-rules-rearm", "value"),
    prevent_initial_call=True,
)
@safe_callback(lambda exc: (True, no_update, f"Error: {exc}", True, "danger"))
def start_rules_run(_, strategy_id, score, pct, exit_score, sl, tp, ts, maxbars,
                    cooldown, rearm):
    if not strategy_id:
        return no_update, no_update, "Seleccioná una estrategia.", True, "warning"
    # Visibilidad: los valores de State los controla el cliente, así que no
    # alcanza con filtrar las opciones del dropdown (igual que nivel A).
    from app.services.strategy_service import get_visible_strategies
    from app.services.visibility import current_viewer
    visible = {s.id for s in get_visible_strategies(*current_viewer())}
    if int(strategy_id) not in visible:
        return no_update, no_update, "Estrategia no visible.", True, "warning"
    spec = _build_spec(score, pct, exit_score, sl, tp, ts, maxbars, cooldown,
                       rearm)
    if not spec["entries"]:
        return (no_update, no_update,
                "Definí al menos una condición de entrada (Score ≥ o Percentil ≥).",
                True, "warning")
    if not _rules_lock.acquire(blocking=False):
        return (no_update, no_update, "Ya hay una corrida de reglas en curso.",
                True, "warning")

    _rules_state.update({"running": True, "current": 0, "total": 0, "phase": "",
                         "error": None, "result": None})

    def _run():
        from app.database import Session
        from app.services.rules_backtest_service import run_rules_backtest

        def _progress(cur, tot, phase):
            (_rules_state["current"], _rules_state["total"],
             _rules_state["phase"]) = cur, tot, phase

        try:
            _rules_state["result"] = run_rules_backtest(
                int(strategy_id), spec, progress_cb=_progress)
        except Exception as exc:
            _rules_state["error"] = str(exc)
        finally:
            _rules_state["running"] = False
            _rules_lock.release()
            Session.remove()

    threading.Thread(target=_run, daemon=True).start()
    return (False, {"display": "block", "height": "16px", "fontSize": "0.72rem"},
            "Corriendo reglas sobre el universo…", True, "info")


@callback(
    Output("bt-rules-progress", "value"),
    Output("bt-rules-progress", "label"),
    Output("bt-rules-progress", "style", allow_duplicate=True),
    Output("bt-rules-interval", "disabled", allow_duplicate=True),
    Output("bt-rules-alert", "children", allow_duplicate=True),
    Output("bt-rules-alert", "is_open", allow_duplicate=True),
    Output("bt-rules-alert", "color", allow_duplicate=True),
    Output("bt-rules-results", "children"),
    Input("bt-rules-interval", "n_intervals"),
    prevent_initial_call=True,
)
@safe_callback(lambda exc: (0, "", {"display": "none"}, True,
                            f"Error al mostrar resultados: {exc}", True,
                            "danger", no_update))
def poll_rules(_):
    hidden = {"display": "none"}
    if _rules_state["running"]:
        cur, tot = _rules_state["current"], _rules_state["total"] or 1
        pct = int(cur / tot * 100)
        label = (f"{_rules_state['phase']} {cur}/{_rules_state['total']}"
                 if _rules_state["total"] else "Iniciando…")
        return pct, label, no_update, False, no_update, True, no_update, no_update
    if _rules_state["error"]:
        return (0, "", hidden, True, f"Error: {_rules_state['error']}", True,
                "danger", no_update)
    return (100, "Completo", hidden, True, "Reglas: corrida terminada.", True,
            "success", _render_results(_rules_state["result"]))


def _render_results(agg):
    if not agg:
        return None
    from app.database import get_session
    from app.models import Asset

    top = agg["ranking"][:20]           # solo se muestran 20 → tickers solo de esos
    ids = [r["asset_id"] for r in top]
    tickers = ({i: tk for i, tk in get_session().query(Asset.id, Asset.ticker)
                .filter(Asset.id.in_(ids)).all()} if ids else {})

    tiles = pv.kpi_tiles([
        {"label": "Activos con trades",
         "value": f"{agg['n_with_trades']} / {agg['n_assets']}"},
        {"label": "Retorno mediano (por activo)",
         "value": pv.fmt_pct(agg["median_total_ret"], signed=True),
         "good": (agg["median_total_ret"] or 0) >= 0},
        {"label": "Win rate medio", "value": pv.fmt_pct(agg["mean_win_rate"])},
        {"label": "Trades totales", "value": str(agg["total_trades"])},
    ])

    figs = []
    if agg["exit_reasons"]:
        figs.append(dbc.Col(dcc.Graph(
            figure=pv.exit_reason_figure(agg["exit_reasons"],
                                         title="Salidas por motivo"),
            config=pv.graph_config()), md=6))
    dist = [r["total_ret"] for r in agg["ranking"] if r["total_ret"] is not None]
    if dist:
        figs.append(dbc.Col(dcc.Graph(
            figure=pv.distribution_figure(dist,
                                          title="Retorno total por activo"),
            config=pv.graph_config()), md=6))

    rows = [html.Tr([
        html.Td(tickers.get(r["asset_id"], f"#{r['asset_id']}")),
        html.Td(str(r["n_trades"]), className="text-end"),
        html.Td(pv.fmt_pct(r["win_rate"]), className="text-end"),
        html.Td(pv.fmt_pct(r["total_ret"], signed=True), className="text-end"),
        html.Td(pv.fmt_pct(r["avg_ret"], signed=True), className="text-end"),
        html.Td(f"{r['avg_bars']:.0f}" if r["avg_bars"] is not None else "—",
                className="text-end"),
    ]) for r in top]
    table = dbc.Table([
        html.Thead(html.Tr([
            html.Th("Activo"), html.Th("Trades", className="text-end"),
            html.Th("Win%", className="text-end"),
            html.Th("Ret. total", className="text-end"),
            html.Th("Ret. medio", className="text-end"),
            html.Th("Ruedas", className="text-end")])),
        html.Tbody(rows)], bordered=False, hover=True, size="sm",
        className="small")

    return html.Div([
        tiles,
        dbc.Row(figs, className="g-2 mt-2") if figs else html.Div(),
        html.H6("Mejores activos (por retorno total)", className="mt-3"),
        table,
    ])
