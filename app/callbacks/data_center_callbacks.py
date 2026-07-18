import threading
from datetime import datetime as _dt

import dash_bootstrap_components as dbc
from dash import Input, Output, State, callback, html, no_update

from app.database import get_session, Session as _ScopedSession
from app.models import (
    FundamentalUpdateLog, PriceUpdateLog,
    SyntheticFormula,
)
from app.services import run_lock_service as _rl

_OPS          = ("prices", "fund", "snap", "indicators", "synth", "signals")
_HAS_NEW_ONLY = {"prices", "fund"}
_HAS_REDOWNLOAD = {"prices", "fund", "synth", "snap", "indicators", "signals"}
_HAS_RECONCILE  = {"indicators"}
_HAS_DAYS       = {"signals"}  # horizonte en días (input dc-days-{op})


def _blank():
    return {
        "running": False, "current": 0, "total": 0,
        "label": "", "msg": "", "error": False, "done": False,
        "start_time": None, "end_time": None,
        "workers": {},   # code -> {"dn", "tn", "start", "end"}
    }


def _fmt_time(dt) -> str:
    return dt.strftime("%H:%M:%S") if dt else "—"


def _fmt_dur(t0, t1) -> str:
    """Duración legible entre dos datetimes: '42s', '10m49s', '1h05m'."""
    if not t0 or not t1:
        return ""
    secs = max(0, int((t1 - t0).total_seconds()))
    m, s = divmod(secs, 60)
    if m >= 60:
        h, m = divmod(m, 60)
        return f"{h}h{m:02d}m"
    return f"{m}m{s:02d}s" if m else f"{s}s"

_state = {op: _blank() for op in _OPS}


def _any_running() -> bool:
    """Sistema ocupado: considera las 3 fuentes de escritura masiva —
    operaciones del Centro de Datos, botones de la pantalla de precios,
    y la corrida nocturna del scheduler."""
    if any(st["running"] for st in _state.values()):
        return True
    try:
        from app.callbacks.price_callbacks import _prices_state
        if _prices_state.get("running"):
            return True
    except Exception:
        pass
    try:
        from app.services.scheduler_service import is_daily_update_running
        return is_daily_update_running()
    except Exception:
        return False


_BUSY_MSG = "Hay otra operación en curso. Esperá a que termine antes de lanzar esta."


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
    from app.models import IndicatorUpdateLog
    try:
        s = get_session()
        # Fase 5 (design_ind_wide_tables.md): los indicadores técnicos con
        # historia viven en 3 tablas anchas por cadencia (una fila por
        # activo/fecha), no en 24 ind_{code}. El conteo es de FILAS de esas
        # tablas (no de valores individuales).
        from app.models.indicator_store import _WIDE_CADENCE_TABLE
        tech_tables = set(_WIDE_CADENCE_TABLE.values())
        # Estimación por catálogo (instantánea, por dialecto en db_compat):
        # un COUNT(*) exacto escanea millones de filas por tabla y bajo
        # carga tarda minutos
        from app.services import db_compat
        rows = db_compat.approx_table_rows(s, "ind_")
        total_rows = sum(n for name, n in rows.items() if name in tech_tables)
        assets_ok = s.query(IndicatorUpdateLog).filter(
            IndicatorUpdateLog.success.is_(True)).count()
        return f"Indicator values: ~{total_rows:,} filas  |  {assets_ok} activos con indicadores OK"
    except Exception:
        return "—"


def _status_synth():
    try:
        s     = get_session()
        total = s.query(SyntheticFormula).count()
        return f"Fórmulas definidas: {total}"
    except Exception:
        return "—"


def _status_signals():
    import sqlalchemy as sa
    try:
        s = get_session()
        # Ambos van contra signal_eval_log (un registro por fecha evaluada,
        # tabla chica): COUNT(DISTINCT date) sobre las tablas de señales
        # escaneaba 40M de filas (100s medidos) en cada refresh del panel,
        # compitiendo por I/O con las corridas.
        last = s.execute(sa.text(
            "SELECT MAX(date) FROM signal_eval_log")).scalar()
        n_dates = s.execute(sa.text(
            "SELECT COUNT(DISTINCT date) FROM signal_eval_log")).scalar()
        last_s = str(last) if last else "—"
        return f"Fechas evaluadas: {n_dates or 0}   Última: {last_s}"
    except Exception:
        return "—"


_STATUS_FN = {
    "prices":       _status_prices,
    "fund":         _status_fund,
    "snap":         _status_ratios,
    "indicators":   _status_indicators,
    "synth":        _status_synth,
    "signals":      _status_signals,
}

# Último estado calculado por tarjeta: con una operación corriendo, las
# tarjetas ajenas muestran esto en vez de un texto tipo "actualizando…"
# que daba a entender que ELLAS estaban trabajando (señalado por el
# usuario: recalcular señales mostraba "actualizando…" en Indicadores).
_status_cache: dict[str, str] = {}


@callback(
    Output("dc-status-prices",        "children"),
    Output("dc-status-fund",          "children"),
    Output("dc-status-snap",          "children"),
    Output("dc-status-indicators",    "children"),
    Output("dc-status-synth",         "children"),
    Output("dc-status-signals",       "children"),
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
    if _any_running():
        # Con una operación en curso, los COUNT pesados (ratios,
        # indicadores, señales) son inútiles (el número cambia por miles) y
        # compiten por I/O con las escrituras masivas — cada tarjeta
        # conserva su último estado real; el conteo fresco llega al
        # terminar la operación.
        return (_status_prices(), _status_fund(),
                _status_cache.get("snap", "—"),
                _status_cache.get("indicators", "—"),
                _status_synth(),
                _status_cache.get("signals", "—"))
    out = {op: fn() for op, fn in _STATUS_FN.items()}
    _status_cache.update(out)
    return tuple(out.values())


# ── Workers ───────────────────────────────────────────────────────────────────

def _launch_run(op_id, fn, lock_token):
    """Lanza _run tras haber tomado el lock. _run libera el lock (vía
    heartbeating) al terminar; pero si el thread NO llega a arrancar, nadie
    liberaría — por eso este wrapper libera ante cualquier fallo previo al
    start, para no dejar el lock trabado hasta el stale-reclaim."""
    try:
        _state[op_id].update(_blank(), running=True, msg="Iniciando...")
        threading.Thread(target=_run, args=(op_id, fn, lock_token),
                         daemon=True).start()
    except Exception:
        _rl.release(_rl.HEAVY_WRITE, lock_token)
        raise


def _run(op_id, service_fn, lock_token=_rl.NO_LOCK):
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
                            c, {"dn": 0, "tn": n, "start": None, "end": None, "worker": None})
            except Exception:
                pass
            st["msg"] = "calculando..."
            return
        if label and label.startswith("__pc__:"):
            # Cuántos activos de este código cayeron al camino lento del
            # delta (gap/checksum/bench) en vez del rápido — ver
            # _DELTA_TAIL_MODE/path_counts en technical_service.py.
            try:
                _, code, fast, gap, checksum, bench = label.split(":")
                w = st["workers"].setdefault(
                    code, {"dn": 0, "tn": 0, "start": None, "end": None, "worker": None})
                w["path_counts"] = {
                    "fast": int(fast), "gap": int(gap),
                    "checksum": int(checksum), "bench": int(bench),
                }
            except Exception:
                pass
            return
        if label and ": " in label:
            try:
                sep    = label.index(": ")
                code   = label[:sep].strip()
                tokens = label[sep + 2:].strip().split()
                prog   = tokens[0]
                dn, tn = int(prog.split("/")[0]), int(prog.split("/")[1])
                # Tokens opcionales tras el progreso:
                #  - "t={segundos}": tiempo ACUMULADO de la etapa (timers de
                #    la instrumentación, no reloj de pared) — filas por etapa
                #    de señales.
                #  - identidad del thread: "w{n}" entero (worker slot de
                #    indicadores, _worker_slot) o texto corto tal cual
                #    ("w1..w8", "productor", "escritor").
                #  - el resto se muestra como detalle de actividad actual
                #    (fecha en curso, rango del chunk, retraso del escritor).
                worker, secs, detail = None, None, []
                for tok in tokens[1:]:
                    if tok.startswith("t="):
                        try:
                            secs = float(tok[2:])
                        except ValueError:
                            pass
                    elif worker is None:
                        worker = (int(tok[1:])
                                  if tok.startswith("w") and tok[1:].isdigit()
                                  else tok)
                    else:
                        detail.append(tok)
                w = st["workers"].setdefault(
                    code, {"dn": 0, "tn": tn, "start": None, "end": None, "worker": None})
                # dn > 0 (no == 1): el escritor persiste de a lotes y su
                # primera actualización salta de 0 a cientos — con == 1 la
                # fila quedaba "desde —" para siempre
                if dn > 0 and w["start"] is None:
                    w["start"] = _dt.now()
                # Monotónico: con el pool por lotes varios threads avanzan el
                # MISMO código y el label se emite fuera del lock — un tick
                # rezagado puede llegar DESPUÉS de uno mayor; aplicar el
                # último a ciegas dejaba la fila final en dn<tn sin ✓.
                w["dn"] = max(dn, w["dn"])
                w["tn"] = tn
                if worker is not None:
                    w["worker"] = worker
                if secs is not None:
                    w["secs"] = secs
                if detail:
                    w["detail"] = " ".join(detail)
                if dn >= tn and w["end"] is None:
                    w["end"] = _dt.now()
            except Exception:
                pass
        st["msg"] = f"{cur} / {tot}" + (f"  —  {label}" if label else "")

    try:
        # heartbeating late el lock persistido mientras corre (así otro
        # proceso lo ve vivo) y lo LIBERA al salir — el guard de _start lo
        # tomó y pasó su token. Con NO_LOCK (fail-open pre-migración) es no-op.
        with _rl.heartbeating(_rl.HEAVY_WRITE, lock_token):
            result = service_fn(progress_cb=_cb)
        errs   = result.get("errors", [])
        total  = result.get("total", 0)
        ok     = result.get("success", total - len(errs))
        first_err = errs[0].get("error", "") if errs else ""
        st["msg"]   = (f"Completado: {ok}/{total} OK  ·  {len(errs)} errores — {first_err[:300]}"
                       if errs else f"Completado: {total} OK")
        # Desglose del modo rango de señales (para decidir dónde optimizar)
        t = result.get("timings")
        if t and not errs:
            st["msg"] += (f"  ·  lectura {t['read_s']:.0f}s / "
                          f"cómputo {t['compute_s']:.0f}s / "
                          f"espera escritor {t['wait_s']:.0f}s")
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

def _days_partial(fn, days, scope=None, with_signals=True):
    """Fija horizonte en días y alcance para las ops que lo aceptan
    (_HAS_DAYS): scope None = todo, "strategy:<id>" o "signal:<key>".
    days vacío/inválido = SIN horizonte (toda la historia) — antes caía
    silenciosamente a 365 y un 'sin horizonte' pedido a mano calculaba
    solo un año. with_signals=False (solo con alcance de estrategia):
    lee las señales guardadas y reconstruye solo strategy_result."""
    import functools
    try:
        days = max(1, int(days))
    except (TypeError, ValueError):
        days = None
    return functools.partial(fn, days=days, scope=scope or None,
                             with_signals=with_signals)


@callback(
    Output("dc-scope-signals", "options"),
    Input("dc-status-interval", "n_intervals"),
)
def load_signal_scope_opts(_):
    """Opciones del alcance del backfill de señales: estrategias y señales."""
    try:
        from app.models import SignalDefinition, Strategy
        s = get_session()
        strategies = s.query(Strategy.id, Strategy.name).order_by(Strategy.name).all()
        signals = s.query(SignalDefinition.key, SignalDefinition.name).order_by(
            SignalDefinition.key).all()
        return (
            [{"label": f"[Estrategia] {name}", "value": f"strategy:{sid}"}
             for sid, name in strategies]
            + [{"label": f"[Señal] {key} — {name}", "value": f"signal:{key}"}
               for key, name in signals]
        )
    except Exception:
        return []


@callback(
    Output("dc-redownload-body-signals", "children"),
    Input("dc-btn-redownload-signals", "n_clicks"),
    State("dc-scope-signals", "value"),
    State("dc-with-signals-signals", "value"),
    State("dc-days-signals", "value"),
    prevent_initial_call=True,
)
def update_signals_confirm_body(_n, scope, with_signals, days):
    """El modal de confirmación de 'Recalcular completo' dice EXACTAMENTE
    qué va a pasar según alcance + «Incluir señales» + horizonte (el texto
    fijo describía siempre el recálculo total, aunque el alcance fuera una
    sola estrategia)."""
    try:
        horizon = f"para los últimos {max(1, int(days))} días"
    except (TypeError, ValueError):
        horizon = "para TODA la historia de precios"

    kind, _, val = (scope or "").partition(":")
    if kind == "strategy":
        try:
            from app.models import Strategy
            strat = get_session().get(Strategy, int(val))
            name = strat.name if strat is not None else f"id={val}"
        except Exception:
            name = f"id={val}"
        if with_signals is False:
            return (f"Se reconstruirá SOLO el resultado de la estrategia "
                    f"«{name}» {horizon}, leyendo las señales ya guardadas "
                    "(ninguna señal se re-evalúa ni se toca). Es el camino "
                    "rápido para cuando solo cambió la estrategia. ¿Confirmás?")
        return (f"Se recalcularán las señales que usa la estrategia «{name}» "
                f"(componentes y filtro) y se reconstruirá su resultado "
                f"{horizon}, reescribiendo lo ya calculado. Puede demorar "
                "varios minutos. ¿Confirmás?")
    if kind == "signal":
        return (f"Se recalculará la señal «{val}» {horizon}, reescribiendo "
                "sus scores. No se tocan los resultados de estrategias. "
                "¿Confirmás?")
    return ("Se recalcularán TODAS las señales y los resultados de TODAS "
            f"las estrategias {horizon}, vaciando y reconstruyendo lo ya "
            "calculado. Puede demorar varios minutos. ¿Confirmás?")


def _register(op_id):
    has_new_only = op_id in _HAS_NEW_ONLY
    has_days     = op_id in _HAS_DAYS

    extra_states = []
    if has_new_only:
        extra_states.append(State(f"dc-new-only-{op_id}", "value"))
    if has_days:
        extra_states.append(State(f"dc-days-{op_id}",  "value"))
        extra_states.append(State(f"dc-scope-{op_id}", "value"))
        extra_states.append(State(f"dc-with-signals-{op_id}", "value"))

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

        # Exclusión mutua: guard en memoria (rápido, cubre este proceso).
        if _any_running():
            return no_update, no_update, _BUSY_MSG, no_update, no_update

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
        elif op_id == "signals":
            from app.services.signal_service import update_signal_history
            days, scope, with_sig = (args + (None, None, None))[:3]
            fn = _days_partial(update_signal_history, days, scope,
                               with_signals=(with_sig is not False))
        else:
            from app.services.synthetic_service import compute_all_synthetic as fn

        # Lock persistido atómico DESPUÉS de armar fn (así un fallo al armar
        # no filtra el lock): cross-proceso y a prueba de reciclado (cierra
        # la carrera check-then-act y la doble corrida con hijos huérfanos).
        # None = otro tiene el lock vivo; token/NO_LOCK = proceder. _run lo
        # libera vía heartbeating.
        lock_token = _rl.guarded_acquire(_rl.HEAVY_WRITE)
        if lock_token is None:
            return no_update, no_update, _BUSY_MSG, no_update, no_update
        _launch_run(op_id, fn, lock_token)
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

        redownload_states = []
        if has_days:
            redownload_states.append(State(f"dc-days-{op_id}",  "value"))
            redownload_states.append(State(f"dc-scope-{op_id}", "value"))
            # Sin este State, with_sig llegaba siempre None y el switch
            # "Incluir señales" se ignoraba en "Recalcular completo"
            redownload_states.append(State(f"dc-with-signals-{op_id}", "value"))

        @callback(
            Output(f"dc-redownload-modal-{op_id}", "is_open",  allow_duplicate=True),
            Output(f"dc-interval-{op_id}",          "disabled", allow_duplicate=True),
            Output(f"dc-btn-{op_id}",               "disabled", allow_duplicate=True),
            Output(f"dc-msg-{op_id}",               "children", allow_duplicate=True),
            Output(f"dc-progress-{op_id}",          "value",    allow_duplicate=True),
            Output(f"dc-progress-{op_id}",          "style",    allow_duplicate=True),
            Input(f"dc-btn-redownload-{op_id}-confirm", "n_clicks"),
            *redownload_states,
            prevent_initial_call=True,
        )
        def _start_redownload(n, *args):
            if not n:
                return no_update, no_update, no_update, no_update, no_update, no_update

            if _any_running():
                return False, no_update, no_update, _BUSY_MSG, no_update, no_update

            if op_id == "prices":
                from app.services.price_service import redownload_prices as fn
            elif op_id == "fund":
                from app.services.fundamental_service import redownload_all_fundamentals as fn
            elif op_id == "snap":
                from app.services.fundamental_service import rebuild_ratio_history as fn
            elif op_id == "indicators":
                from app.services.technical_service import rebuild_indicator_history as fn
            elif op_id == "signals":
                from app.services.signal_service import rebuild_signal_history
                days, scope, with_sig = (args + (None, None, None))[:3]
                fn = _days_partial(rebuild_signal_history, days, scope,
                                   with_signals=(with_sig is not False))
            else:
                import functools
                from app.services.synthetic_service import compute_all_synthetic
                fn = functools.partial(compute_all_synthetic, full=True)

            lock_token = _rl.guarded_acquire(_rl.HEAVY_WRITE)
            if lock_token is None:
                return False, no_update, no_update, _BUSY_MSG, no_update, no_update
            _launch_run(op_id, fn, lock_token)
            return False, False, True, "Iniciando...", 0, _BAR_RUNNING

    has_reconcile = op_id in _HAS_RECONCILE
    if has_reconcile:
        @callback(
            Output(f"dc-interval-{op_id}", "disabled",  allow_duplicate=True),
            Output(f"dc-btn-{op_id}",      "disabled",  allow_duplicate=True),
            Output(f"dc-msg-{op_id}",      "children",  allow_duplicate=True),
            Output(f"dc-progress-{op_id}", "value",     allow_duplicate=True),
            Output(f"dc-progress-{op_id}", "style",     allow_duplicate=True),
            Input(f"dc-btn-reconcile-{op_id}", "n_clicks"),
            prevent_initial_call=True,
        )
        def _start_reconcile(n):
            if not n:
                return no_update, no_update, no_update, no_update, no_update

            if _any_running():
                return no_update, no_update, _BUSY_MSG, no_update, no_update

            from app.services.technical_service import reconcile_ind_asset_meta as fn

            lock_token = _rl.guarded_acquire(_rl.HEAVY_WRITE)
            if lock_token is None:
                return no_update, no_update, _BUSY_MSG, no_update, no_update
            _launch_run(op_id, fn, lock_token)
            return False, True, "Iniciando...", 0, _BAR_RUNNING

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
            # Ancho de la columna de indicador (el más largo del lote)
            name_w = max((len(c) for c in workers), default=20) + 2
            rows = []
            for code, w in sorted(workers.items(),
                                   key=lambda x: x[1]["dn"], reverse=True):
                dn, tn = w["dn"], w["tn"]
                ws = _fmt_time(w["start"])
                we = _fmt_time(w["end"]) if w["end"] else ""
                prog = f"{dn:>4}/{tn}"
                # Worker real que proceso este indicador (diagnostico de
                # scheduling/concurrencia, ver _worker_slot en technical_service.py)
                wk = w.get("worker")
                wk_tag = ""
                if wk is not None:
                    wk_tag = f" [w{wk}]" if isinstance(wk, int) else f" [{wk}]"
                # Cuántos activos de este código cayeron al camino lento del
                # delta (gap/checksum/bench) en vez del rápido — ver
                # _DELTA_TAIL_MODE/path_counts en technical_service.py.
                pc = w.get("path_counts")
                slow_tag = ""
                if pc:
                    slow_n = pc["gap"] + pc["checksum"] + pc["bench"]
                    if slow_n:
                        detail = ", ".join(
                            f"{k}={pc[k]}" for k in ("gap", "checksum", "bench") if pc[k]
                        )
                        slow_tag = f"  ·  lento={slow_n} ({detail})"
                if w.get("secs") is not None:
                    # Fila por ETAPA (señales): lo útil en vivo es lo que
                    # DIFIERE entre etapas — segundos acumulados de la etapa
                    # + actividad actual — no el % (las tres avanzan casi en
                    # paralelo y triplicarían la barra)
                    mark  = "✓" if dn >= tn else " "
                    color = ("#4ade80" if dn >= tn
                             else "#d1d5db" if dn > 0 else "#4b5563")
                    text  = (f"{mark} {code:<{name_w}}{prog}"
                             f"  {w['secs']:>5.0f}s{wk_tag}"
                             f"  {w.get('detail', '')}")
                elif dn >= tn:
                    color = "#4ade80"
                    text  = (f"✓ {code:<{name_w}}{prog}   {ws} → {we}"
                             f"  ({_fmt_dur(w['start'], w['end'])}){wk_tag}{slow_tag}")
                elif dn > 0:
                    color = "#d1d5db"
                    text  = f"  {code:<{name_w}}{prog}   desde {ws}{wk_tag}"
                else:
                    color = "#4b5563"
                    text  = f"  {code:<{name_w}}{'—':>4}"
                rows.append(html.Div(text, style={"fontSize": "0.72rem",
                                                   "color": color,
                                                   "lineHeight": "1.6",
                                                   "fontFamily": "monospace",
                                                   "whiteSpace": "pre"}))
            if done:
                total_dur = _fmt_dur(st.get("start_time"), st.get("end_time"))
                if all("secs" in w for w in workers.values()):
                    # Filas por ETAPA (señales): el mensaje final real ya
                    # trae el conteo de fechas y el desglose de tiempos —
                    # no pisarlo con un conteo de filas ("3/3 OK")
                    overall = f"{st['msg']}  •  {t_start} → {t_end}  ({total_dur})"
                else:
                    overall = (f"Completado: {done_cnt}/{len(workers)} OK  •  "
                               f"{t_start} → {t_end}  ({total_dur})")
            else:
                overall = (f"{st['current']} / {st['total']}  •  "
                           f"{done_cnt} / {len(workers)} listos  •  "
                           f"{t_start} → {t_end}")
            msg_children = [
                html.Div(overall, style={"fontSize": "0.73rem", "color": "#9ca3af",
                                         "marginBottom": "4px",
                                         "fontVariantNumeric": "tabular-nums"}),
                html.Div(rows),
            ]
            msg_style = {"minHeight": "16px", "marginBottom": "10px"}
        else:
            _dur = _fmt_dur(st.get("start_time"), st.get("end_time"))
            overall_times = (f"  •  {t_start} → {t_end}" + (f"  ({_dur})" if _dur else "")
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


# ── Exclusión mutua visual: con una operación corriendo, TODOS los botones se
#    deshabilitan (el guard de _start/_start_redownload es la protección real) ──
_RECONCILE_OPS = sorted(_HAS_RECONCILE)


@callback(
    *[Output(f"dc-btn-{_op}", "disabled", allow_duplicate=True) for _op in _OPS],
    *[Output(f"dc-btn-redownload-{_op}", "disabled") for _op in _OPS],
    *[Output(f"dc-btn-reconcile-{_op}", "disabled") for _op in _RECONCILE_OPS],
    *[Input(f"dc-interval-{_op}", "disabled") for _op in _OPS],
    prevent_initial_call="initial_duplicate",
)
def sync_buttons_mutex(*_):
    busy = _any_running()
    return tuple([busy] * (2 * len(_OPS) + len(_RECONCILE_OPS)))

