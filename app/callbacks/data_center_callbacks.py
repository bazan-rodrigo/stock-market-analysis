import threading

import dash_bootstrap_components as dbc
from dash import Input, Output, State, callback, html, no_update

from app.database import get_session, Session as _ScopedSession
from app.models import (
    FundamentalUpdateLog, PriceUpdateLog,
    SyntheticFormula,
)

_OPS          = ("prices", "fund", "snap", "indicators", "synth", "fund_backfill", "backfill")
_HAS_NEW_ONLY = {"prices", "fund"}
_HAS_FORCE    = {"backfill", "fund_backfill"}


def _blank():
    return {
        "running": False, "current": 0, "total": 0,
        "label": "", "msg": "", "error": False, "done": False,
        "workers": {},   # code -> (assets_done, assets_total)
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


def _status_snap():
    import sqlalchemy as sa
    from app.models.indicator_store import get_ind_table
    s = get_session()
    try:
        t = get_ind_table("fundamental_pe_ttm")
        count     = s.execute(sa.select(sa.func.count(sa.distinct(t.c.asset_id)))).scalar() or 0
        last_date = s.execute(sa.select(sa.func.max(t.c.date))).scalar()
        last_s    = str(last_date) if last_date else "—"
        return f"Snapshots fundamentales: {count} activos   Último: {last_s}"
    except Exception:
        return "Snapshots fundamentales: —"


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
    assets_seen: set = set()
    dates_seen:  set = set()
    for code in tech_codes:
        try:
            t = get_ind_table(code)
            for row in s.execute(sa.select(t.c.asset_id, t.c.date)).fetchall():
                assets_seen.add(row[0])
                dates_seen.add(row[1])
        except Exception:
            continue
    return f"Indicator values: {len(assets_seen)} activos  |  {len(dates_seen)} fechas"


def _status_synth():
    try:
        s     = get_session()
        total = s.query(SyntheticFormula).count()
        return f"Fórmulas definidas: {total}"
    except Exception:
        return "—"


def _status_fund_backfill():
    import sqlalchemy as sa
    from app.models.indicator_definition import IndicatorDefinition
    from app.models.indicator_store import get_ind_table
    try:
        s = get_session()
        fund_codes = [
            r[0] for r in s.query(IndicatorDefinition.code).filter(
                IndicatorDefinition.category == "Fundamental",
                IndicatorDefinition.keep_history.is_(True),
            ).all()
        ]
    except Exception:
        return "—"
    if not fund_codes:
        return "Sin indicadores fundamentales definidos"
    total_rows = 0
    assets_seen: set = set()
    for code in fund_codes:
        try:
            t = get_ind_table(code)
            total_rows += s.execute(sa.select(sa.func.count()).select_from(t)).scalar() or 0
            for row in s.execute(sa.select(t.c.asset_id).distinct()).fetchall():
                assets_seen.add(row[0])
        except Exception:
            continue
    return f"Historial fundamental: {total_rows:,} filas  |  {len(assets_seen)} activos con datos"


def _status_backfill():
    import sqlalchemy as sa
    from app.models.indicator_definition import IndicatorDefinition
    from app.models.indicator_store import get_ind_table
    try:
        s = get_session()
        tech_codes = [
            r[0] for r in s.query(IndicatorDefinition.code).filter(
                IndicatorDefinition.category != "Fundamental",
                IndicatorDefinition.keep_history.is_(True),
            ).all()
        ]
    except Exception:
        return "—"
    if not tech_codes:
        return "Sin indicadores técnicos definidos"
    total_rows = 0
    assets_seen: set = set()
    for code in tech_codes:
        try:
            t = get_ind_table(code)
            total_rows += s.execute(sa.select(sa.func.count()).select_from(t)).scalar() or 0
            for row in s.execute(sa.select(t.c.asset_id).distinct()).fetchall():
                assets_seen.add(row[0])
        except Exception:
            continue
    return f"Historial técnico: {total_rows:,} filas  |  {len(assets_seen)} activos con datos"


_STATUS_FN = {
    "prices":       _status_prices,
    "fund":         _status_fund,
    "snap":         _status_snap,
    "indicators":   _status_indicators,
    "synth":        _status_synth,
    "fund_backfill": _status_fund_backfill,
    "backfill":     _status_backfill,
}


@callback(
    Output("dc-status-prices",        "children"),
    Output("dc-status-fund",          "children"),
    Output("dc-status-snap",          "children"),
    Output("dc-status-indicators",    "children"),
    Output("dc-status-synth",         "children"),
    Output("dc-status-fund_backfill", "children"),
    Output("dc-status-backfill",      "children"),
    Input("dc-status-interval",       "n_intervals"),
)
def refresh_status(_):
    try:
        _ScopedSession.remove()
    except Exception:
        pass
    return tuple(fn() for fn in _STATUS_FN.values())


# ── Workers ───────────────────────────────────────────────────────────────────

def _run(op_id, service_fn):
    st = _state[op_id]
    st.update(_blank(), running=True, msg="Iniciando...")

    def _cb(cur, tot, label=""):
        st["current"] = cur
        st["total"]   = tot
        st["label"]   = label
        if label and label.startswith("__init__:"):
            # Pre-pobla todos los workers antes de que arranquen los threads
            try:
                _, n_str, codes_str = label.split(":", 2)
                n = int(n_str)
                for c in codes_str.split(","):
                    if c:
                        st["workers"].setdefault(c, (0, n))
            except Exception:
                pass
            st["msg"] = "calculando..."
            return
        # Parsea "code: N/M" para actualizar progreso por worker
        if label and ": " in label:
            try:
                sep  = label.index(": ")
                code = label[:sep].strip()
                prog = label[sep + 2:].strip().split()[0]   # "234/560"
                dn, tn = prog.split("/")
                st["workers"][code] = (int(dn), int(tn))
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
        st["running"] = False
        st["done"]    = True
        _ScopedSession.remove()


# ── Callbacks por operación ───────────────────────────────────────────────────

def _register(op_id):
    has_new_only = op_id in _HAS_NEW_ONLY
    has_force    = op_id in _HAS_FORCE

    extra_states = []
    if has_new_only:
        extra_states.append(State(f"dc-new-only-{op_id}", "value"))
    elif has_force:
        extra_states.append(State(f"dc-force-{op_id}", "value"))

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

        extra_val = bool(args[0]) if args else False
        new_only  = extra_val if has_new_only else False
        force     = extra_val if has_force    else False

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
        elif op_id == "fund_backfill":
            import functools
            from app.services.fundamental_service import backfill_all_fundamental_values
            fn = functools.partial(backfill_all_fundamental_values, force=force)
        elif op_id == "backfill":
            import functools
            from app.services.technical_service import backfill_all_indicator_values
            fn = functools.partial(backfill_all_indicator_values, force=force)
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

        workers = st.get("workers", {})
        if workers and st["running"]:
            done_cnt = sum(1 for dn, tn in workers.values() if dn >= tn)
            pct      = int(done_cnt / len(workers) * 100) if workers else 0
            rows = []
            for code, (dn, tn) in sorted(workers.items(), key=lambda x: x[1][0], reverse=True):
                if dn >= tn:
                    color = "#4ade80"
                    text  = f"✓ {code}"
                elif dn > 0:
                    color = "#d1d5db"
                    text  = f"{code}: {dn}/{tn}"
                else:
                    color = "#4b5563"
                    text  = code
                rows.append(html.Div(text, style={"fontSize": "0.72rem",
                                                   "color": color,
                                                   "lineHeight": "1.6"}))
            msg_children = [
                html.Div(
                    f"{st['current']} / {st['total']}  •  "
                    f"{done_cnt} / {len(workers)} indicadores listos",
                    style={"fontSize": "0.73rem", "color": "#9ca3af", "marginBottom": "4px"},
                ),
                html.Div(rows),
            ]
            msg_style = {"minHeight": "16px", "marginBottom": "10px"}
        else:
            msg_children = st["msg"]
            msg_style    = {"fontSize": "0.74rem", "minHeight": "16px",
                            "marginBottom": "10px", "color": msg_color}

        return (
            pct if st["running"] else (100 if done else 0),
            bar_style,
            msg_children,
            msg_style,
            done,
            not done,
        )


for _op in _OPS:
    _register(_op)

