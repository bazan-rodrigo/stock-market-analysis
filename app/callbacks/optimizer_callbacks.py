"""
Optimizador de parámetros del simulador (pantalla Análisis de Activo).

Corre server-side con el motor Python HOMOLOGADO (trade_simulator, la misma
semántica exacta que el JS del gráfico) sobre el activo/estrategia
seleccionados: grid search de los valores de las condiciones ACTIVAS del
panel (trade_optimizer), ranking por retorno total compuesto en train y
validación out-of-sample. Cada fila del top se puede "Aplicar" al panel.
"""
import dash_bootstrap_components as dbc
from dash import ALL, Input, Output, State, callback, ctx, html, no_update

from app.callbacks.chart_callbacks import _sim_control_deps
from app.utils import safe_callback

_TOP_N = 10


def _on(v):
    return bool(v and len(v))


def _num(v):
    if v is None or v == "":
        return None
    try:
        x = float(v)
    except (TypeError, ValueError):
        return None
    return x


def _spec_from_controls(vals) -> dict:
    """Espejo PYTHON de window._lwc.buildSpec (chart_callbacks): mismo orden
    posicional (_SIM_CONTROL_IDS) y misma semántica de armado. Si cambia
    la spec, cambian los tres lugares en el mismo commit."""
    (ent_sc_on, ent_sc, ent_pct_on, ent_pct,
     xs_abs_on, xs_abs, xs_absup_on, xs_absup,
     xs_dent_on, xs_dent, xs_dmax_on, xs_dmax,
     xs_mak_on, xs_mak, xs_pct_on, xs_pct,
     cap_bars_on, cap_bars, cap_sl_on, cap_sl,
     cap_ts_on, cap_ts, cap_tp_on, cap_tp,
     rearm_on, cool_on, cool) = vals

    entries = []
    if _on(ent_sc_on) and _num(ent_sc) is not None:
        entries.append({"type": "score", "th": _num(ent_sc)})
    if _on(ent_pct_on) and _num(ent_pct) is not None:
        entries.append({"type": "pct", "th": _num(ent_pct)})
    score_exits = []
    if _on(xs_abs_on) and _num(xs_abs) is not None:
        score_exits.append({"type": "absolute", "x": _num(xs_abs)})
    if _on(xs_absup_on) and _num(xs_absup) is not None:
        score_exits.append({"type": "absolute_above", "x": _num(xs_absup)})
    if _on(xs_dent_on) and _num(xs_dent) is not None:
        score_exits.append({"type": "delta_entry", "x": _num(xs_dent)})
    if _on(xs_dmax_on) and _num(xs_dmax) is not None:
        score_exits.append({"type": "trailing_score", "x": _num(xs_dmax)})
    if _on(xs_mak_on) and _num(xs_mak) is not None:
        score_exits.append({"type": "score_ma",
                            "k": max(2, round(_num(xs_mak)))})
    if _on(xs_pct_on) and _num(xs_pct) is not None:
        score_exits.append({"type": "percentile", "x": _num(xs_pct)})
    caps = []
    if _on(cap_bars_on) and _num(cap_bars) is not None:
        caps.append({"type": "max_bars", "n": max(1, round(_num(cap_bars)))})
    if _on(cap_sl_on) and _num(cap_sl) is not None:
        caps.append({"type": "stop_loss", "pct": _num(cap_sl)})
    if _on(cap_ts_on) and _num(cap_ts) is not None:
        caps.append({"type": "trailing_stop", "pct": _num(cap_ts)})
    if _on(cap_tp_on) and _num(cap_tp) is not None:
        caps.append({"type": "take_profit", "pct": _num(cap_tp)})
    cooldown = 0
    if _on(cool_on) and _num(cool) is not None:
        cooldown = max(0, round(_num(cool)))
    return {"entries": entries, "score_exits": score_exits, "caps": caps,
            "rearm": _on(rearm_on), "cooldown": cooldown}


def _load_series(asset_id: int, strategy_id: int):
    """Arrays diarios alineados a las barras PROPIAS del activo (gate
    natural: solo fechas con precio propio, igual que el backtest)."""
    from app.database import get_session
    from app.models import Price, StrategyResult

    db = get_session()
    prows = (db.query(Price.date, Price.close)
             .filter(Price.asset_id == asset_id, Price.close.isnot(None))
             .order_by(Price.date).all())
    srows = (db.query(StrategyResult.date, StrategyResult.score,
                      StrategyResult.pct)
             .filter(StrategyResult.strategy_id == strategy_id,
                     StrategyResult.asset_id == asset_id).all())
    sc_by_date = {d: (float(s) if s is not None else None,
                      float(p) if p is not None else None)
                  for d, s, p in srows}
    closes, scores, pcts = [], [], []
    for d, c in prows:
        closes.append(float(c))
        s, p = sc_by_date.get(d, (None, None))
        scores.append(s)
        pcts.append(p)
    return closes, scores, pcts


def _fmt_pct(v, colored=True):
    if v is None:
        return html.Span("—", style={"color": "#6b7280"})
    txt = f"{'+' if v >= 0 else ''}{v * 100:.1f}%"
    color = ("#4ade80" if v >= 0 else "#ef5350") if colored else "#dee2e6"
    return html.Span(txt, style={"color": color})


_TH = {"fontSize": "0.72rem", "color": "#9ca3af", "padding": "3px 8px",
       "borderBottom": "1px solid #374151", "textAlign": "left"}
_TD = {"fontSize": "0.78rem", "padding": "3px 8px",
       "borderBottom": "1px solid #2c2c2c"}


def _results_table(out) -> html.Div:
    header = html.Tr([
        html.Th("Configuración", style=_TH),
        html.Th("Train: trades", style=_TH), html.Th("% gan.", style=_TH),
        html.Th("Total", style=_TH),
        html.Th("Test: trades", style=_TH), html.Th("% gan.", style=_TH),
        html.Th("Total", style=_TH),
        html.Th("", style=_TH),
    ])
    rows = []
    for i, r in enumerate(out["results"]):
        tr, te = r["train"], r["test"]
        rows.append(html.Tr([
            html.Td(r["label"], style={**_TD, "fontFamily": "monospace"}),
            html.Td(tr["n"], style=_TD),
            html.Td(f"{tr['win'] * 100:.0f}%" if tr["win"] is not None else "—",
                    style=_TD),
            html.Td(_fmt_pct(tr["total"]), style=_TD),
            html.Td(te["n"], style=_TD),
            html.Td(f"{te['win'] * 100:.0f}%" if te["win"] is not None else "—",
                    style=_TD),
            html.Td(_fmt_pct(te["total"]), style=_TD),
            html.Td(dbc.Button("Aplicar",
                               id={"type": "opt-apply", "index": i},
                               size="sm", color="primary",
                               style={"fontSize": "0.7rem",
                                      "padding": "0 8px"}),
                    style=_TD),
        ]))
    meta = (f"{out['n_combos']} combinaciones probadas · "
            f"{out['n_valid']} con ≥{out['min_trades']} trades en train · "
            f"train = primer 70% de las ruedas, test = el 30% restante "
            f"(nunca visto por el ranking)")
    return html.Div([
        html.Div(meta, className="text-muted mb-2",
                 style={"fontSize": "0.72rem"}),
        html.Table([html.Thead(header), html.Tbody(rows)],
                   style={"width": "100%", "borderCollapse": "collapse"}),
        dbc.Alert(
            "Optimizado sobre ESTE activo: el ranking ajusta también al "
            "ruido del pasado. Mirá la columna Test (fuera de muestra) y "
            "validá la configuración en otros activos antes de confiar.",
            color="warning", className="mt-2 mb-0 small py-1"),
    ])


# ── Abrir/cerrar modal ────────────────────────────────────────────────────────

@callback(
    Output("chart-opt-modal", "is_open"),
    Input("chart-strategy-opt-btn", "n_clicks"),
    Input("chart-opt-close", "n_clicks"),
    State("chart-opt-modal", "is_open"),
    prevent_initial_call=True,
)
def toggle_opt_modal(_open, _close, is_open):
    return not is_open


# ── Correr la optimización ────────────────────────────────────────────────────

@callback(
    Output("chart-opt-results", "children"),
    Output("chart-opt-store", "data"),
    Input("chart-opt-run", "n_clicks"),
    State("analysis-asset-select", "value"),
    State("chart-strategy-sel", "value"),
    *_sim_control_deps(State),
    prevent_initial_call=True,
)
@safe_callback(lambda exc: (dbc.Alert(f"Error: {exc}", color="danger",
                                      className="small py-1"), no_update))
def run_optimizer(_, asset_id, strategy_id, *vals):
    from app.services.trade_optimizer import optimize

    if not asset_id or not strategy_id:
        return dbc.Alert("Elegí un activo y una estrategia primero.",
                         color="warning", className="small py-1"), no_update
    spec = _spec_from_controls(vals)
    closes, scores, pcts = _load_series(int(asset_id), int(strategy_id))
    out = optimize(closes, scores, pcts, spec, top_n=_TOP_N)
    if not out["results"]:
        return dbc.Alert(
            f"Ninguna de las {out['n_combos']} combinaciones alcanzó "
            f"{out['min_trades']} trades cerrados en train. Probá con "
            "salidas más cortas o menos condiciones.",
            color="warning", className="small py-1"), no_update
    store = [r["spec"] for r in out["results"]]
    return _results_table(out), store


# ── Aplicar una fila al panel ─────────────────────────────────────────────────

# valor de cada control ← (sección, tipo, clave) de la spec
_APPLY_MAP = [
    ("chart-strategy-entry-sc",  "entries",     "score",          "th"),
    ("chart-strategy-entry-pct", "entries",     "pct",            "th"),
    ("chart-strategy-xs-abs",    "score_exits", "absolute",       "x"),
    ("chart-strategy-xs-absup",  "score_exits", "absolute_above", "x"),
    ("chart-strategy-xs-dent",   "score_exits", "delta_entry",    "x"),
    ("chart-strategy-xs-dmax",   "score_exits", "trailing_score", "x"),
    ("chart-strategy-xs-mak",    "score_exits", "score_ma",       "k"),
    ("chart-strategy-xs-pct",    "score_exits", "percentile",     "x"),
    ("chart-strategy-cap-bars",  "caps",        "max_bars",       "n"),
    ("chart-strategy-cap-sl",    "caps",        "stop_loss",      "pct"),
    ("chart-strategy-cap-ts",    "caps",        "trailing_stop",  "pct"),
    ("chart-strategy-cap-tp",    "caps",        "take_profit",    "pct"),
]


@callback(
    *[Output(cid, "value", allow_duplicate=True) for cid, *_ in _APPLY_MAP],
    Output("chart-strategy-cooldown", "value", allow_duplicate=True),
    Output("chart-opt-modal", "is_open", allow_duplicate=True),
    Input({"type": "opt-apply", "index": ALL}, "n_clicks"),
    State("chart-opt-store", "data"),
    prevent_initial_call=True,
)
def apply_opt_row(n_clicks_list, store):
    """Setea los valores de la fila elegida en los controles del panel (el
    cambio de values dispara el re-render del gráfico con la config nueva).
    Solo toca las condiciones activas; el resto queda como está."""
    if not any(n for n in n_clicks_list if n) or not store:
        return (no_update,) * (len(_APPLY_MAP) + 2)
    spec = store[ctx.triggered_id["index"]]
    values = []
    for _cid, section, typ, key in _APPLY_MAP:
        item = next((it for it in (spec.get(section) or [])
                     if it["type"] == typ), None)
        values.append(item[key] if item else no_update)
    cooldown = spec.get("cooldown") or no_update
    return (*values, cooldown, False)
