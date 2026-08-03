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

import sqlalchemy as sa

from app.database import get_session
from app.models import (BacktestIcPoint, BacktestQuantileStat, BacktestRun,
                        Price, signal_store)
from app.services import backtest_engine as eng
from app.services import db_compat

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


def a_fecha(valor):
    """ISO ('2024-01-31') → date. None/'' → None. Ya-date → tal cual.

    Existe porque comparar la columna `date` contra un **string** funciona en
    sqlite y **falla en PostgreSQL** con `operator does not exist: date >=
    character varying`. La config guarda las fechas como texto (tiene que
    serializarse a JSON para el snapshot del run), así que la conversión va
    donde se arma la query, no en la config.

    Es un bug que vivió en producción sin que nadie lo viera: la pantalla de
    Backtest pasa la fecha del selector como ISO, así que cualquiera que
    completara «desde» lo pegaba. La suite corre sobre sqlite, que coerciona el
    string sin chistar — la misma clase de diferencia entre motores que motiva
    `tests/test_bootstrap_portability`.
    """
    import datetime as _dt

    if not valor:
        return None
    if isinstance(valor, _dt.datetime):
        return valor.date()
    if isinstance(valor, _dt.date):
        return valor
    try:
        return _dt.date.fromisoformat(str(valor)[:10])
    except ValueError:
        raise ValueError(
            f"Fecha inválida: {valor!r}. Usá el formato AAAA-MM-DD.") from None


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
    # Se validan acá para que una fecha mal escrita falle con un mensaje claro
    # en vez de con un error de SQL. Se guardan como ISO: la config se
    # serializa a JSON para el snapshot del run, y un `date` no es JSON.
    for k in ("date_from", "date_to"):
        f = a_fecha(cfg[k])
        cfg[k] = f.isoformat() if f else None
    return cfg


def compute_backtest(strategy_id: int, config=None, progress_cb=None) -> dict:
    """Corre el backtest y DEVUELVE el resultado. **No escribe nada.**

    Correr y guardar son dos cosas distintas, y hasta ahora estaban pegadas
    solo en este nivel: los niveles de reglas y de cartera ya computaban sin
    persistir (`run_portfolio_backtest` + `save_portfolio_run` son funciones
    separadas). Esto alinea el nivel A con ese patrón, que ya estaba probado
    dos módulos más allá.

    Sirve para explorar sin dejar rastro —probar tres horizontes y quedarse con
    uno— y es lo que hace que una IA pueda backtestear sin llenar la base de
    corridas de prueba, sin necesidad de un camino paralelo.

    Devuelve dicts planos, no objetos ORM: el resultado puede viajar (a la UI,
    a una herramienta MCP, a un JSON) sin arrastrar una sesión de base.
    """
    cfg = normalize_config(config)
    s = get_session()
    t0 = time.time()
    datos = _computar(s, int(strategy_id), cfg, progress_cb)
    datos["duration_seconds"] = time.time() - t0
    return datos


def save_backtest_run(resultado: dict, strategy_id: int,
                      owner_id=None) -> int:
    """Persiste como snapshot un resultado de `compute_backtest`. Devuelve el
    run_id. Es una acción explícita: correr no guarda."""
    s = get_session()
    run = BacktestRun(strategy_id=int(strategy_id), owner_id=owner_id,
                      config=json.dumps(resultado["config"]), status="done",
                      duration_seconds=resultado.get("duration_seconds"))
    s.add(run)
    s.commit()
    try:
        _persistir(s, run.id, resultado)
    except Exception:
        s.rollback()
        raise
    return run.id


def run_backtest(strategy_id: int, config=None, owner_id=None,
                 progress_cb=None) -> int:
    """Corre y persiste, en un paso. Devuelve el run_id.

    El run se crea ANTES de computar y a propósito: ante error queda con
    status='error' y el mensaje, visible en la lista de corridas. Si se creara
    al final, un backtest que falla no dejaría ningún rastro de haber existido.
    Por eso no es simplemente `save_backtest_run(compute_backtest(...))`.
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
        datos = _computar(s, int(strategy_id), cfg, progress_cb)
        _persistir(s, run_id, datos)
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


def compute_variant_backtest(strategy_id: int, components: list[dict],
                             config=None, progress_cb=None) -> dict:
    """Backtestea una VARIANTE de una estrategia **sin materializarla**.

    Contesta "¿y si le cambio los pesos?" sin crear nada. Importa porque crear
    una estrategia de verdad no es barato: son dos `ALTER TABLE ADD COLUMN`
    sobre una tabla ancha COMPARTIDA (con su lock sobre lo que usa todo el
    pipeline), una corrida de backfill sobre producción, y en PostgreSQL la
    columna borrada después sigue ocupando lugar y contando contra el tope de
    1600 hasta reescribir la tabla. Probar cinco variantes así es caro y sucio.

    **La variante hereda la elegibilidad de la estrategia base.** Los pares
    (fecha, activo) que se evalúan son exactamente los que la base tiene
    puntuados, y eso ya codifica su filtro: un activo tiene score en una fecha
    si y solo si pasó el filtro ese día. Sale gratis y es fiel — pero implica
    que esto sirve para cambiar COMPONENTES Y PESOS, no el filtro. Cambiar el
    universo es otra cosa y exige recalcular la elegibilidad fecha por fecha.

    `components`: [{"signal_key": str, "weight": float}]. Misma semántica de
    score que el motor real (`strategy_service._compute_asset_score`): promedio
    ponderado con divisor Σ|peso|, y los componentes sin dato se SALTEAN en vez
    de contar como cero.

    Devuelve {"base": …, "variante": …} con la misma forma que
    `compute_backtest`, para poder compararlos lado a lado. Los dos se calculan
    sobre el MISMO panel de precios: la parte cara se paga una sola vez.
    """
    from app.models import SignalDefinition
    from app.services.strategy_service import parse_component_weight

    if not components:
        raise ValueError("Indicá al menos un componente.")

    cfg = normalize_config(config)
    s = get_session()
    t0 = time.time()

    base_rows = leer_scores(s, strategy_id, cfg)

    # Componentes → (signal_id, peso). La key es el identificador del formato
    # de packs, así que es lo que ve y escribe quien arma la variante.
    pesos: dict[int, float] = {}
    for c in components:
        clave = str(c.get("signal_key") or "").strip()
        if not clave:
            raise ValueError("Cada componente necesita un signal_key.")
        sig = s.query(SignalDefinition).filter(
            db_compat.ci_equals(SignalDefinition.key, clave)).first()
        if sig is None:
            raise ValueError(f"No existe la señal '{clave}'.")
        pesos[sig.id] = parse_component_weight(c.get("weight"))

    d0 = min(d for d, _a, _s in base_rows)
    d1 = max(d for d, _a, _s in base_rows)

    # Se lee por `read_sig_table`, que es el despacho que anda con la tabla
    # ancha y con las per-señal. `load_wide_signal_scores` sería un scan menos,
    # pero solo existe en modo ancho: con el flag apagado esto quedaría roto, y
    # son unos pocos componentes — la diferencia no paga saltear la abstracción.
    por_par: dict = defaultdict(dict)
    for sid in pesos:
        rt = signal_store.read_sig_table(s, sid)
        q = (sa.select(rt.c.date, rt.c.asset_id, rt.c.score)
             .where(rt.c.score.isnot(None),
                    rt.c.date >= a_fecha(d0), rt.c.date <= a_fecha(d1)))
        for d, aid, val in s.execute(q).all():
            por_par[(d, aid)][sid] = float(val)

    # Solo los pares que la base tiene puntuados: ahí está su elegibilidad.
    variante_rows = []
    for d, aid, _sc in base_rows:
        disponibles = por_par.get((d, aid))
        if not disponibles:
            continue
        num = tot = 0.0
        for sid, w in pesos.items():
            v = disponibles.get(sid)
            if v is None:
                continue        # se saltea, no cuenta como cero
            num += v * w
            tot += abs(w)
        if tot:
            variante_rows.append((d, aid, round(num / tot, 4)))

    if not variante_rows:
        raise ValueError(
            "Ninguna de esas señales tiene valores en el período de la "
            "estrategia. Revisá que las señales tengan historia calculada.")

    # Un solo panel de precios para los dos: es la parte cara.
    fwd = _retornos_forward(s, base_rows, cfg, progress_cb)

    def _resultado(filas):
        datos = _agregar(_por_fecha(filas, fwd, cfg), cfg, None)
        datos["config"] = cfg
        return datos

    return {
        "config": cfg,
        "duration_seconds": time.time() - t0,
        "base": _resultado(base_rows),
        "variante": _resultado(variante_rows),
    }


def _persistir(s, run_id: int, datos: dict) -> None:
    """Vuelca un resultado computado a las tablas del snapshot."""
    s.add_all([BacktestIcPoint(run_id=run_id, **p) for p in datos["ic_points"]])
    s.add_all([BacktestQuantileStat(run_id=run_id, **q)
               for q in datos["quantile_stats"]])
    run = s.get(BacktestRun, run_id)
    run.status = "done"
    run.date_from = datos["date_from"]
    run.date_to = datos["date_to"]
    run.n_dates = datos["n_dates"]
    s.commit()
    logger.info("Backtest run %s: %s fechas, %s horizontes",
                run_id, datos["n_dates"], len(datos["config"]["horizons"]))


def _chunks(lst, n):
    for i in range(0, len(lst), n):
        yield lst[i:i + n]


def leer_scores(s, strategy_id, cfg) -> list[tuple]:
    """[(date, asset_id, score)] de una estrategia MATERIALIZADA, en el período.

    Separado de `_computar` para que el resto del cálculo —precios, retornos
    forward, cross-sections, agregación— pueda alimentarse también con scores
    calculados en memoria (ver `compute_variant_backtest`). Sin esta división
    habría que duplicar todo el motor para backtestear una variante.
    """
    rt = signal_store.read_strat_table(s, strategy_id)
    q = (sa.select(rt.c.date, rt.c.asset_id, rt.c.score)
         .where(rt.c.score.isnot(None)))
    # a_fecha y no el string crudo: PostgreSQL no compara `date` con `varchar`.
    if cfg["date_from"]:
        q = q.where(rt.c.date >= a_fecha(cfg["date_from"]))
    if cfg["date_to"]:
        q = q.where(rt.c.date <= a_fecha(cfg["date_to"]))
    filas = s.execute(q).all()
    if not filas:
        raise ValueError(
            "La estrategia no tiene historia calculada en el período. "
            "Correr «Recalcular completo» en Centro de Datos → Señales y "
            "Estrategias.")
    return filas


def _computar(s, strategy_id, cfg, progress_cb, score_rows=None) -> dict:
    """El cálculo, sin escribir. Devuelve dicts planos (no objetos ORM) para
    que el resultado pueda viajar sin arrastrar una sesión.

    `score_rows` permite alimentar el motor con puntajes que no salen de la
    tabla de la estrategia: es lo que hace posible backtestear una variante
    hipotética sin materializarla.
    """
    horizons = cfg["horizons"]

    if score_rows is None:
        score_rows = leer_scores(s, strategy_id, cfg)

    per_date = _por_fecha(score_rows,
                          _retornos_forward(s, score_rows, cfg, progress_cb),
                          cfg)
    return _agregar(per_date, cfg, progress_cb)


def _retornos_forward(s, score_rows, cfg, progress_cb) -> dict:
    """{asset_id: (posición_por_fecha, retornos_forward)} — la parte CARA.

    Está separada porque es lo único que depende de los precios y no de los
    puntajes: así se puede evaluar más de un juego de scores sobre el mismo
    panel sin volver a leer millones de filas de `prices`. Es lo que hace
    viable comparar una estrategia con una variante en una sola pasada.
    """
    horizons = cfg["horizons"]
    asset_ids = sorted({aid for _d, aid, _sc in score_rows})
    salida: dict = {}
    done = 0
    for batch in _chunks(asset_ids, _ASSET_BATCH):
        q = (s.query(Price.asset_id, Price.date, Price.close)
             .filter(Price.asset_id.in_(batch), Price.close.isnot(None)))
        # PISO SÍ, TECHO NO — y la asimetría es la parte importante. Los
        # retornos son FORWARD: ningún precio anterior a date_from se usa
        # jamás, así que recortar la cabeza no puede cambiar un resultado
        # (medido: sin esto, una corrida acotada a 2025 leía 50 años de
        # precios para usar 1,6). Un techo, en cambio, truncaría en silencio
        # la ventana futura del horizonte más largo: el retorno a 60 días de
        # la última fecha necesita precios POSTERIORES a date_to.
        if cfg["date_from"]:
            q = q.filter(Price.date >= a_fecha(cfg["date_from"]))
        price_rows = q.order_by(Price.asset_id, Price.date).all()
        prices_by_asset = defaultdict(list)
        for aid, d, c in price_rows:
            prices_by_asset[aid].append((d, float(c)))

        for aid in batch:
            series = prices_by_asset.get(aid)
            if not series:
                continue
            closes = [c for _, c in series]
            salida[aid] = ({d: i for i, (d, _) in enumerate(series)},
                           eng.forward_returns_for_series(closes, horizons,
                                                          cfg["lag"]))
        done += len(batch)
        if progress_cb:
            progress_cb(done, len(asset_ids), "activos")
    return salida


def _por_fecha(score_rows, fwd_por_activo, cfg) -> dict:
    """per_date[D] = [(score, {h: ret|None}), ...] — solo pares (activo, D)
    donde el activo tiene precio PROPIO en D (el gate de lectura)."""
    per_date = defaultdict(list)
    for d, aid, sc in score_rows:
        datos = fwd_por_activo.get(aid)
        if datos is None:
            continue
        pos, fwd = datos
        i = pos.get(d)
        if i is None:
            continue          # GATE: sin precio propio en D → afuera
        per_date[d].append((float(sc), fwd[i]))
    return per_date


def _agregar(per_date, cfg, progress_cb) -> dict:
    """Cross-sections por fecha × horizonte y sus agregados."""
    horizons = cfg["horizons"]

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
            ic_rows.append({"date": d, "horizon": h, "ic": cs["ic"],
                            "spread": cs["spread"], "n_assets": cs["n"]})
        if progress_cb and (j % 100 == 0 or j == len(all_dates) - 1):
            progress_cb(j + 1, len(all_dates), "fechas")

    # ── Agregados + persistencia ──────────────────────────────────────────
    stat_rows = []
    for h in horizons:
        agg = eng.aggregate_cross_sections(sections_by_h[h])
        if agg is None:
            continue
        for qd in agg["quantiles"]:
            stat_rows.append({"horizon": h, "quantile": qd["quantile"],
                              "n_dates": qd["n_dates"], "mean_ret": qd["mean_ret"],
                              "median_ret": qd["median_ret"],
                              "pct_pos": qd["pct_pos"]})
    if not stat_rows:
        raise ValueError(
            "Ninguna fecha alcanzó el mínimo de observaciones "
            f"({cfg['min_assets']}). Bajá el mínimo o revisá la historia.")

    computed = sorted({r["date"] for r in ic_rows})
    # La config viaja DENTRO del resultado: así el dict se explica solo, y
    # `_persistir` no depende de que el caller se acuerde de adjuntarla.
    return {"config": cfg, "ic_points": ic_rows, "quantile_stats": stat_rows,
            "date_from": computed[0], "date_to": computed[-1],
            "n_dates": len(computed)}


# ── Lectura para la UI ────────────────────────────────────────────────────────

RETENCION_DIAS = 180


def prune_old(retention_days: int = RETENCION_DIAS) -> int:
    """Borra los backtests guardados más viejos que la retención.

    Sin esto la tabla crece para siempre: `backtest_ic_point` guarda una fila
    por fecha × horizonte, así que cada corrida deja miles. Mismo criterio y
    misma retención que `run_history_service.prune_old`.

    Fail-open a propósito (devuelve 0 y no propaga): corre al arrancar la
    aplicación, y no poder podar nunca puede ser motivo de que la app no
    levante.
    """
    from datetime import datetime, timedelta

    corte = datetime.utcnow() - timedelta(days=int(retention_days))
    s = get_session()
    try:
        viejos = [r.id for r in s.query(BacktestRun.id)
                  .filter(BacktestRun.created_at < corte).all()]
        if not viejos:
            return 0
        # Las hijas primero y explícitas: el CASCADE está declarado en el
        # modelo, pero en SQLite no se aplica salvo que las FK estén activas.
        for modelo in (BacktestIcPoint, BacktestQuantileStat):
            s.query(modelo).filter(modelo.run_id.in_(viejos)).delete(
                synchronize_session=False)
        s.query(BacktestRun).filter(BacktestRun.id.in_(viejos)).delete(
            synchronize_session=False)
        s.commit()
        return len(viejos)
    except Exception as exc:                                # noqa: BLE001
        s.rollback()
        logger.warning("No se pudieron purgar backtests viejos: %s", exc)
        return 0


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
