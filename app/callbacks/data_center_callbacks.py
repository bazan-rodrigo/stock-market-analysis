import threading

import dash_bootstrap_components as dbc
from dash import Input, Output, State, callback, html, no_update

from app.database import get_session, Session as _ScopedSession
from app.models import (
    FundamentalUpdateLog, PriceUpdateLog,
    ScreenerSnapshot, SyntheticFormula,
)

_OPS         = ("prices", "fund", "snap", "indicators", "synth")
_HAS_NEW_ONLY = {"prices", "fund"}


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
    from app.models.indicator_value import IndicatorValue
    from app.models.indicator_definition import IndicatorDefinition
    from sqlalchemy import func as _func
    s = get_session()
    ind = s.query(IndicatorDefinition).filter(
        IndicatorDefinition.code == "fundamental_pe_ttm"
    ).first()
    if ind is None:
        return "Snapshots fundamentales: —"
    count = s.query(_func.count(_func.distinct(IndicatorValue.asset_id))).filter(
        IndicatorValue.indicator_id == ind.id
    ).scalar() or 0
    last_date = s.query(_func.max(IndicatorValue.date)).filter(
        IndicatorValue.indicator_id == ind.id
    ).scalar()
    last_s = str(last_date) if last_date else "—"
    return f"Snapshots fundamentales: {count} activos   Último: {last_s}"


def _status_indicators():
    from app.models.indicator_value import IndicatorValue
    from sqlalchemy import func as _func
    s     = get_session()
    total = s.query(_func.count(ScreenerSnapshot.id)).scalar() or 0
    iv_total = s.query(_func.count(_func.distinct(IndicatorValue.asset_id))).scalar() or 0
    return f"Snapshots técnicos: {total} activos  |  Indicator values: {iv_total} activos"


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
        first_err = errs[0].get("error", "") if errs else ""
        st["msg"]   = (f"Completado: {ok}/{total} OK  ·  {len(errs)} errores — {first_err[:300]}"
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
    has_new_only = op_id in _HAS_NEW_ONLY
    extra_states = [State(f"dc-new-only-{op_id}", "value")] if has_new_only else []

    @callback(
        Output(f"dc-interval-{op_id}", "disabled",  allow_duplicate=True),
        Output(f"dc-btn-{op_id}",      "disabled",  allow_duplicate=True),
        Output(f"dc-msg-{op_id}",      "children",  allow_duplicate=True),
        Input(f"dc-btn-{op_id}",       "n_clicks"),
        *extra_states,
        prevent_initial_call=True,
    )
    def _start(n, *args):
        if not n:
            return no_update, no_update, no_update

        new_only = bool(args[0]) if args else False

        if op_id == "prices":
            from app.services.price_service import (
                update_all_active_assets, update_new_assets_prices)
            fn = update_new_assets_prices if new_only else update_all_active_assets
        elif op_id == "fund":
            from app.services.fundamental_service import (
                update_all_fundamentals, update_new_fundamentals)
            fn = update_new_fundamentals if new_only else update_all_fundamentals
        elif op_id == "snap":
            from app.services.fundamental_service import recompute_all_snapshots as fn
        elif op_id == "indicators":
            from app.services.technical_service import recompute_all_snapshots as fn
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

