"""
Motor de simulación de cartera (backtest nivel C) — lógica pura, sin BD.

Sub-modo 'ranking puro': en cada rebalanceo se mantiene el top-N por score,
equal-weight, y se opera hacia adelante. El sub-modo 'gated' (con reglas de
entrada/salida del simulador), la orquestación (carga de datos, benchmark,
persistencia) y la UI se agregan en pasos posteriores; las métricas de la curva
(CAGR/Sharpe/drawdown/…) salen de `portfolio_metrics`.

Semántica SIN look-ahead: la cartera se forma con los scores al cierre de la
fecha D y su PRIMER retorno es el de D+1 (se rebalancea DESPUÉS de acreditar el
retorno del día con los pesos vigentes). Los costos (bps por lado) se descuentan
sobre el turnover one-way (0.5·Σ|Δw|) en cada rebalanceo.
"""


def topn_weights(scores, top_n):
    """Pesos equal-weight del top-N por score (descendente). {} si no hay scores.

    Empates: se resuelven por el orden estable de `sorted` (por score desc; ante
    igualdad, el orden de iteración del dict de entrada).
    """
    ranked = sorted(scores.items(), key=lambda kv: kv[1], reverse=True)[:top_n]
    if not ranked:
        return {}
    w = 1.0 / len(ranked)
    return {aid: w for aid, _ in ranked}


def simulate_topn(dates, scores, rets, *, top_n, rebalance_every=1,
                  cost_bps=0.0):
    """Simula la cartera top-N por score, equal-weight (sub-modo 'ranking puro').

    - `dates`: lista ordenada de fechas del calendario común.
    - `scores`: {fecha: {asset_id: score}} — scores al cierre de esa fecha.
    - `rets`: {fecha: {asset_id: retorno}} — retorno cierre-a-cierre del activo
      EN esa fecha (el que gana quien lo tenía entrando a la fecha).
    - `top_n`: tamaño de la cartera.
    - `rebalance_every`: cada cuántas fechas se rebalancea (1 = todos los días).
    - `cost_bps`: costo por lado, en puntos básicos, sobre el turnover.

    Devuelve {'dates', 'equity', 'weights', 'turnover'} (listas paralelas a
    `dates`). `equity` arranca en 1.0 (indexar ×100 en la UI). Alimentar
    `portfolio_metrics.summary(equity, dates=dates)` para los KPIs.
    """
    equity, weights_hist, turnovers = [], [], []
    w, val = {}, 1.0
    for i, d in enumerate(dates):
        day_rets = rets.get(d, {})
        # 1) acreditar el retorno del día con los pesos vigentes
        r = sum(wi * day_rets.get(a, 0.0) for a, wi in w.items())
        val *= (1.0 + r)
        # 2) rebalanceo al cierre (los nuevos pesos ganan recién D+1)
        to = 0.0
        if i % rebalance_every == 0:
            new_w = topn_weights(scores.get(d, {}), top_n)
            to = 0.5 * sum(abs(new_w.get(a, 0.0) - w.get(a, 0.0))
                           for a in set(new_w) | set(w))
            val *= (1.0 - cost_bps / 10000.0 * to)
            w = new_w
        equity.append(val)
        weights_hist.append(dict(w))
        turnovers.append(to)
    return {"dates": list(dates), "equity": equity,
            "weights": weights_hist, "turnover": turnovers}


def simulate_gated(dates, scores, eligible, rets, *, top_n, rebalance_every=1,
                   cost_bps=0.0):
    """Sub-modo 'gated': mantiene los del top-N por score QUE ADEMÁS son elegibles.

    `eligible`: {fecha: set(asset_id)} — activos "en posición" según las reglas
    por-activo del simulador (su regla de entrada disparó y ninguna de salida
    cerró todavía). En la orquestación sale de correr `trade_simulator` por
    activo; acá se recibe precomputado para mantener el motor PURO y no
    reimplementar el contrato homologado.

    held(D) = top_N(scores[D]) ∩ eligible[D]  → entra si la regla lo tiene en
    posición Y está en el top-N; sale cuando la regla lo cierra (deja de ser
    elegible) O cae del corte del top-N. Equal-weight entre los held (puede ser
    < N si algunos del top-N no son elegibles). Resto igual que `simulate_topn`
    (sin look-ahead, costos sobre turnover).

    Mismo formato de salida que `simulate_topn`.
    """
    equity, weights_hist, turnovers = [], [], []
    w, val = {}, 1.0
    for i, d in enumerate(dates):
        day_rets = rets.get(d, {})
        r = sum(wi * day_rets.get(a, 0.0) for a, wi in w.items())
        val *= (1.0 + r)
        to = 0.0
        if i % rebalance_every == 0:
            topset = set(topn_weights(scores.get(d, {}), top_n))
            held = sorted(topset & eligible.get(d, set()))
            nw = (1.0 / len(held)) if held else 0.0
            new_w = {a: nw for a in held}
            to = 0.5 * sum(abs(new_w.get(a, 0.0) - w.get(a, 0.0))
                           for a in set(new_w) | set(w))
            val *= (1.0 - cost_bps / 10000.0 * to)
            w = new_w
        equity.append(val)
        weights_hist.append(dict(w))
        turnovers.append(to)
    return {"dates": list(dates), "equity": equity,
            "weights": weights_hist, "turnover": turnovers}
