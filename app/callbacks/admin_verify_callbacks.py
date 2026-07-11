import itertools
import subprocess
import sys
import threading
from pathlib import Path

from dash import ALL, Input, Output, State, callback, ctx, html, no_update
from flask_login import current_user

_ROOT = Path(__file__).resolve().parent.parent.parent

_pytest_state = {"running": False, "output": "", "passed": None, "error": None}
_verify_state = {"running": False, "current": 0, "total": 0, "label": "",
                 "result": None, "error": None, "kind": None}

_TAB_LABELS = {"calc": "Discrepancias de cálculo", "sanity": "Datos de origen"}


# ── Suite de tests (pytest) ─────────────────────────────────────────────────

@callback(
    Output("verify-pytest-interval", "disabled", allow_duplicate=True),
    Output("verify-pytest-spinner",  "style",    allow_duplicate=True),
    Output("verify-pytest-btn",      "disabled", allow_duplicate=True),
    Output("verify-pytest-alert",    "is_open",  allow_duplicate=True),
    Output("verify-pytest-output",   "children", allow_duplicate=True),
    Input("verify-pytest-btn", "n_clicks"),
    prevent_initial_call=True,
)
def start_pytest(_):
    if not current_user.is_authenticated or not current_user.is_admin:
        return no_update, no_update, no_update, no_update, no_update
    if _pytest_state["running"]:
        return False, {"display": "block"}, True, no_update, no_update

    _pytest_state.update({"running": True, "output": "", "passed": None, "error": None})

    def _run():
        try:
            proc = subprocess.run(
                [sys.executable, "-m", "pytest", "tests/", "-q"],
                cwd=str(_ROOT), capture_output=True, text=True, timeout=300,
            )
            _pytest_state["output"] = (proc.stdout or "") + (proc.stderr or "")
            _pytest_state["passed"] = proc.returncode == 0
        except Exception as exc:
            _pytest_state["error"] = str(exc)
        finally:
            _pytest_state["running"] = False

    threading.Thread(target=_run, daemon=True).start()
    return False, {"display": "block"}, True, False, ""


@callback(
    Output("verify-pytest-interval", "disabled",  allow_duplicate=True),
    Output("verify-pytest-spinner",  "style",     allow_duplicate=True),
    Output("verify-pytest-btn",      "disabled",  allow_duplicate=True),
    Output("verify-pytest-alert",    "children",  allow_duplicate=True),
    Output("verify-pytest-alert",    "is_open",   allow_duplicate=True),
    Output("verify-pytest-alert",    "color",     allow_duplicate=True),
    Output("verify-pytest-output",   "children",  allow_duplicate=True),
    Input("verify-pytest-interval", "n_intervals"),
    prevent_initial_call=True,
)
def poll_pytest(_):
    if _pytest_state["running"]:
        return False, {"display": "block"}, True, no_update, False, no_update, no_update

    if _pytest_state["error"]:
        msg = f"Error corriendo pytest: {_pytest_state['error']}"
        return True, {"display": "none"}, False, msg, True, "danger", _pytest_state["output"]

    passed = _pytest_state["passed"]
    color  = "success" if passed else "danger"
    msg    = "Suite OK — todos los tests pasaron." if passed else "Hay tests que fallaron — ver detalle abajo."
    return True, {"display": "none"}, False, msg, True, color, _pytest_state["output"]


# ── Verificación de datos reales ────────────────────────────────────────────

@callback(
    Output("verify-codes", "options"),
    Output("verify-codes", "value"),
    Input("verify-domain", "value"),
)
def update_code_options(domain):
    if domain == "fundamentals":
        from app.services.fundamental_service import _ALL_FUND_CODES
        options = [{"label": c, "value": c} for c in sorted(_ALL_FUND_CODES)]
    else:
        from app.services.technical_service import _DELTA_TAIL_MODE
        options = [{"label": c, "value": c} for c in sorted(_DELTA_TAIL_MODE)]
    return options, []


@callback(
    Output("verify-sample-col",  "style"),
    Output("verify-tickers-col", "style"),
    Output("verify-domain",      "options"),
    Output("verify-codes",       "disabled"),
    Output("verify-domain-note", "className"),
    Input("verify-scope", "value"),
)
def toggle_scope_inputs(scope):
    show  = {"display": "block"}
    hide  = {"display": "none"}
    full_scope = scope in ("all", "marked")
    domain_opts = [
        {"label": "Indicadores técnicos", "value": "indicators", "disabled": full_scope},
        {"label": "Ratios fundamentales", "value": "fundamentals", "disabled": full_scope},
    ]
    note_class = "text-muted" if full_scope else "text-muted d-none"
    return (
        show if scope == "sample"  else hide,
        show if scope == "tickers" else hide,
        domain_opts, full_scope, note_class,
    )


@callback(
    Output("verify-run-interval",       "disabled", allow_duplicate=True),
    Output("verify-run-progress",       "style",    allow_duplicate=True),
    Output("verify-run-btn",            "disabled", allow_duplicate=True),
    Output("verify-run-alert",          "is_open",  allow_duplicate=True),
    Output("verify-tree-calc",          "children", allow_duplicate=True),
    Output("verify-tree-sanity",        "children", allow_duplicate=True),
    Output("verify-tab-calc",           "label",    allow_duplicate=True),
    Output("verify-tab-sanity",         "label",    allow_duplicate=True),
    Input("verify-run-btn", "n_clicks"),
    State("verify-scope",   "value"),
    State("verify-domain",  "value"),
    State("verify-codes",   "value"),
    State("verify-sample",  "value"),
    State("verify-tickers", "value"),
    prevent_initial_call=True,
)
def start_verify(_, scope, domain, codes, sample, tickers_raw):
    if not current_user.is_authenticated or not current_user.is_admin:
        return (no_update,) * 8
    if _verify_state["running"]:
        return (False, {"display": "block"}, True, no_update,
                no_update, no_update, no_update, no_update)

    tickers = None
    if tickers_raw and tickers_raw.strip():
        tickers = [t.strip() for t in tickers_raw.split(",") if t.strip()]

    kind = "flags" if scope in ("all", "marked") else "sample"
    _verify_state.update({"running": True, "current": 0, "total": 0, "label": "",
                          "result": None, "error": None, "kind": kind})

    def _run():
        def _progress(cur, tot, label=""):
            _verify_state["current"] = cur
            _verify_state["total"]   = tot
            _verify_state["label"]   = label
        try:
            if kind == "flags":
                from app.services.verification_service import (
                    get_flagged_asset_ids, update_flags_for_assets,
                )
                asset_ids = None if scope == "all" else list(get_flagged_asset_ids())
                result = update_flags_for_assets(asset_ids=asset_ids, progress_cb=_progress)
            else:
                from app.services.verification_service import (
                    run_fund_verification, run_verification,
                )
                run_fn = run_verification if domain != "fundamentals" else run_fund_verification
                result = run_fn(
                    codes=codes or None,
                    sample=int(sample) if sample else 30,
                    tickers=tickers,
                    progress_cb=_progress,
                )
            _verify_state["result"] = result
        except Exception as exc:
            _verify_state["error"] = str(exc)
        finally:
            _verify_state["running"] = False

    threading.Thread(target=_run, daemon=True).start()
    return (False, {"display": "block"}, True, False,
            [], [], _TAB_LABELS["calc"], _TAB_LABELS["sanity"])


def _split_by_category(result: dict) -> tuple[list, list]:
    """Separa cada combo (código, activo) en sus diffs "calc" (guardado !=
    recalculado — sospecha real de bug de caché/delta) vs. "sanity"
    (guardado == recalculado pero el valor no tiene sentido — no es un bug
    de esta herramienta, es un dato de entrada raro). Ver _diff_category
    en verification_service.py."""
    calc, sanity = [], []
    for r in result["results"]:
        calc_diffs   = [d for d in r["diffs"] if d[4] == "calc"]
        sanity_diffs = [d for d in r["diffs"] if d[4] == "sanity"]
        if calc_diffs:
            calc.append({**r, "diffs": calc_diffs})
        if sanity_diffs:
            sanity.append({**r, "diffs": sanity_diffs})
    return calc, sanity


_TREE_PRE_STYLE = {
    "backgroundColor": "#111827", "color": "#e5e7eb",
    "padding": "0.5rem 0.75rem", "borderRadius": "4px",
    "fontSize": "0.76rem", "whiteSpace": "pre-wrap", "margin": "0.25rem 0 0.5rem 0",
}


def _diff_lines(diffs: list) -> str:
    return "\n".join(
        f"{d}  {kind}  guardado={stored!r}  recalculado={fresh!r}"
        for d, kind, stored, fresh, _cat in diffs
    )


def _code_node(r: dict, tab: str, counter) -> html.Details:
    return html.Details(
        [
            html.Summary(f"{r['code']} — {len(r['diffs'])} diferencia(s)"),
            html.Pre(_diff_lines(r["diffs"]), style=_TREE_PRE_STYLE),
        ],
        id={"type": "verify-tree-node", "tab": tab, "idx": next(counter)},
        style={"marginLeft": "1.25rem"},
    )


def _domain_node(label: str, combos: list, tab: str, counter) -> html.Details:
    total = sum(len(r["diffs"]) for r in combos)
    children = [_code_node(r, tab, counter)
               for r in sorted(combos, key=lambda r: -len(r["diffs"]))]
    return html.Details(
        [html.Summary(f"{label} — {total} diferencia(s)"), html.Div(children)],
        id={"type": "verify-tree-node", "tab": tab, "idx": next(counter)},
        style={"marginLeft": "1rem"},
    )


def _asset_node(asset_id: int, ticker: str, combos: list, tab: str, counter) -> html.Details:
    """Un nodo por activo; si el resultado mezcla indicadores + fundamentales
    (alcance "Todos los activos"/"Solo los marcados") se intercala un nivel
    Técnico/Fundamentales — con un solo dominio (Muestra/Tickers) se salta
    ese nivel porque no aportaría nada."""
    total = sum(len(r["diffs"]) for r in combos)
    fund = [r for r in combos if r["code"].startswith("fundamental_")]
    tech = [r for r in combos if not r["code"].startswith("fundamental_")]
    if tech and fund:
        children = [_domain_node("Técnico", tech, tab, counter),
                    _domain_node("Fundamentales", fund, tab, counter)]
    else:
        children = [_code_node(r, tab, counter)
                   for r in sorted(combos, key=lambda r: -len(r["diffs"]))]
    return html.Details(
        [html.Summary(f"{ticker} (id={asset_id}) — {total} diferencia(s)"), html.Div(children)],
        id={"type": "verify-tree-node", "tab": tab, "idx": next(counter)},
    )


def _build_tree(combos: list, tab: str) -> list:
    """Árbol Activo > [Técnico/Fundamentales] > Código > diferencias, con
    html.Details anidados nativos del navegador (abren/cierran sin
    callback por nodo — solo "Expandir/Colapsar todo" necesita uno, ver
    toggle_tree_calc/toggle_tree_sanity). Con "Expandir todo" el texto
    completo queda seleccionable/copiable igual que antes."""
    if not combos:
        return [html.Div("Sin diferencias.", className="text-muted small")]
    by_asset: dict = {}
    for r in combos:
        by_asset.setdefault((r["asset_id"], r["ticker"]), []).append(r)
    counter = itertools.count()
    ordered = sorted(by_asset.items(),
                     key=lambda kv: -sum(len(r["diffs"]) for r in kv[1]))
    return [_asset_node(aid, ticker, rs, tab, counter) for (aid, ticker), rs in ordered]


def _tab_label(base: str, n: int) -> str:
    return f"{base} ({n})"


@callback(
    Output("verify-run-interval",       "disabled", allow_duplicate=True),
    Output("verify-run-progress",       "value",    allow_duplicate=True),
    Output("verify-run-progress",       "label",    allow_duplicate=True),
    Output("verify-run-progress",       "style",    allow_duplicate=True),
    Output("verify-run-btn",            "disabled", allow_duplicate=True),
    Output("verify-run-alert",          "children", allow_duplicate=True),
    Output("verify-run-alert",          "is_open",  allow_duplicate=True),
    Output("verify-run-alert",          "color",    allow_duplicate=True),
    Output("verify-tree-calc",          "children", allow_duplicate=True),
    Output("verify-tree-sanity",        "children", allow_duplicate=True),
    Output("verify-tab-calc",           "label",    allow_duplicate=True),
    Output("verify-tab-sanity",         "label",    allow_duplicate=True),
    Output("verify-flags-last-run",     "children", allow_duplicate=True),
    Input("verify-run-interval", "n_intervals"),
    prevent_initial_call=True,
)
def poll_verify(_):
    if _verify_state["running"]:
        tot = _verify_state["total"] or 1
        pct = int(_verify_state["current"] / tot * 100)
        label = f"{_verify_state['current']} / {_verify_state['total']}  {_verify_state['label']}"
        return (False, pct, label, {"display": "block"}, True,
                no_update, False, no_update, no_update, no_update,
                no_update, no_update, no_update)

    if _verify_state["error"]:
        msg = f"Error corriendo la verificación: {_verify_state['error']}"
        return (True, 0, "", {"display": "none"}, False,
                msg, True, "danger", [], [],
                _TAB_LABELS["calc"], _TAB_LABELS["sanity"], no_update)

    result = _verify_state["result"]
    if result is None:
        return (True, 0, "", {"display": "none"}, False,
                no_update, False, no_update, no_update, no_update,
                no_update, no_update, no_update)

    calc, sanity = _split_by_category(result)
    n_calc   = sum(len(r["diffs"]) for r in calc)
    n_sanity = sum(len(r["diffs"]) for r in sanity)

    prefix = ""
    last_run_text = no_update
    if _verify_state["kind"] == "flags":
        prefix = (f"Marcado actualizado — {result['checked_assets']} activos verificados "
                 f"en {result['seconds']}s, {result['flagged_assets']} quedaron marcados, "
                 f"{result['cleared_assets']} se limpiaron. ")
        from app.services.verification_service import get_last_verification_run
        last_run_text = _format_last_run(get_last_verification_run())

    if n_calc == 0 and n_sanity == 0:
        color = "success"
        msg = prefix + "Sin diferencias en lo verificado."
    elif n_calc == 0:
        color = "warning"
        msg = (prefix + f"Sin discrepancias de cálculo. {n_sanity} posibles errores de "
               f"datos de origen (revisar el dato de entrada, no es un bug de caché) — "
               f"ver pestaña 'Datos de origen'.")
    else:
        color = "danger"
        msg = (prefix + f"{n_calc} discrepancias de cálculo (posible bug de caché/delta) + "
               f"{n_sanity} posibles errores de datos de origen — ver detalle en cada pestaña.")
    if result.get("missing_tickers"):
        msg += f" (tickers no encontrados, salteados: {', '.join(result['missing_tickers'])})"

    return (True, 100, "Completo", {"display": "none"}, False,
            msg, True, color,
            _build_tree(calc, "calc"), _build_tree(sanity, "sanity"),
            _tab_label(_TAB_LABELS["calc"], n_calc), _tab_label(_TAB_LABELS["sanity"], n_sanity),
            last_run_text)


def _format_last_run(info: dict | None) -> str:
    if info is None:
        return "Todavía no corrió ninguna verificación completa."
    mode = "todos los activos" if info["mode"] == "all" else "solo los marcados"
    mins, secs = divmod(int(info["seconds"]), 60)
    dur = f"{mins}m{secs:02d}s" if mins else f"{secs}s"
    when = info["started_at"].strftime("%Y-%m-%d %H:%M UTC")
    return (f"Última corrida: {when} — modo: {mode} — "
           f"{info['checked_assets']} activos verificados, "
           f"{info['flagged_assets']} marcados, {info['cleared_assets']} limpiados — "
           f"tardó {dur}.")


@callback(
    Output("verify-flags-last-run", "children"),
    Input("verify-flags-last-run", "id"),
)
def load_last_run(_):
    from app.services.verification_service import get_last_verification_run
    return _format_last_run(get_last_verification_run())


# ── Expandir/colapsar todo el árbol — un callback por pestaña: el patrón de
# id de cada nodo fija "tab" y solo deja "idx" como comodín (ALL), así que
# el Output alcanza a todos los nodos ya renderizados en esa pestaña sin
# necesidad de un callback por nodo individual. ──────────────────────────────

@callback(
    Output({"type": "verify-tree-node", "tab": "calc", "idx": ALL}, "open"),
    Input("verify-tree-expand-calc",   "n_clicks"),
    Input("verify-tree-collapse-calc", "n_clicks"),
    State({"type": "verify-tree-node", "tab": "calc", "idx": ALL}, "id"),
    prevent_initial_call=True,
)
def toggle_tree_calc(_expand, _collapse, ids):
    return [ctx.triggered_id == "verify-tree-expand-calc"] * len(ids)


@callback(
    Output({"type": "verify-tree-node", "tab": "sanity", "idx": ALL}, "open"),
    Input("verify-tree-expand-sanity",   "n_clicks"),
    Input("verify-tree-collapse-sanity", "n_clicks"),
    State({"type": "verify-tree-node", "tab": "sanity", "idx": ALL}, "id"),
    prevent_initial_call=True,
)
def toggle_tree_sanity(_expand, _collapse, ids):
    return [ctx.triggered_id == "verify-tree-expand-sanity"] * len(ids)
