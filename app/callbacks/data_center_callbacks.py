import threading
from datetime import datetime as _dt

import dash_bootstrap_components as dbc
from dash import Input, Output, State, callback, html, no_update

from app.database import get_session, Session as _ScopedSession
from app.models import (
    FundamentalUpdateLog, PriceUpdateLog,
    SyntheticFormula,
)

_OPS          = ("prices", "fund", "snap", "indicators", "synth")
_HAS_NEW_ONLY = {"prices", "fund"}
_HAS_REDOWNLOAD = {"prices", "fund", "synth", "snap", "indicators"}


def _blank():
    return {
        "running": False, "current": 0, "total": 0,
        "label": "", "msg": "", "error": False, "done": False,
        "start_time": None, "end_time": None,
        "workers": {},   # code -> {"dn", "tn", "start", "end"}
    }


def _fmt_time(dt) -> str:
    return dt.strftime("%H:%M:%S") if dt else "—"

_state = {op: _blank() for op in _OPS}


# ── Status por operación ──────────────────────────────────────────────────────

def _fmt_counts(ok, total, last):
    last_s = last.strftime("%d/%m %H:%M") if last else "—"
    err    = total - ok
    ok_txt = f"✓ {ok}" if ok else "—"
    err_cl = f"  ✗ {err}" if err else ""
    return f"Último run: {last_s}   {ok_txt}{err_cl}   ({total} activos)"


def _status_prices():
    try:
        s    = get_session()
        logs = s.query(PriceUpdateLog).all()
        ok   = sum(1 for l in logs if l.success)
        last = max((l.last_attempt_at for l in logs), default=None)
        return _fmt_counts(ok, len(logs), last)
    except Exception:
        return "—"


def _status_fund():
    try:
        s    = get_session()
        logs = s.query(FundamentalUpdateLog).all()
        ok   = sum(1 for l in logs if l.success)
        last = max((l.last_attempt_at for l in logs), default=None)
        return _fmt_counts(ok, len(logs), last)
    except Exception:
        return "—"


def _status_ratios():
    import sqlalchemy as sa
    from app.models.indicator_store import get_ind_table
    s = get_session()
    try:
        t = get_ind_table("fundamental_pe_ttm")
        count     = s.execute(sa.select(sa.func.count(sa.distinct(t.c.asset_id)))).scalar() or 0
        last_date = s.execute(sa.select(sa.func.max(t.c.date))).scalar()
        last_s    = str(last_date) if last_date else "—"
        return f"Ratios fundamentales: {count} activos   Último: {last_s}"
    except Exception:
        return "Ratios fundamentales: —"


def _status_indicators():
    import sqlalchemy as sa
    from app.models.indicator_definition import IndicatorDefinition
    from app.models.indicator_store import get_ind_table
    try:
        s = get_session()
        tech_codes = [
            r[0] for r in s.query(IndicatorDefinition.code).filter(
                IndicatorDefinition.keep_history.is_(True),
                IndicatorDefinition.category != "Fundamental",
            ).all()
        ]
    except Exception:
        return "—"
    total_rows:  int = 0
    assets_seen: set = set()
    for code in tech_codes:
        try:
            t = get_ind_table(code)
            total_rows += s.execute(sa.select(sa.func.count()).select_from(t)).scalar() or 0
            for row in s.execute(sa.select(t.c.asset_id).distinct()).fetchall():
                assets_seen.add(row[0])
        except Exception:
            continue
    return f"Indicator values: {total_rows:,} filas  |  {len(assets_seen)} activos con datos"


def _status_synth():
    try:
        s     = get_session()
        total = s.query(SyntheticFormula).count()
        return f"Fórmulas definidas: {total}"
    except Exception:
        return "—"


_STATUS_FN = {
    "prices":       _status_prices,
    "fund":         _status_fund,
    "snap":         _status_ratios,
    "indicators":   _status_indicators,
    "synth":        _status_synth,
}


@callback(
    Output("dc-status-prices",        "children"),
    Output("dc-status-fund",          "children"),
    Output("dc-status-snap",          "children"),
    Output("dc-status-indicators",    "children"),
    Output("dc-status-synth",         "children"),
    Input("dc-status-interval",       "n_intervals"),
    # Refrescar también cuando una operación arranca (baseline) o termina
    # (números finales). _poll solo escribe 'disabled' en la transición.
    *[Input(f"dc-interval-{_op_id}", "disabled") for _op_id in _OPS],
)
def refresh_status(*_):
    try:
        _ScopedSession.remove()
    except Exception:
        pass
    return tuple(fn() for fn in _STATUS_FN.values())


# ── Workers ───────────────────────────────────────────────────────────────────

def _run(op_id, service_fn):
    st = _state[op_id]
    st.update(_blank(), running=True, msg="Iniciando...", start_time=_dt.now())

    def _cb(cur, tot, label=""):
        st["current"] = cur
        st["total"]   = tot
        st["label"]   = label
        if label and label.startswith("__init__:"):
            try:
                _, n_str, codes_str = label.split(":", 2)
                n = int(n_str)
                for c in codes_str.split(","):
                    if c:
                        st["workers"].setdefault(
                            c, {"dn": 0, "tn": n, "start": None, "end": None})
            except Exception:
                pass
            st["msg"] = "calculando..."
            return
        if label and ": " in label:
            try:
                sep  = label.index(": ")
                code = label[:sep].strip()
                prog = label[sep + 2:].strip().split()[0]
                dn, tn = int(prog.split("/")[0]), int(prog.split("/")[1])
                w = st["workers"].setdefault(
                    code, {"dn": 0, "tn": tn, "start": None, "end": None})
                if dn == 1 and w["start"] is None:
                    w["start"] = _dt.now()
                w["dn"] = dn
                w["tn"] = tn
                if dn >= tn and w["end"] is None:
                    w["end"] = _dt.now()
            except Exception:
                pass
        st["msg"] = f"{cur} / {tot}" + (f"  —  {label}" if label else "")

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
        st["running"]  = False
        st["done"]     = True
        st["end_time"] = _dt.now()
        _ScopedSession.remove()


# ── Callbacks por operación ───────────────────────────────────────────────────

def _register(op_id):
    has_new_only = op_id in _HAS_NEW_ONLY

    extra_states = []
    if has_new_only:
        extra_states.append(State(f"dc-new-only-{op_id}", "value"))

    _BAR_RUNNING = {"height": "5px", "display": "flex"}

    @callback(
        Output(f"dc-interval-{op_id}", "disabled",  allow_duplicate=True),
        Output(f"dc-btn-{op_id}",      "disabled",  allow_duplicate=True),
        Output(f"dc-msg-{op_id}",      "children",  allow_duplicate=True),
        Output(f"dc-progress-{op_id}", "value",     allow_duplicate=True),
        Output(f"dc-progress-{op_id}", "style",     allow_duplicate=True),
        Input(f"dc-btn-{op_id}",       "n_clicks"),
        *extra_states,
        prevent_initial_call=True,
    )
    def _start(n, *args):
        if not n:
            return no_update, no_update, no_update, no_update, no_update

        extra_val = bool(args[0]) if args else False
        new_only  = extra_val if has_new_only else False

        if op_id == "prices":
            from app.services.price_service import (
                update_all_active_assets, update_new_assets_prices)
            fn = update_new_assets_prices if new_only else update_all_active_assets
        elif op_id == "fund":
            from app.services.fundamental_service import (
                update_all_fundamentals, update_new_fundamentals)
            fn = update_new_fundamentals if new_only else update_all_fundamentals
        elif op_id == "snap":
            from app.services.fundamental_service import update_ratio_history as fn
        elif op_id == "indicators":
            from app.services.technical_service import update_indicator_history as fn
        else:
            from app.services.synthetic_service import compute_all_synthetic as fn

        _state[op_id].update(_blank())
        threading.Thread(target=_run, args=(op_id, fn), daemon=True).start()
        return False, True, "Iniciando...", 0, _BAR_RUNNING

    has_redownload = op_id in _HAS_REDOWNLOAD
    if has_redownload:
        @callback(
            Output(f"dc-redownload-modal-{op_id}", "is_open"),
            Input(f"dc-btn-redownload-{op_id}",         "n_clicks"),
            Input(f"dc-btn-redownload-{op_id}-confirm", "n_clicks"),
            Input(f"dc-btn-redownload-{op_id}-cancel",  "n_clicks"),
            prevent_initial_call=True,
        )
        def _toggle_redownload_modal(n_open, n_confirm, n_cancel):
            from dash import ctx
            return ctx.triggered_id == f"dc-btn-redownload-{op_id}"

        @callback(
            Output(f"dc-redownload-modal-{op_id}", "is_open",  allow_duplicate=True),
            Output(f"dc-interval-{op_id}",          "disabled", allow_duplicate=True),
            Output(f"dc-btn-{op_id}",               "disabled", allow_duplicate=True),
            Output(f"dc-msg-{op_id}",               "children", allow_duplicate=True),
            Output(f"dc-progress-{op_id}",          "value",    allow_duplicate=True),
            Output(f"dc-progress-{op_id}",          "style",    allow_duplicate=True),
            Input(f"dc-btn-redownload-{op_id}-confirm", "n_clicks"),
            prevent_initial_call=True,
        )
        def _start_redownload(n):
            if not n:
                return no_update, no_update, no_update, no_update, no_update, no_update

            if op_id == "prices":
                from app.services.price_service import redownload_prices as fn
            elif op_id == "fund":
                from app.services.fundamental_service import redownload_all_fundamentals as fn
            elif op_id == "snap":
                from app.services.fundamental_service import rebuild_ratio_history as fn
            elif op_id == "indicators":
                from app.services.technical_service import rebuild_indicator_history as fn
            else:
                import functools
                from app.services.synthetic_service import compute_all_synthetic
                fn = functools.partial(compute_all_synthetic, full=True)

            _state[op_id].update(_blank())
            threading.Thread(target=_run, args=(op_id, fn), daemon=True).start()
            return False, False, True, "Iniciando...", 0, _BAR_RUNNING

    @callback(
        Output(f"dc-progress-{op_id}", "value",     allow_duplicate=True),
        Output(f"dc-progress-{op_id}", "style",     allow_duplicate=True),
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
            bar_style = {"height": "5px", "display": "flex"}
        elif st["done"]:
            bar_style = {"height": "5px", "display": "flex"}
        else:
            bar_style = {"height": "5px", "display": "none"}

        msg_color = ("#f87171" if st["error"]
                     else "#4ade80" if done
                     else "#9ca3af")

        t_start = _fmt_time(st.get("start_time"))
        t_end   = _fmt_time(st.get("end_time"))

        workers = st.get("workers", {})
        if workers and (st["running"] or st["done"]):
            done_cnt = sum(1 for w in workers.values() if w["dn"] >= w["tn"])
            rows = []
            for code, w in sorted(workers.items(),
                                   key=lambda x: x[1]["dn"], reverse=True):
                dn, tn = w["dn"], w["tn"]
                ws = _fmt_time(w["start"])
                we = _fmt_time(w["end"]) if w["end"] else ""
                if dn >= tn:
                    color = "#4ade80"
                    text  = f"✓ {code}   {ws} → {we}"
                elif dn > 0:
                    color = "#d1d5db"
                    text  = f"{code}: {dn}/{tn}   desde {ws}"
                else:
                    color = "#4b5563"
                    text  = code
                rows.append(html.Div(text, style={"fontSize": "0.72rem",
                                                   "color": color,
                                                   "lineHeight": "1.6",
                                                   "fontVariantNumeric": "tabular-nums"}))
            if done:
                overall = f"Completado: {done_cnt}/{len(workers)} OK  •  {t_start} → {t_end}"
            else:
                overall = (f"{st['current']} / {st['total']}  •  "
                           f"{done_cnt} / {len(workers)} indicadores listos  •  "
                           f"{t_start} → {t_end}")
            msg_children = [
                html.Div(overall, style={"fontSize": "0.73rem", "color": "#9ca3af",
                                         "marginBottom": "4px",
                                         "fontVariantNumeric": "tabular-nums"}),
                html.Div(rows),
            ]
            msg_style = {"minHeight": "16px", "marginBottom": "10px"}
        else:
            overall_times = (f"  •  {t_start} → {t_end}"
                             if st.get("start_time") else "")
            msg_children = str(st["msg"]) + overall_times if st.get("start_time") else st["msg"]
            msg_style    = {"fontSize": "0.74rem", "minHeight": "16px",
                            "marginBottom": "10px", "color": msg_color,
                            "fontVariantNumeric": "tabular-nums"}

        return (
            pct if st["running"] else (100 if done else 0),
            bar_style,
            msg_children,
            msg_style,
            # Escribir 'disabled' solo al terminar: cada escritura dispara
            # refresh_status, y durante la corrida no queremos recontar.
            True if done else no_update,
            False if done else no_update,
        )


for _op in _OPS:
    _register(_op)

