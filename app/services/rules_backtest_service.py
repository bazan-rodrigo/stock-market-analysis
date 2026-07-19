"""
Backtest nivel B (Reglas): fan-out del simulador de trades sobre TODO el
universo de la estrategia.

Corre `trade_simulator.simulate_trades` por activo (con una spec de reglas de
entrada/salida) y agrega con `portfolio_metrics`: distribución por activo,
desglose de salidas por motivo y ranking. Reusa `load_series` (gate de precio
propio) y el patrón de enumeración del universo de `backtest_service`.

Responde "¿qué tan buenas son estas reglas EN PROMEDIO sobre el universo?", a
diferencia del nivel A (poder predictivo del ranking) y del nivel C (cartera).

Primera versión ON-DEMAND (sin persistir). La persistencia (tabla hija de
backtest_run) y el recorte por fecha son pasos posteriores; el loteo de precios
(como backtest_service, _ASSET_BATCH=200) es la optimización pendiente para 10k
activos (hoy load_series consulta por-activo).
"""
from statistics import mean, median

from app.services import portfolio_metrics as pm


def aggregate_rules_results(per_asset):
    """Agrega los resultados por-activo del fan-out (lógica pura, testeable).

    `per_asset`: lista de dicts {asset_id, summary, trades}, donde `summary` es
    lo que devuelve `trade_simulator.summarize_trades` y `trades` la lista de
    `trade_simulator.simulate_trades`.

    Devuelve: conteos del universo, retorno mediano/medio y win rate medio entre
    los activos con trades, desglose global de salidas por motivo, y el ranking
    de activos por retorno total (descendente).
    """
    with_trades = [a for a in per_asset if a["summary"]["n_trades"] > 0]
    total_rets = [a["summary"]["total_ret"] for a in with_trades
                  if a["summary"]["total_ret"] is not None]
    win_rates = [a["summary"]["win_rate"] for a in with_trades
                 if a["summary"]["win_rate"] is not None]
    all_trades = [t for a in per_asset for t in a["trades"]]

    ranking = sorted(
        with_trades,
        key=lambda a: (a["summary"]["total_ret"]
                       if a["summary"]["total_ret"] is not None
                       else float("-inf")),
        reverse=True)

    return {
        "n_assets": len(per_asset),
        "n_with_trades": len(with_trades),
        "total_trades": sum(a["summary"]["n_trades"] for a in per_asset),
        "total_closed": sum(a["summary"]["n_closed"] for a in per_asset),
        "median_total_ret": median(total_rets) if total_rets else None,
        "mean_total_ret": mean(total_rets) if total_rets else None,
        "mean_win_rate": mean(win_rates) if win_rates else None,
        "exit_reasons": pm.exit_reason_breakdown(all_trades),
        "ranking": [{
            "asset_id": a["asset_id"],
            "n_trades": a["summary"]["n_trades"],
            "win_rate": a["summary"]["win_rate"],
            "total_ret": a["summary"]["total_ret"],
            "avg_ret": a["summary"]["avg_ret"],
            "avg_bars": a["summary"]["avg_bars"],
        } for a in ranking],
    }


def run_rules_backtest(strategy_id, spec, *, progress_cb=None):
    """Orquesta el fan-out sobre el universo de la estrategia (toca BD).

    Enumera los activos con score en strat_res_{id}, corre el simulador por
    activo con `spec` y agrega. Devuelve el dict de `aggregate_rules_results`.
    """
    import sqlalchemy as sa

    from app.database import get_session
    from app.models import signal_store
    from app.services.trade_optimizer import load_series
    from app.services.trade_simulator import simulate_trades, summarize_trades

    s = get_session()
    rt = signal_store.ensure_strat_table(strategy_id, bind=s.connection())
    asset_ids = sorted(r[0] for r in s.execute(
        sa.select(rt.c.asset_id).where(rt.c.score.isnot(None)).distinct()).all())
    if not asset_ids:
        raise ValueError(
            "La estrategia no tiene historia calculada. Corré 'Recalcular "
            "completo' en Centro de Datos → Señales y Estrategias.")

    per_asset = []
    for i, aid in enumerate(asset_ids):
        closes, scores, pcts = load_series(aid, strategy_id)
        trades = simulate_trades(closes, scores, spec, percentiles=pcts)
        per_asset.append({"asset_id": aid,
                          "summary": summarize_trades(trades),
                          "trades": trades})
        if progress_cb:
            progress_cb(i + 1, len(asset_ids), "activos")

    return aggregate_rules_results(per_asset)
