import threading

import dash_bootstrap_components as dbc
from dash import Input, Output, callback, html, no_update

from app.database import get_session, Session as _ScopedSession
from app.models import (
    FundamentalSnapshot, FundamentalUpdateLog, PriceUpdateLog,
    ScreenerSnapshot, SyntheticFormula,
)

_OPS = ("prices", "fund", "snap", "indicators", "synth")


def _blank():
    return {
        "running": False, "current": 0, "total": 0,
        "label": "", "msg": "", "error": False, "done": False,
    }

_state = {op: _blank() for op in _OPS}


# ── Status por operación ──────────────────────────────────────────────────────

def _fmt_counts(ok, total, last):
    last_s = last.strftime("%d/%m %H:%M") if last else "—"
    err    = total - ok
    ok_txt = f"✓ {ok}" if ok else "—"
    err_cl = f"  ✗ {err}" if err else ""
    return f"Último run: {last_s}   {ok_txt}{err_cl}   ({total} activos)"


def _status_prices():
    s     = get_session()
    logs  = s.query(PriceUpdateLog).all()
    ok    = sum(1 for l in logs if l.success)
    last  = max((l.last_attempt_at for l in logs), default=None)
    return _fmt_counts(ok, len(logs), last)


def _status_fund():
    s     = get_session()
    logs  = s.query(FundamentalUpdateLog).all()
    ok    = sum(1 for l in logs if l.success)
    last  = max((l.last_attempt_at for l in logs), default=None)
    return _fmt_counts(ok, len(logs), last)


def _status_snap():
    s     = get_session()
    snaps = s.query(FundamentalSnapshot).all()
    last  = max((sn.updated_at for sn in snaps if sn.updated_at), default=None)
    last_s = last.strftime("%d/%m %H:%M") if last else "—"
    return f"Snapshots fundamentales: {len(snaps)}   Último recompute: {last_s}"


def _status_indicators():
    s     = get_session()
    total = s.query(ScreenerSnapshot).count()
    return f"Snapshots técnicos: {total} activos"


def _status_synth():
    s     = get_session()
    total = s.query(SyntheticFormula).count()
    return f"Fórmulas definidas: {total}"


_STATUS_FN = {
    "prices":     _status_prices,
    "fund":       _status_fund,
    "snap":       _status_snap,
    "indicators": _status_indicators,
    "synth":      _status_synth,
}


@callback(
    Output("dc-status-prices",     "children"),
    Output("dc-status-fund",       "children"),
    Output("dc-status-snap",       "children"),
    Output("dc-status-indicators", "children"),
    Output("dc-status-synth",      "children"),
    Input("dc-status-interval",    "n_intervals"),
)
def refresh_status(_):
    return tuple(fn() for fn in _STATUS_FN.values())


# ── Workers ───────────────────────────────────────────────────────────────────

def _run(op_id, service_fn):
    st = _state[op_id]
    st.update(_blank(), running=True, msg="Iniciando...")

    def _cb(cur, tot, label=""):
        st["current"] = cur
        st["total"]   = tot
        st["label"]   = label
        st["msg"]     = f"{cur} / {tot}" + (f"  —  {label}" if label else "")

    try:
        result = service_fn(progress_cb=_cb)
        errs   = result.get("errors", [])
        total  = result.get("total", 0)
        ok     = result.get("success", total - len(errs))
        st["msg"]   = (f"Completado: {ok}/{total} OK  ·  {len(errs)} errores"
                       if errs else f"Completado: {total} OK")
        st["error"] = bool(errs)
    except Exception as exc:
        st["msg"]   = f"Error: {exc}"
        st["error"] = True
    finally:
        st["running"] = False
        st["done"]    = True
        _ScopedSession.remove()


# ── Callbacks por operación ───────────────────────────────────────────────────

def _register(op_id):

    @callback(
        Output(f"dc-interval-{op_id}", "disabled",  allow_duplicate=True),
        Output(f"dc-btn-{op_id}",      "disabled",  allow_duplicate=True),
        Output(f"dc-msg-{op_id}",      "children",  allow_duplicate=True),
        Input(f"dc-btn-{op_id}",       "n_clicks"),
        prevent_initial_call=True,
    )
    def _start(n):
        if not n:
            return no_update, no_update, no_update

        if op_id == "prices":
            from app.services.price_service import update_all_active_assets as fn
        elif op_id == "fund":
            from app.services.fundamental_service import update_all_fundamentals as fn
        elif op_id == "snap":
            from app.services.fundamental_service import recompute_all_snapshots as fn
        elif op_id == "indicators":
            from app.services.screener_service import recompute_all_snapshots as fn
        else:
            from app.services.synthetic_service import compute_all_synthetic as fn

        _state[op_id].update(_blank())
        threading.Thread(target=_run, args=(op_id, fn), daemon=True).start()
        return False, True, "Iniciando..."

    @callback(
        Output(f"dc-progress-{op_id}", "value"),
        Output(f"dc-progress-{op_id}", "style"),
        Output(f"dc-msg-{op_id}",      "children",  allow_duplicate=True),
        Output(f"dc-msg-{op_id}",      "style"),
        Output(f"dc-interval-{op_id}", "disabled",  allow_duplicate=True),
        Output(f"dc-btn-{op_id}",      "disabled",  allow_duplicate=True),
        Input(f"dc-interval-{op_id}",  "n_intervals"),
        prevent_initial_call=True,
    )
    def _poll(_):
        st    = _state[op_id]
        tot   = st["total"] or 1
        pct   = int(st["current"] / tot * 100) if st["total"] else 0
        done  = st["done"] and not st["running"]

        if st["running"]:
            bar_style = {"height": "5px", "display": "block"}
        elif st["done"]:
            bar_style = {"height": "5px", "display": "block"}
        else:
            bar_style = {"height": "5px", "display": "none"}

        msg_color = ("#f87171" if st["error"]
                     else "#4ade80" if done
                     else "#9ca3af")

        return (
            pct if st["running"] else (100 if done else 0),
            bar_style,
            st["msg"],
            {"fontSize": "0.74rem", "minHeight": "16px",
             "marginBottom": "10px", "color": msg_color},
            done,    # deshabilita interval al terminar
            not done,  # habilita botón al terminar
        )


for _op in _OPS:
    _register(_op)
