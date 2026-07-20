"""
Orquestación del backtest de cartera (nivel C).

Arma el cross-section del universo (scores de `strat_res_{id}` + retornos de
precios), computa la elegibilidad por-activo corriendo `trade_simulator`, y corre
los dos sub-modos (`simulate_topn` ranking-puro y `simulate_gated`) más el
benchmark EW, con los KPIs de `portfolio_metrics`.

Decomposición:
- `_in_position` y `build_panels` son PUROS (testeados): mapean trades → barras
  en posición y ensamblan los paneles {fecha: {activo: …}} que consumen los
  motores.
- `run_portfolio_backtest` toca BD (enumera universo, carga precios/scores, corre
  el simulador por activo) — se verifica en el Codespace. La persistencia y la UI
  (pestaña Cartera en /backtest) son pasos posteriores.

Simplificaciones de la v1 (documentadas): el retorno de un activo en una fecha
del calendario común donde ese activo no cotizó se toma como 0 (gate a fechas
propias). La carga de precios/scores es BATCHEADA (`_load_raw`, IN por lotes de
_ASSET_BATCH, como backtest_service) para acotar round-trips a escala 10k — la
comparten nivel C (`run_portfolio_backtest`) y el walk-forward (`_load_universe`).
"""

_ASSET_BATCH = 200   # activos por query (acota round-trips/memoria a 10k)


def _chunks(seq, n):
    for i in range(0, len(seq), n):
        yield seq[i:i + n]


def _in_position(trades, n_bars):
    """Índices de barra en posición según los trades del simulador.

    Un trade entra en `entry_idx` (comprado al cierre) y sale en `exit_idx`
    (vendido a ese cierre): se cuenta EN POSICIÓN en [entry_idx, exit_idx-1] (al
    cierre de exit_idx ya está flat). Un trade abierto (exit_idx None) llega
    hasta la última barra. Así el retorno que capta la cartera al mantener el
    activo en esas fechas replica el retorno del trade por-activo.
    """
    out = set()
    for t in trades:
        ei = t.get("entry_idx")
        if ei is None:
            continue
        xi = t.get("exit_idx")
        end = (xi - 1) if xi is not None else (n_bars - 1)
        for j in range(ei, end + 1):
            out.add(j)
    return out


def _score_ret_panels(per_asset):
    """all_dates, scores_by_date, rets_by_date: la parte del cross-section que
    NO depende de in_position (o sea, del trailing). Separada de la
    elegibilidad para poder computarla UNA vez por ventana en el walk-forward y
    reusarla entre trailings. Misma semántica de hueco interior que
    build_panels (arrastra el último score en los huecos)."""
    all_dates = sorted({d for a in per_asset.values() for d in a["dates"]})
    pos = {d: i for i, d in enumerate(all_dates)}
    scores_by_date, rets_by_date = {}, {}
    for aid, data in per_asset.items():
        dts, closes, scores = data["dates"], data["closes"], data["scores"]
        if not dts:
            continue
        own = {d: k for k, d in enumerate(dts)}
        last_score, prev_close = None, None
        for ci in range(pos[dts[0]], pos[dts[-1]] + 1):
            d = all_dates[ci]
            k = own.get(d)
            if k is not None:                      # barra propia del activo
                if prev_close:
                    rets_by_date.setdefault(d, {})[aid] = closes[k] / prev_close - 1.0
                prev_close = closes[k]
                if scores[k] is not None:
                    scores_by_date.setdefault(d, {})[aid] = scores[k]
                    last_score = scores[k]
            elif last_score is not None:           # hueco interior: arrastra score
                scores_by_date.setdefault(d, {})[aid] = last_score
    return all_dates, scores_by_date, rets_by_date


def _eligible_by_date(per_asset, all_dates):
    """eligible_by_date: la parte que SÍ depende de in_position (del trailing).
    Recibe all_dates ya calculado por _score_ret_panels. Misma semántica de
    arrastre que build_panels: la elegibilidad se carga en los huecos hasta la
    próxima barra propia (para no evictar el activo en el hueco)."""
    pos = {d: i for i, d in enumerate(all_dates)}
    eligible_by_date = {}
    for aid, data in per_asset.items():
        dts = data["dates"]
        if not dts:
            continue
        inpos = data.get("in_position", set())
        own = {d: k for k, d in enumerate(dts)}
        last_elig = False
        for ci in range(pos[dts[0]], pos[dts[-1]] + 1):
            d = all_dates[ci]
            k = own.get(d)
            if k is not None:
                last_elig = k in inpos
            if last_elig:
                eligible_by_date.setdefault(d, set()).add(aid)
    return eligible_by_date


def build_panels(per_asset):
    """Ensambla el cross-section para los motores (lógica pura).

    `per_asset`: {asset_id: {"dates": [...], "closes": [...], "scores": [...],
    "in_position": set(indices)}} — series alineadas a las barras PROPIAS del
    activo. Devuelve (all_dates, scores_by_date, rets_by_date, eligible_by_date):
    - all_dates: unión ordenada de todas las fechas (calendario común).
    - scores_by_date: {fecha: {activo: score}} (score no-None).
    - rets_by_date: {fecha: {activo: retorno}} (cierre-a-cierre entre barras
      propias; el retorno que cruza un hueco se registra en la barra de
      reanudación).
    - eligible_by_date: {fecha: set(activo)}.

    HUECOS INTERIORES: si un activo no cotiza en una fecha del calendario común
    (existe porque OTRO activo cotizó) DENTRO de su rango [primera, última barra
    propia], se ARRASTRA su último score y su elegibilidad a esa fecha. Así el
    motor no lo evicta en el hueco y el retorno que cruza el hueco se acredita
    con el activo aún en cartera (si no, se perdía y se pagaba turnover fantasma;
    ver revisión nivel C). En universos de un solo mercado, día-completos, no hay
    huecos y el comportamiento es el directo.
    """
    all_dates, scores_by_date, rets_by_date = _score_ret_panels(per_asset)
    eligible_by_date = _eligible_by_date(per_asset, all_dates)
    return all_dates, scores_by_date, rets_by_date, eligible_by_date


def run_portfolio_backtest(strategy_id, spec, *, top_n, rebalance_every=1,
                           cost_bps=0.0, progress_cb=None):
    """Corre el backtest de cartera (nivel C) sobre el universo de la estrategia.

    Devuelve {'dates', 'ranking', 'gated', 'benchmark_ew'}, donde cada sub-modo
    trae {'equity': [...], **métricas de portfolio_metrics.summary}. `spec` son
    las reglas del simulador (para la elegibilidad del sub-modo gated).
    """
    import sqlalchemy as sa

    from app.database import get_session
    from app.models import signal_store
    from app.services import portfolio_metrics as pm
    from app.services import portfolio_sim_engine as eng
    from app.services.trade_simulator import simulate_trades

    s = get_session()
    rt = signal_store.ensure_strat_table(strategy_id, bind=s.connection())
    asset_ids = sorted(r[0] for r in s.execute(
        sa.select(rt.c.asset_id).where(rt.c.score.isnot(None)).distinct()).all())
    if not asset_ids:
        raise ValueError(
            "La estrategia no tiene historia calculada. Corré 'Recalcular "
            "completo' en Centro de Datos → Señales y Estrategias.")

    raw = _load_raw(s, rt, asset_ids, progress_cb=progress_cb)
    per_asset = {}
    for aid, r in raw.items():
        trades = simulate_trades(r["closes"], r["scores"], spec,
                                 percentiles=r["pcts"])
        per_asset[aid] = {"dates": r["dates"], "closes": r["closes"],
                          "scores": r["scores"],
                          "in_position": _in_position(trades, len(r["closes"]))}

    dates, scores_by_date, rets_by_date, eligible_by_date = build_panels(per_asset)

    ranking = eng.simulate_topn(dates, scores_by_date, rets_by_date,
                                top_n=top_n, rebalance_every=rebalance_every,
                                cost_bps=cost_bps)
    gated = eng.simulate_gated(dates, scores_by_date, eligible_by_date,
                               rets_by_date, top_n=top_n,
                               rebalance_every=rebalance_every, cost_bps=cost_bps)
    bench = eng.simulate_topn(dates, scores_by_date, rets_by_date,
                              top_n=10 ** 9, rebalance_every=rebalance_every,
                              cost_bps=0.0)

    def _pack(res):
        return {"equity": res["equity"],
                **pm.summary(res["equity"], dates=dates)}

    return {"dates": dates, "ranking": _pack(ranking), "gated": _pack(gated),
            "benchmark_ew": _pack(bench)}


def curated_equity_series(session, portfolio_id):
    """Equity de una cartera teórica CURADA: constant-mix de sus miembros
    (rebalanceo diario a los pesos objetivo). Devuelve {'dates','equity', **KPIs}
    o None si no hay miembros con precios. Es sincrónica (pocos miembros)."""
    from app.models import Price
    from app.services import portfolio_metrics as pm
    from app.services import portfolio_sim_engine as eng
    from app.services.portfolio_service import resolve_membership

    members = resolve_membership(session, portfolio_id)
    if not members:
        return None
    target = {aid: w for aid, w in members}
    per_asset = {}
    for aid in target:
        prows = (session.query(Price.date, Price.close)
                 .filter(Price.asset_id == aid, Price.close.isnot(None))
                 .order_by(Price.date).all())
        if not prows:
            continue
        per_asset[aid] = {"dates": [d for d, _ in prows],
                          "closes": [float(c) for _, c in prows],
                          "scores": [None] * len(prows), "in_position": set()}
    if not per_asset:
        return None
    dates, _sc, rets, _el = build_panels(per_asset)
    res = eng.simulate_fixed_weights(dates, target, rets, rebalance_every=1)
    return {"dates": dates, "equity": res["equity"],
            **pm.summary(res["equity"], dates=dates)}


# ── Persistencia de corridas (nivel D — comparar) ─────────────────────────────

_SUBMODES = (("gated", "gated"), ("ranking", "ranking"),
             ("benchmark", "benchmark_ew"))


def save_portfolio_run(session, owner_id, strategy_id, name, config, result):
    """Persiste una corrida de cartera (result de run_portfolio_backtest) como
    snapshot inmutable: portfolio_run (config + KPIs) + puntos de equity por
    sub-modo. Devuelve el PortfolioRun."""
    import json

    from app.models import PortfolioRun, PortfolioRunPoint

    def _kpis(d):
        return {k: d.get(k) for k in ("total_return", "cagr", "sharpe",
                                      "sortino", "max_drawdown", "volatility")}
    summary = {sm: _kpis(result[key]) for sm, key in _SUBMODES}
    run = PortfolioRun(owner_id=owner_id, strategy_id=strategy_id, name=name,
                       config=json.dumps(config), summary=json.dumps(summary))
    session.add(run)
    session.flush()
    dates = result["dates"]
    points = [{"run_id": run.id, "submode": sm, "date": d, "value": v}
              for sm, key in _SUBMODES
              for d, v in zip(dates, result[key]["equity"])]
    if points:
        session.bulk_insert_mappings(PortfolioRunPoint, points)
    session.commit()
    return run


def list_portfolio_runs(session, user_id, is_admin, limit=50):
    """Corridas guardadas visibles (propias; admin: todas), más reciente primero."""
    from app.models import PortfolioRun
    q = session.query(PortfolioRun)
    if not is_admin:
        q = q.filter(PortfolioRun.owner_id == user_id)
    return q.order_by(PortfolioRun.created_at.desc()).limit(limit).all()


def get_portfolio_run(session, run_id):
    """Reconstruye una corrida: {'run', 'config', 'summary', 'series'} donde
    series = {submode: {'dates': [...], 'equity': [...]}}. None si no existe."""
    import json

    from app.models import PortfolioRun, PortfolioRunPoint
    run = session.get(PortfolioRun, run_id)
    if run is None:
        return None
    series = {}
    for p in (session.query(PortfolioRunPoint)
              .filter(PortfolioRunPoint.run_id == run_id)
              .order_by(PortfolioRunPoint.date).all()):
        sm = series.setdefault(p.submode, {"dates": [], "equity": []})
        sm["dates"].append(p.date)
        sm["equity"].append(p.value)
    return {"run": run, "config": json.loads(run.config or "{}"),
            "summary": json.loads(run.summary or "{}"), "series": series}


# ── Walk-forward (optimización robusta out-of-sample) ─────────────────────────

def _window_splits(n, n_windows):
    """Ventanas train/test anclado-expansivo: n_windows tramos de test
    consecutivos al final; el train de cada uno va desde el inicio. Devuelve
    tuplas de índices (train_lo, train_hi, test_lo, test_hi). [] si no alcanza."""
    if n_windows < 1 or n < n_windows + 1:
        return []
    seg = n // (n_windows + 1)
    if seg < 1:
        return []
    out = []
    for w in range(n_windows):
        te_lo = (w + 1) * seg
        te_hi = (w + 2) * seg - 1 if w < n_windows - 1 else n - 1
        out.append((0, te_lo - 1, te_lo, te_hi))
    return out


def _spec_with_trailing(base_spec, trailing_pct):
    """Copia de la spec con el trailing_stop fijado (reemplaza el existente)."""
    caps = [c for c in base_spec.get("caps", []) if c["type"] != "trailing_stop"]
    caps = caps + [{"type": "trailing_stop", "pct": trailing_pct}]
    return {**base_spec, "caps": caps}


def _range_slice(per_asset_raw, date_from, date_to):
    """Recorta el universo a [date_from, date_to] por activo (excluye los que no
    tienen barras propias en el rango). Es la parte NO dependiente del trailing,
    para computarla una vez por ventana en el walk-forward.
    {aid: {dates, closes, scores, pcts}}."""
    base = {}
    for aid, raw in per_asset_raw.items():
        idxs = [i for i, d in enumerate(raw["dates"])
                if date_from <= d <= date_to]
        if not idxs:
            continue
        base[aid] = {
            "dates":  [raw["dates"][i]  for i in idxs],
            "closes": [raw["closes"][i] for i in idxs],
            "scores": [raw["scores"][i] for i in idxs],
            "pcts":   [raw["pcts"][i]   for i in idxs],
        }
    return base


def _eligible_for_spec(base, spec, all_dates):
    """eligible_by_date de un universo YA recortado (`base`) bajo `spec`. Los
    trades arrancan FRESCOS en el rango. Es la ÚNICA parte del panel que depende
    del trailing → en el walk-forward se recomputa por trailing mientras el
    resto (dates/scores/rets) se reusa."""
    from app.services.trade_simulator import simulate_trades
    per_asset = {}
    for aid, r in base.items():
        trades = simulate_trades(r["closes"], r["scores"], spec,
                                 percentiles=r["pcts"])
        per_asset[aid] = {"dates": r["dates"],
                          "in_position": _in_position(trades, len(r["closes"]))}
    return _eligible_by_date(per_asset, all_dates)


def _panels_for_range(per_asset_raw, spec, date_from, date_to):
    """Panels (dates, scores, rets, eligible) de la cartera sobre [date_from,
    date_to]. Los trades arrancan FRESCOS en el rango (sin carryover del train).
    La elegibilidad depende de la spec (entrada + trailing), NO de top_n → en el
    walk-forward se calcula una vez por trailing y se reusa para todos los
    top_n. `per_asset_raw`: {aid: {dates, closes, scores, pcts}}."""
    base = _range_slice(per_asset_raw, date_from, date_to)
    all_dates, scores_bd, rets_bd = _score_ret_panels(base)
    elig_bd = _eligible_for_spec(base, spec, all_dates)
    return all_dates, scores_bd, rets_bd, elig_bd


def _gated_equity_range(per_asset_raw, spec, top_n, date_from, date_to, *,
                        rebalance_every=1, cost_bps=0.0):
    """Equity gated de la cartera sobre [date_from, date_to] (arranque fresco →
    correcto para OOS). Reusa el motor."""
    from app.services import portfolio_sim_engine as eng
    dates, scores_bd, rets_bd, elig_bd = _panels_for_range(
        per_asset_raw, spec, date_from, date_to)
    res = eng.simulate_gated(dates, scores_bd, elig_bd, rets_bd, top_n=top_n,
                             rebalance_every=rebalance_every, cost_bps=cost_bps)
    return dates, res["equity"]


def _span_cagr(equity, dates):
    """CAGR sobre el período REAL de la ventana. Permite comparar train (expansivo)
    vs test (un tramo) de forma justa — los retornos totales crudos no son
    comparables porque cubren largos distintos."""
    from app.services import portfolio_metrics as pm
    if not equity or not dates or len(dates) < 2:
        return None
    days = (dates[-1] - dates[0]).days
    years = days / 365.25 if days > 0 else None
    return pm.cagr(equity, years)


def _wf_score(equity):
    """Métrica de selección de config en el train: Sharpe (risk-adjusted). Premia
    consistencia, no sólo retorno crudo — que favorece la config más suelta que
    montó la mayor tendencia, sin mirar el riesgo. Equity vacía/degenerada (o vol
    cero → Sharpe indefinido) → -inf (nunca elegida)."""
    from app.services import portfolio_metrics as pm
    if not equity or len(equity) < 2:
        return float("-inf")
    sh = pm.sharpe(pm.returns_from_equity(equity), 0.0, pm.TRADING_DAYS)
    return sh if sh is not None else float("-inf")


def _load_raw(session, rt, asset_ids, progress_cb=None):
    """{aid: {dates, closes, scores, pcts}} para `asset_ids`, con carga BATCHEADA:
    un par de queries por LOTE (IN de _ASSET_BATCH) — precios de `prices` + scores
    de la tabla de estrategia `rt` — en vez de dos queries por activo (evita el
    N+1 a escala 10k). Lo comparten nivel C y el walk-forward."""
    import sqlalchemy as sa
    from collections import defaultdict

    from app.models import Price
    per_asset = {}
    done = 0
    for batch in _chunks(asset_ids, _ASSET_BATCH):
        prows = (session.query(Price.asset_id, Price.date, Price.close)
                 .filter(Price.asset_id.in_(batch), Price.close.isnot(None))
                 .order_by(Price.asset_id, Price.date).all())
        prices = defaultdict(list)
        for aid, d, c in prows:
            prices[aid].append((d, float(c)))
        srows = session.execute(
            sa.select(rt.c.asset_id, rt.c.date, rt.c.score, rt.c.pct)
            .where(rt.c.asset_id.in_(batch))).all()
        scmap = defaultdict(dict)
        for aid, d, x, p in srows:
            scmap[aid][d] = (float(x) if x is not None else None,
                             float(p) if p is not None else None)
        for aid in batch:
            series = prices.get(aid)
            if not series:
                continue
            dates = [d for d, _ in series]
            sc = scmap.get(aid, {})
            per_asset[aid] = {
                "dates": dates,
                "closes": [c for _, c in series],
                "scores": [sc.get(d, (None, None))[0] for d in dates],
                "pcts": [sc.get(d, (None, None))[1] for d in dates]}
        done += len(batch)
        if progress_cb:
            progress_cb(done, len(asset_ids), "activos")
    return per_asset


def _load_universe(session, strategy_id):
    """{aid: {dates, closes, scores, pcts}} para todo el universo de la
    estrategia (activos con score). Se carga UNA vez y se reusa por ventana."""
    import sqlalchemy as sa

    from app.models import signal_store
    rt = signal_store.ensure_strat_table(strategy_id, bind=session.connection())
    asset_ids = sorted(r[0] for r in session.execute(
        sa.select(rt.c.asset_id).where(rt.c.score.isnot(None)).distinct()).all())
    return _load_raw(session, rt, asset_ids)


_WF_MIN_SEG_BARS = 10   # cada tramo (train inicial / test) necesita ≥ esto


def walk_forward(session, strategy_id, base_spec, *, topn_grid=(10, 20, 30),
                 trail_grid=(10.0, 15.0, 20.0), n_windows=4, rebalance_every=1,
                 cost_bps=0.0, progress_cb=None):
    """Walk-forward de OPTIMIZACIÓN. En cada ventana train busca la mejor
    (top_n, trailing) por Sharpe (risk-adjusted) del gated, la aplica en el test
    (out-of-sample, fresco) y concatena los tests → curva OOS. Cada ventana
    reporta CAGR de train y test (comparables entre sí pese al largo distinto).
    Devuelve {oos_dates, oos_equity, windows, **KPIs de portfolio_metrics}.

    NOTA: en cada costura la cartera se re-arma desde plano (el test arranca sin
    posiciones del train) — sesgo conservador (no cobra el retorno de la rueda de
    costura y paga entrada), nunca look-ahead."""
    from app.services import portfolio_metrics as pm
    from app.services import portfolio_sim_engine as eng

    per_asset_raw = _load_universe(session, strategy_id)
    # Única fase con BD: cierro la transacción de lectura para liberar el
    # read-view y devolver la conexión al pool durante el cómputo puro (CLAUDE.md:
    # presión de undo/purge de una transacción ociosa larga en MariaDB).
    session.rollback()
    if not per_asset_raw:
        raise ValueError("La estrategia no tiene historia calculada. Corré "
                         "'Recalcular completo' en Centro de Datos.")
    all_dates = sorted({d for raw in per_asset_raw.values()
                        for d in raw["dates"]})
    splits = _window_splits(len(all_dates), n_windows)
    if not splits:
        raise ValueError("Historia insuficiente para el walk-forward.")
    if (splits[0][1] - splits[0][0] + 1) < _WF_MIN_SEG_BARS:
        raise ValueError(
            f"Historia insuficiente para {n_windows} ventanas (cada tramo "
            f"quedaría con < {_WF_MIN_SEG_BARS} ruedas). Reducí las ventanas.")

    oos_dates, oos_equity, windows = [], [], []
    val = 1.0
    for w, (tr_lo, tr_hi, te_lo, te_hi) in enumerate(splits):
        tr_from, tr_to = all_dates[tr_lo], all_dates[tr_hi]
        te_from, te_to = all_dates[te_lo], all_dates[te_hi]
        # dates/scores/rets NO dependen del trailing → se arman UNA vez por
        # ventana (antes _panels_for_range los rearmaba por trailing = 3x, y son
        # el costo dominante del build). Sólo la elegibilidad (simulate_trades)
        # se recomputa por trailing. top_n se varía con simulate_gated (barato).
        base = _range_slice(per_asset_raw, tr_from, tr_to)
        dts, scores_bd, rets_bd = _score_ret_panels(base)
        best = None   # (obj, top_n, trailing, train_eq, train_dates)
        for trail in trail_grid:
            spec = _spec_with_trailing(base_spec, trail)
            elig_bd = _eligible_for_spec(base, spec, dts)
            for tn in topn_grid:
                res = eng.simulate_gated(
                    dts, scores_bd, elig_bd, rets_bd, top_n=tn,
                    rebalance_every=rebalance_every, cost_bps=cost_bps)
                eq = res["equity"]
                obj = _wf_score(eq)          # Sharpe del train (risk-adjusted)
                if best is None or obj > best[0]:
                    best = (obj, tn, trail, eq, dts)
        _obj, tn, trail, tr_eq, tr_dts = best
        spec = _spec_with_trailing(base_spec, trail)
        td, teq = _gated_equity_range(per_asset_raw, spec, tn, te_from, te_to,
                                      rebalance_every=rebalance_every,
                                      cost_bps=cost_bps)
        for d, e in zip(td, teq):
            oos_dates.append(d)
            oos_equity.append(val * e)
        if teq:
            val = val * teq[-1]
        windows.append({"train": [tr_from, tr_to], "test": [te_from, te_to],
                        "top_n": tn, "trailing": trail,
                        "train_sharpe": best[0] if best[0] != float("-inf") else None,
                        "train_ret": (tr_eq[-1] - 1.0) if tr_eq else None,
                        "test_ret": (teq[-1] - 1.0) if teq else None,
                        "train_cagr": _span_cagr(tr_eq, tr_dts),
                        "test_cagr": _span_cagr(teq, td)})
        if progress_cb:
            progress_cb(w + 1, len(splits), "ventanas")

    return {"oos_dates": oos_dates, "oos_equity": oos_equity,
            "windows": windows, **pm.summary(oos_equity, dates=oos_dates)}
