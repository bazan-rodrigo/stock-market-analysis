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
    - scores_by_date: {fecha: {activo: score}} (solo scores no-None).
    - rets_by_date: {fecha: {activo: retorno}} (cierre-a-cierre en fechas propias).
    - eligible_by_date: {fecha: set(activo)} (in_position mapeado a fechas).
    """
    all_dates = sorted({d for a in per_asset.values() for d in a["dates"]})
    scores_by_date, rets_by_date, eligible_by_date = {}, {}, {}
    for aid, data in per_asset.items():
        dts, closes, scores = data["dates"], data["closes"], data["scores"]
        inpos = data.get("in_position", set())
        for i, d in enumerate(dts):
            if scores[i] is not None:
                scores_by_date.setdefault(d, {})[aid] = scores[i]
            if i > 0 and closes[i - 1]:
                rets_by_date.setdefault(d, {})[aid] = closes[i] / closes[i - 1] - 1.0
            if i in inpos:
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
