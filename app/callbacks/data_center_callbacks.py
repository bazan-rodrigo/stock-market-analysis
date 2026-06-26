import threading
from datetime import datetime

import dash_bootstrap_components as dbc
from dash import Input, Output, State, callback, html, no_update

from app.database import get_session
from app.models import FundamentalSnapshot, FundamentalUpdateLog, PriceUpdateLog, SyntheticFormula

# ── Estado por operación ─────────────────────────────────────────────────────

def _blank():
    return {"running": False, "current": 0, "total": 0, "msg": "", "error": False, "done": False}

_state = {op: _blank() for op in ("prices", "fund", "snap", "synth")}


# ── Helpers de estado ─────────────────────────────────────────────────────────

def _status_card(title, lines, color="#f59e0b"):
    return dbc.Card([
        dbc.CardHeader(html.Strong(title, style={"fontSize": "0.78rem"}),
                       style={"backgroundColor": "#111827", "padding": "6px 12px"}),
        dbc.CardBody(
            [html.Div(line, style={"fontSize": "0.72rem", "color": c}) for line, c in lines],
            style={"padding": "8px 12px"},
        ),
    ], style={"backgroundColor": "#1f2937", "border": "1px solid #374151",
              "borderRadius": "8px"})


def _get_price_status():
    s = get_session()
    logs  = s.query(PriceUpdateLog).all()
    total = len(logs)
    ok    = sum(1 for l in logs if l.success)
    last  = max((l.last_attempt_at for l in logs), default=None)
    last_s = last.strftime("%d/%m %H:%M") if last else "—"
    return _status_card("Precios", [
        (f"Activos: {total}", "#9ca3af"),
        (f"OK: {ok}  |  Errores: {total - ok}", "#4ade80" if total == ok else "#f87171"),
        (f"Último run: {last_s}", "#6b7280"),
    ])


def _get_fund_status():
    s = get_session()
    logs  = s.query(FundamentalUpdateLog).all()
    total = len(logs)
    ok    = sum(1 for l in logs if l.success)
    last  = max((l.last_attempt_at for l in logs), default=None)
    last_s = last.strftime("%d/%m %H:%M") if last else "—"
    return _status_card("Fundamentales", [
        (f"Con fuente: {total}", "#9ca3af"),
        (f"OK: {ok}  |  Errores: {total - ok}", "#4ade80" if total == ok else "#f87171"),
        (f"Último run: {last_s}", "#6b7280"),
    ])


def _get_snap_status():
    s = get_session()
    snaps = s.query(FundamentalSnapshot).all()
    total = len(snaps)
    last  = max((sn.updated_at for sn in snaps if sn.updated_at), default=None)
    last_s = last.strftime("%d/%m %H:%M") if last else "—"
    return _status_card("Snapshots", [
        (f"Activos con snapshot: {total}", "#9ca3af"),
        (f"Último recompute: {last_s}", "#6b7280"),
    ])


def _get_synth_status():
    s = get_session()
    total = s.query(SyntheticFormula).count()
    return _status_card("Sintéticos", [
        (f"Fórmulas definidas: {total}", "#9ca3af"),
    ])


# ── Callbacks de estado ───────────────────────────────────────────────────────

@callback(
    Output("dc-status-prices", "children"),
    Output("dc-status-fund",   "children"),
    Output("dc-status-snap",   "children"),
    Output("dc-status-synth",  "children"),
    Input("dc-status-interval", "n_intervals"),
)
def refresh_status(_):
    return (_get_price_status(), _get_fund_status(),
            _get_snap_status(),  _get_synth_status())


# ── Workers ───────────────────────────────────────────────────────────────────

def _run(op, fn):
    st = _state[op]
    st.update(running=True, current=0, total=0, msg="Iniciando...", error=False, done=False)

    def _progress(cur, tot):
        st["current"] = cur
        st["total"]   = tot
        st["msg"]     = f"{cur}/{tot}"

    try:
        result = fn(progress_cb=_progress)
        errs   = result.get("errors", [])
        ok     = result.get("success", result.get("total", 0) - len(errs))
        total  = result.get("total", 0)
        if errs:
            st["msg"]   = f"Completado: {ok}/{total} OK, {len(errs)} errores"
            st["error"] = True
        else:
            st["msg"] = f"Completado: {total} OK"
    except Exception as exc:
        st["msg"]   = f"Error: {exc}"
        st["error"] = True
    finally:
        st["running"] = False
        st["done"]    = True


# ── Callbacks por operación ───────────────────────────────────────────────────

def _make_callbacks(op_id):

    @callback(
        Output(f"dc-interval-{op_id}", "disabled", allow_duplicate=True),
        Output(f"dc-btn-{op_id}",      "disabled", allow_duplicate=True),
        Input(f"dc-btn-{op_id}",       "n_clicks"),
        prevent_initial_call=True,
    )
    def start(n):
        if not n:
            return no_update, no_update

        if op_id == "prices":
            from app.services.price_service import update_all_active_assets as fn
        elif op_id == "fund":
            from app.services.fundamental_service import update_all_fundamentals as fn
        elif op_id == "snap":
            from app.services.fundamental_service import recompute_all_snapshots as fn
        else:
            from app.services.synthetic_service import compute_all_synthetic as fn

        _state[op_id].update(_blank())
        threading.Thread(target=_run, args=(op_id, fn), daemon=True).start()
        return False, True   # habilita interval, deshabilita botón

    @callback(
        Output(f"dc-progress-{op_id}", "value"),
        Output(f"dc-progress-{op_id}", "style"),
        Output(f"dc-msg-{op_id}",      "children"),
        Output(f"dc-msg-{op_id}",      "style"),
        Output(f"dc-interval-{op_id}", "disabled", allow_duplicate=True),
        Output(f"dc-btn-{op_id}",      "disabled", allow_duplicate=True),
        Input(f"dc-interval-{op_id}",  "n_intervals"),
        prevent_initial_call=True,
    )
    def poll(_):
        st    = _state[op_id]
        total = st["total"] or 1
        pct   = int(st["current"] / total * 100) if st["total"] else 0
        msg   = st["msg"]
        color = "#f87171" if st["error"] else "#4ade80" if st["done"] else "#60a5fa"

        bar_style = {"height": "6px",
                     "display": "none" if (not st["running"] and not st["done"]) else "block"}
        done = not st["running"] and st["done"]
        return (
            pct if st["running"] else (100 if st["done"] else 0),
            bar_style,
            msg,
            {"fontSize": "0.75rem", "minHeight": "18px", "color": color},
            done,    # deshabilita el interval cuando termina
            not done,  # habilita botón cuando termina
        )


for _op in ("prices", "fund", "snap", "synth"):
    _make_callbacks(_op)
