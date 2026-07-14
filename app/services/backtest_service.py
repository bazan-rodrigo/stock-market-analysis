"""
Orquestación del backtest por deciles: carga de datos (con gate de precio
propio), ejecución del motor puro (backtest_engine) y persistencia del run.

GATE DE LECTURA: un score de strategy_result entra al análisis SOLO si el
activo tiene precio propio en esa fecha exacta. Los scores "arrastrados" por
la lectura as-of del pipeline (activo que no cotizó ese día) quedan afuera —
misma semántica que la alternativa A de docs/notes/design_scores_dias_sin_precio.md,
aplicada acá al leer: si algún día se implementa en el pipeline, este filtro
se vuelve redundante sin cambiar los resultados.

Un run es un SNAPSHOT: config JSON + resultados persistidos. La historia de
strategy_result se reescribe con cada "Recalcular completo", así que un run
nunca se recalcula — se corre uno nuevo y se comparan.
"""
import json
import logging
import time
from collections import defaultdict

from app.database import get_session
from app.models import (BacktestIcPoint, BacktestQuantileStat, BacktestRun,
                        Price, StrategyResult)
from app.services import backtest_engine as eng

logger = logging.getLogger(__name__)

DEFAULT_CONFIG = {
    "horizons":    [1, 5, 20, 60],  # ruedas propias
    "lag":         1,               # ejecución al cierre siguiente (sin look-ahead)
    "n_quantiles": 10,
    "min_assets":  20,              # mínimo de observaciones por fecha
    "date_from":   None,            # ISO o None
    "date_to":     None,
}

_ASSET_BATCH = 200  # activos por query de precios (acota memoria a 10k activos)


def normalize_config(config) -> dict:
    """Defaults + validación. Levanta ValueError con mensaje para la UI."""
    cfg = {**DEFAULT_CONFIG, **(config or {})}
    horizons = sorted({int(h) for h in cfg["horizons"] if int(h) > 0})
    if not horizons:
        raise ValueError("Al menos un horizonte (> 0 ruedas).")
    cfg["horizons"] = horizons
    cfg["lag"] = max(0, int(cfg["lag"]))
    cfg["n_quantiles"] = int(cfg["n_quantiles"])
    if not 2 <= cfg["n_quantiles"] <= 20:
        raise ValueError("Cuantiles: entre 2 y 20.")
    cfg["min_assets"] = max(int(cfg["min_assets"]), cfg["n_quantiles"])
    return cfg


def run_backtest(strategy_id: int, config=None, owner_id=None,
                 progress_cb=None) -> int:
    """Ejecuta un backtest completo y lo persiste. Devuelve el run_id.

    Ante error deja el run con status='error' + mensaje y relanza (el caller
    en thread decide cómo mostrarlo). progress_cb(cur, tot, fase).
    """
    cfg = normalize_config(config)
    s = get_session()
    run = BacktestRun(strategy_id=int(strategy_id), owner_id=owner_id,
                      config=json.dumps(cfg), status="running")
    s.add(run)
    s.commit()
    run_id = run.id
    t0 = time.time()
    try:
        _execute(s, run_id, int(strategy_id), cfg, progress_cb)
    except Exception as exc:
        s.rollback()
        run = s.get(BacktestRun, run_id)
        run.status = "error"
        run.error = str(exc)[:2000]
        run.duration_seconds = time.time() - t0
        s.commit()
        raise
    run = s.get(BacktestRun, run_id)
    run.duration_seconds = time.time() - t0
    s.commit()
    return run_id


def _chunks(lst, n):
    for i in range(0, len(lst), n):
        yield lst[i:i + n]


def _execute(s, run_id, strategy_id, cfg, progress_cb):
    horizons = cfg["horizons"]

    # ── Scores de la estrategia ───────────────────────────────────────────
    q = (s.query(StrategyResult.date, StrategyResult.asset_id,
                 StrategyResult.score)
         .filter(StrategyResult.strategy_id == strategy_id,
                 StrategyResult.score.isnot(None)))
    if cfg["date_from"]:
        q = q.filter(StrategyResult.date >= cfg["date_from"])
    if cfg["date_to"]:
        q = q.filter(StrategyResult.date <= cfg["date_to"])
    score_rows = q.all()
    if not score_rows:
        raise ValueError(
            "La estrategia no tiene historia calculada en el período. "
            "Correr «Recalcular completo» en Centro de Datos → Señales y "
            "Estrategias.")

    scores_by_asset = defaultdict(list)
    for d, aid, sc in score_rows:
        scores_by_asset[aid].append((d, float(sc)))
    asset_ids = sorted(scores_by_asset)

    # ── Precios por lote + gate + retornos forward ────────────────────────
    # per_date[D] = [(score, {h: ret|None}), ...] — solo pares (activo, D)
    # donde el activo tiene precio PROPIO en D (gate).
    per_date = defaultdict(list)
    done = 0
    for batch in _chunks(asset_ids, _ASSET_BATCH):
        price_rows = (s.query(Price.asset_id, Price.date, Price.close)
                      .filter(Price.asset_id.in_(batch),
                              Price.close.isnot(None))
                      .order_by(Price.asset_id, Price.date)
                      .all())
        prices_by_asset = defaultdict(list)
        for aid, d, c in price_rows:
            prices_by_asset[aid].append((d, float(c)))

        for aid in batch:
            series = prices_by_asset.get(aid)
            if not series:
                continue
            closes = [c for _, c in series]
            pos = {d: i for i, (d, _) in enumerate(series)}
            fwd = eng.forward_returns_for_series(closes, horizons, cfg["lag"])
            for d, sc in scores_by_asset[aid]:
                i = pos.get(d)
                if i is None:
                    continue  # GATE: sin precio propio en D → afuera
                per_date[d].append((sc, fwd[i]))
        done += len(batch)
        if progress_cb:
            progress_cb(done, len(asset_ids), "activos")

    # ── Cross-sections por fecha × horizonte ──────────────────────────────
    all_dates = sorted(per_date)
    sections_by_h = {h: [] for h in horizons}
    ic_rows = []
    for j, d in enumerate(all_dates):
        entries = per_date[d]
        for h in horizons:
            pairs = [(sc, fr[h]) for sc, fr in entries if fr[h] is not None]
            cs = eng.date_cross_section(pairs, cfg["n_quantiles"],
                                        cfg["min_assets"])
            if cs is None:
                continue
            sections_by_h[h].append(cs)
            ic_rows.append(BacktestIcPoint(
                run_id=run_id, date=d, horizon=h,
                ic=cs["ic"], spread=cs["spread"], n_assets=cs["n"]))
        if progress_cb and (j % 100 == 0 or j == len(all_dates) - 1):
            progress_cb(j + 1, len(all_dates), "fechas")

    # ── Agregados + persistencia ──────────────────────────────────────────
    stat_rows = []
    for h in horizons:
        agg = eng.aggregate_cross_sections(sections_by_h[h])
        if agg is None:
            continue
        for qd in agg["quantiles"]:
            stat_rows.append(BacktestQuantileStat(
                run_id=run_id, horizon=h, quantile=qd["quantile"],
                n_dates=qd["n_dates"], mean_ret=qd["mean_ret"],
                median_ret=qd["median_ret"], pct_pos=qd["pct_pos"]))
    if not stat_rows:
        raise ValueError(
            "Ninguna fecha alcanzó el mínimo de observaciones "
            f"({cfg['min_assets']}). Bajá el mínimo o revisá la historia.")

    s.add_all(ic_rows)
    s.add_all(stat_rows)
    computed = sorted({r.date for r in ic_rows})
    run = s.get(BacktestRun, run_id)
    run.status = "done"
    run.date_from, run.date_to = computed[0], computed[-1]
    run.n_dates = len(computed)
    s.commit()
    logger.info("Backtest run %s: %s fechas, %s horizontes",
                run_id, len(computed), len(horizons))


# ── Lectura para la UI ────────────────────────────────────────────────────────

def list_runs(strategy_ids) -> list[BacktestRun]:
    """Runs de las estrategias visibles para el viewer, más reciente primero."""
    if not strategy_ids:
        return []
    s = get_session()
    return (s.query(BacktestRun)
            .filter(BacktestRun.strategy_id.in_(list(strategy_ids)))
            .order_by(BacktestRun.id.desc())
            .limit(50).all())


def get_run_results(run_id: int) -> dict | None:
    """Todo lo que necesita la pantalla de resultados de UN run."""
    s = get_session()
    run = s.get(BacktestRun, run_id)
    if run is None:
        return None
    stats = (s.query(BacktestQuantileStat)
             .filter(BacktestQuantileStat.run_id == run_id)
             .order_by(BacktestQuantileStat.horizon,
                       BacktestQuantileStat.quantile).all())
    points = (s.query(BacktestIcPoint)
              .filter(BacktestIcPoint.run_id == run_id)
              .order_by(BacktestIcPoint.horizon, BacktestIcPoint.date).all())

    ic_summary = {}
    by_h = defaultdict(list)
    for p in points:
        if p.ic is not None:
            by_h[p.horizon].append(p.ic)
    for h, ics in by_h.items():
        n = len(ics)
        mean = sum(ics) / n
        std = t = None
        if n > 1:
            var = sum((x - mean) ** 2 for x in ics) / (n - 1)
            std = var ** 0.5
            if std > 0:
                t = mean / std * (n ** 0.5)
        ic_summary[h] = {"mean": mean, "std": std, "t": t, "n": n,
                         "pct_pos": sum(1 for x in ics if x > 0) / n}

    return {
        "run": run,
        "config": json.loads(run.config),
        "quantile_stats": stats,
        "ic_points": points,
        "ic_summary": ic_summary,
    }
