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
propias); el loteo de precios (como backtest_service, _ASSET_BATCH=200) es la
optimización pendiente para 10k activos.
"""


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
    all_dates = sorted({d for a in per_asset.values() for d in a["dates"]})
    pos = {d: i for i, d in enumerate(all_dates)}
    scores_by_date, rets_by_date, eligible_by_date = {}, {}, {}
    for aid, data in per_asset.items():
        dts, closes, scores = data["dates"], data["closes"], data["scores"]
        if not dts:
            continue
        inpos = data.get("in_position", set())
        own = {d: k for k, d in enumerate(dts)}
        last_score, last_elig, prev_close = None, False, None
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
                last_elig = k in inpos
            elif last_score is not None:           # hueco interior: arrastra score
                scores_by_date.setdefault(d, {})[aid] = last_score
            if last_elig:                          # y elegibilidad (para no evictar)
                eligible_by_date.setdefault(d, set()).add(aid)
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
    from app.models import Price, signal_store
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

    per_asset = {}
    for k, aid in enumerate(asset_ids):
        prows = (s.query(Price.date, Price.close)
                 .filter(Price.asset_id == aid, Price.close.isnot(None))
                 .order_by(Price.date).all())
        if not prows:
            continue
        srows = s.execute(sa.select(rt.c.date, rt.c.score, rt.c.pct)
                          .where(rt.c.asset_id == aid)).all()
        sc = {d: (float(x) if x is not None else None,
                  float(p) if p is not None else None) for d, x, p in srows}
        dates = [d for d, _ in prows]
        closes = [float(c) for _, c in prows]
        scores = [sc.get(d, (None, None))[0] for d in dates]
        pcts = [sc.get(d, (None, None))[1] for d in dates]
        trades = simulate_trades(closes, scores, spec, percentiles=pcts)
        per_asset[aid] = {"dates": dates, "closes": closes, "scores": scores,
                          "in_position": _in_position(trades, len(closes))}
        if progress_cb:
            progress_cb(k + 1, len(asset_ids), "activos")

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
