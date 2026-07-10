import subprocess
import sys
import threading
from pathlib import Path

from dash import Input, Output, State, callback, no_update
from flask_login import current_user

_ROOT = Path(__file__).resolve().parent.parent.parent

_pytest_state = {"running": False, "output": "", "passed": None, "error": None}
_verify_state = {"running": False, "current": 0, "total": 0, "label": "",
                 "result": None, "error": None}


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
    Output("verify-run-interval",       "disabled", allow_duplicate=True),
    Output("verify-run-progress",       "style",    allow_duplicate=True),
    Output("verify-run-btn",            "disabled", allow_duplicate=True),
    Output("verify-run-alert",          "is_open",  allow_duplicate=True),
    Output("verify-run-summary-calc",   "children", allow_duplicate=True),
    Output("verify-run-detail-calc",    "children", allow_duplicate=True),
    Output("verify-run-summary-sanity", "children", allow_duplicate=True),
    Output("verify-run-detail-sanity",  "children", allow_duplicate=True),
    Input("verify-run-btn", "n_clicks"),
    State("verify-domain",  "value"),
    State("verify-codes",   "value"),
    State("verify-sample",  "value"),
    State("verify-tickers", "value"),
    prevent_initial_call=True,
)
def start_verify(_, domain, codes, sample, tickers_raw):
    if not current_user.is_authenticated or not current_user.is_admin:
        return (no_update,) * 8
    if _verify_state["running"]:
        return False, {"display": "block"}, True, no_update, no_update, no_update, no_update, no_update

    tickers = None
    if tickers_raw and tickers_raw.strip():
        tickers = [t.strip() for t in tickers_raw.split(",") if t.strip()]

    _verify_state.update({"running": True, "current": 0, "total": 0, "label": "",
                          "result": None, "error": None})

    def _run():
        def _progress(cur, tot, label=""):
            _verify_state["current"] = cur
            _verify_state["total"]   = tot
            _verify_state["label"]   = label
        try:
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
    return False, {"display": "block"}, True, False, "", "", "", ""


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


def _format_summary(combos: list) -> str:
    """Un renglón por activo (no por código/activo como "combos"): cuántos
    códigos y diferencias tiene, ordenado de más a menos — para ver de un
    vistazo qué activos concentran el problema antes de bajar al detalle."""
    if not combos:
        return "Sin diferencias."
    by_asset: dict = {}
    for r in combos:
        key = (r["asset_id"], r["ticker"])
        agg = by_asset.setdefault(key, {"codes": 0, "diffs": 0})
        agg["codes"] += 1
        agg["diffs"] += len(r["diffs"])
    lines = [f"{len(by_asset)} activo(s) afectados:"]
    for (asset_id, ticker), agg in sorted(by_asset.items(), key=lambda kv: -kv[1]["diffs"]):
        lines.append(f"  {ticker} (id={asset_id}): {agg['codes']} código(s), "
                     f"{agg['diffs']} diferencia(s)")
    return "\n".join(lines)


def _format_detail(combos: list) -> str:
    if not combos:
        return ""
    lines = []
    for r in combos:
        lines.append(f"[DIFF] {r['code']} / {r['ticker']} (id={r['asset_id']}): "
                     f"{len(r['diffs'])} diferencias")
        for d, kind, stored, fresh, _cat in r["diffs"][:10]:
            lines.append(f"    {d}  {kind}  guardado={stored!r}  recalculado={fresh!r}")
        if len(r["diffs"]) > 10:
            lines.append(f"    ... y {len(r['diffs']) - 10} más")
        lines.append("")
    return "\n".join(lines)


@callback(
    Output("verify-run-interval",        "disabled",  allow_duplicate=True),
    Output("verify-run-progress",        "value",     allow_duplicate=True),
    Output("verify-run-progress",        "label",     allow_duplicate=True),
    Output("verify-run-progress",        "style",     allow_duplicate=True),
    Output("verify-run-btn",             "disabled",  allow_duplicate=True),
    Output("verify-run-alert",           "children",  allow_duplicate=True),
    Output("verify-run-alert",           "is_open",   allow_duplicate=True),
    Output("verify-run-alert",           "color",     allow_duplicate=True),
    Output("verify-run-summary-calc",    "children",  allow_duplicate=True),
    Output("verify-run-detail-calc",     "children",  allow_duplicate=True),
    Output("verify-run-summary-sanity",  "children",  allow_duplicate=True),
    Output("verify-run-detail-sanity",   "children",  allow_duplicate=True),
    Input("verify-run-interval", "n_intervals"),
    prevent_initial_call=True,
)
def poll_verify(_):
    if _verify_state["running"]:
        tot = _verify_state["total"] or 1
        pct = int(_verify_state["current"] / tot * 100)
        label = f"{_verify_state['current']} / {_verify_state['total']}  {_verify_state['label']}"
        return (False, pct, label, {"display": "block"}, True,
                no_update, False, no_update, no_update, no_update, no_update, no_update)

    if _verify_state["error"]:
        msg = f"Error corriendo la verificación: {_verify_state['error']}"
        return (True, 0, "", {"display": "none"}, False,
                msg, True, "danger", "", "", "", "")

    result = _verify_state["result"]
    if result is None:
        return (True, 0, "", {"display": "none"}, False,
                no_update, False, no_update, no_update, no_update, no_update, no_update)

    calc, sanity = _split_by_category(result)
    n_calc   = sum(len(r["diffs"]) for r in calc)
    n_sanity = sum(len(r["diffs"]) for r in sanity)
    if n_calc == 0 and n_sanity == 0:
        color = "success"
        msg = (f"OK — sin diferencias en {len(result['codes'])} códigos x "
               f"{len(result['asset_ids'])} activos ({result['combos']} combinaciones).")
    elif n_calc == 0:
        color = "warning"
        msg = (f"Sin discrepancias de cálculo. {n_sanity} posibles errores de datos de "
               f"origen (revisar el dato de entrada, no es un bug de caché) — ver pestaña "
               f"'Datos de origen'.")
    else:
        color = "danger"
        msg = (f"{n_calc} discrepancias de cálculo (posible bug de caché/delta) + "
               f"{n_sanity} posibles errores de datos de origen — ver detalle en cada pestaña.")
    if result["missing_tickers"]:
        msg += f" (tickers no encontrados, salteados: {', '.join(result['missing_tickers'])})"

    return (True, 100, "Completo", {"display": "none"}, False,
            msg, True, color,
            _format_summary(calc),   _format_detail(calc),
            _format_summary(sanity), _format_detail(sanity))
