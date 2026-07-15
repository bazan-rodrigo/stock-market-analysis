"""
Modo rango del backfill de señales/estrategias.

El pipeline por-fecha (signal_service.run_daily y compañía) está diseñado
para UNA fecha — el uso diario del scheduler. Llamarlo 25.000 veces en un
loop repite por fecha queries que son constantes (definiciones, grupos de
activos) o incrementales (as-of de indicadores). Este módulo hace el mismo
cálculo para un RANGO de fechas con:

- Contexto invariante cargado una vez (señales parseadas, grupos de
  activos, estrategias con filtros parseados, valores current).
- Barrido cronológico por chunks: cada tabla ind_* se carga UNA vez por
  chunk (ventana [inicio - 45 días, fin]) ordenada por fecha, y un puntero
  por código avanza fecha a fecha — el as-of sale de memoria en O(1)
  amortizado, con la MISMA semántica que query_values_asof (última fila
  <= fecha, tope 45 días, valores NULL excluidos).
- Escrituras en bloque por chunk: DELETE de las fechas procesadas (acotado
  al alcance) + INSERT masivo, un commit por chunk.

La MATEMÁTICA no vive acá: los evaluadores compartidos
(_evaluate_asset_signal_scores, _evaluate_group_signal_scores,
aggregate_group_scores, rank_strategy_assets) son los mismos que usa el
camino por-fecha — ver tests/test_signal_range_parity.py.

Divergencias deliberadas con el camino por-fecha (no son regresiones):
- El DELETE por fecha elimina filas obsoletas (señales/grupos que ya no
  puntúan ese día) que el upsert por-fecha dejaría zombies.
- group_scores/group_signal_value se escriben SOLO para los grupos que
  alguna estrategia consume (_derive_needed_groups): sin señales de grupo
  no se escribe historia, y una señal acotada a un país solo calcula ese
  país. El camino por-fecha (compute_group_scores) escribe todos los grupos
  todas las fechas porque alimenta el mapa de mercado; en modo rango eso se
  preserva escribiendo la ÚLTIMA fecha completa y el resto solo lo necesario.
"""
import logging
import queue
import random
import threading
import time
from datetime import timedelta
from types import SimpleNamespace

import sqlalchemy as sa
from sqlalchemy.exc import OperationalError

from app.database import Session as _DbSession
from app.database import get_session
from app.services.db_utils import delete_by_ranges
from app.models import (
    Asset,
    GroupScore,
    GroupSignalValue,
    SignalEvalLog,
    SignalValue,
    Strategy,
    StrategyResult,
)
from app.models.indicator_store import (
    ASOF_MAX_LOOKBACK_DAYS,
    CurrentIndicatorValue,
    get_ind_table,
)
from app.models.price import Price
from app.services import strategy_filter
from app.services.group_score_service import (
    _TF_MAP,
    _TREND_CODES,
    aggregate_group_scores,
)
from app.services.signal_service import (
    _VIRTUAL_CODES,
    _evaluate_asset_signal_scores,
    _evaluate_group_signal_scores,
    _prepare_signals,
)
from app.services.strategy_service import percent_ranks, rank_strategy_assets

logger = logging.getLogger(__name__)

_CHUNK_DATES = 250   # ~1 año de ruedas por chunk (unidad de carga del barrido)

# Errores InnoDB que la app debe reintentar (escrituras concurrentes contra
# las mismas tablas — p.ej. una baja de activo que borra en cascada
# signal_value mientras este backfill inserta; ver _fund_worker en
# fundamental_service, mismo patrón). Sin esto un lock timeout abandona el
# chunk entero (un año de fechas), que reaparece como hueco en el próximo delta.
_DEADLOCK_ERRNO     = 1213  # "Deadlock found when trying to get lock"
_LOCK_TIMEOUT_ERRNO = 1205  # "Lock wait timeout exceeded"
_MAX_LOCK_RETRIES   = 3


def _is_retryable_lock_error(exc: BaseException) -> bool:
    orig  = getattr(exc, "orig", None)
    errno = orig.args[0] if orig and getattr(orig, "args", None) else None
    return errno in (_DEADLOCK_ERRNO, _LOCK_TIMEOUT_ERRNO)


def _load_derivation_inputs(s):
    """Insumos (desde la BD) para derivar qué grupos calcular: se miran TODAS
    las estrategias y TODAS las señales, no solo las del alcance de esta
    corrida — el conjunto de grupos de una señal es propiedad de la señal y de
    todos sus consumidores, no del alcance con que se la recalcula (si no,
    recalcular la estrategia de Argentina borraría los grupos que necesita la
    de Brasil sobre la misma señal). Devuelve (strategies, gtypes_by_id,
    gtypes_by_key)."""
    from app.models import SignalDefinition, Strategy

    # {signal_key: set(group_type)} — cada señal de grupo aporta su propio tipo
    gtypes_by_key, gtypes_by_id = {}, {}
    for sig in s.query(SignalDefinition).all():
        gtypes = ({sig.group_type}
                  if sig.source == "group" and sig.group_type else set())
        gtypes_by_key[sig.key] = gtypes
        gtypes_by_id[sig.id] = gtypes

    strategies = []
    for st in s.query(Strategy).all():
        tree = strategy_filter.parse_tree(st.filter_conditions)
        sig_ops = ({key for t, key, _r in strategy_filter.collect_operands(tree)
                    if t == "signal"} if tree is not None else set())
        comps = [SimpleNamespace(signal_id=c.signal_id, scope=c.scope,
                                 group_type=c.group_type, group_id=c.group_id)
                 for c in st.components]
        strategies.append({"tree": tree, "components": comps,
                           "signal_operands": sig_ops})
    return strategies, gtypes_by_id, gtypes_by_key


def _derive_needed_groups(types_with_signals, strategies,
                          gtypes_by_id, gtypes_by_key) -> dict:
    """{group_type: set[int] | None}. None = todos los ids de ese tipo;
    group_type AUSENTE = ninguna estrategia lo consume → no se escribe su
    historia en modo rango (el mapa de mercado lo mantiene el camino diario,
    que siempre escribe la última fecha completa).

    Una señal de grupo de tipo T se calcula solo para los group_id que alguna
    estrategia realmente usa: specific_group puntual, own_group acotado por el
    filtro de esa estrategia (ver strategy_filter.restricted_attribute_ids).
    Se toma la UNIÓN sobre todas las estrategias que la consumen — así el
    conjunto no depende del alcance de la corrida. Si ninguna estrategia la
    restringe (o la usa sin filtrar ese atributo) → todos los grupos del tipo,
    default seguro (una señal creada para verse suelta se calcula entera)."""
    if not types_with_signals:
        return {}

    needed: dict = {}
    constrained: set = set()

    def _mark(t, ids):
        if t not in types_with_signals:
            return
        constrained.add(t)
        if t in needed and needed[t] is None:       # ya abierto a todos
            return
        if ids is None:
            needed[t] = None
        else:
            needed[t] = (needed.get(t) or set()) | ids

    for st in strategies:
        tree = st["tree"]
        for comp in st["components"]:
            if comp.scope == "specific_group" and comp.group_id is not None:
                _mark(comp.group_type, {comp.group_id})
            elif comp.scope == "own_group" and comp.group_type:
                _mark(comp.group_type,
                      strategy_filter.restricted_attribute_ids(tree, comp.group_type))
            else:
                # scope directo: lee el valor por-activo de la señal; si es de
                # grupo necesita el grupo de cada activo que pase el filtro
                for t in gtypes_by_id.get(comp.signal_id, ()):
                    _mark(t, strategy_filter.restricted_attribute_ids(tree, t))
        # señales de grupo usadas en el filtro: se evalúan sobre TODOS los
        # candidatos antes de filtrar → hacen falta todos los grupos del tipo
        for key in st["signal_operands"]:
            for t in gtypes_by_key.get(key, ()):
                _mark(t, None)

    # tipos con señal que ninguna estrategia restringe → todos
    for t in types_with_signals:
        if t not in constrained:
            needed[t] = None
    return needed

# Tope de filas acumuladas antes de escribir: un chunk de la era densa
# (500 activos × 16 señales × 250 fechas ≈ 2M filas) en una sola
# transacción infla memoria (dicts + GC) y el commit de InnoDB — el flush
# intermedio mantiene ambos acotados sin cambiar el resultado
_MAX_ROWS_PER_FLUSH = 150_000


class _Sweep:
    """Puntero cronológico sobre las filas (asset_id, date, value) de un
    ind_{code}, ordenadas por fecha. advance(d) deja en .live la última
    fila <= d por activo."""

    __slots__ = ("rows", "idx", "live")

    def __init__(self, rows):
        self.rows = rows      # [(asset_id, date, value)] orden por date
        self.idx  = 0
        self.live = {}        # {asset_id: (date, value)}

    def advance(self, d):
        rows, n = self.rows, len(self.rows)
        i = self.idx
        while i < n and rows[i][1] <= d:
            self.live[rows[i][0]] = (rows[i][1], rows[i][2])
            i += 1
        self.idx = i

    def snapshot_asof(self, d):
        """{asset_id: value} con la semántica exacta de query_values_asof:
        última fila <= d, no más vieja que 45 días, valor no NULL."""
        cutoff = d - timedelta(days=ASOF_MAX_LOOKBACK_DAYS)
        return {aid: v for aid, (dt, v) in self.live.items()
                if v is not None and dt >= cutoff}

    def exact(self, d):
        """{asset_id: value} solo de filas con fecha EXACTA d (semántica de
        compute_group_scores sobre ind_trend_*)."""
        return {aid: v for aid, (dt, v) in self.live.items() if dt == d}


def _load_sweep(s, code, window_start, window_end) -> _Sweep:
    try:
        tbl = get_ind_table(code)
    except sa.exc.NoSuchTableError:
        logger.warning("signal_backfill_range: tabla ind_%s no existe", code)
        return _Sweep([])
    rows = s.execute(
        sa.select(tbl.c.asset_id, tbl.c.date, tbl.c.value)
        .where(tbl.c.date >= window_start, tbl.c.date <= window_end)
        .order_by(tbl.c.date)
    ).fetchall()
    return _Sweep([(r[0], r[1], r[2]) for r in rows])


def _load_current_values(s, codes) -> dict[str, dict]:
    """{code: {asset_id: value}} desde current_indicator_values (indicadores
    sin historia y operandos resolution=current del filtro)."""
    if not codes:
        return {}
    out: dict[str, dict] = {c: {} for c in codes}
    rows = s.query(
        CurrentIndicatorValue.asset_id, CurrentIndicatorValue.code,
        CurrentIndicatorValue.value_num, CurrentIndicatorValue.value_str,
    ).filter(CurrentIndicatorValue.code.in_(list(codes))).all()
    for aid, code, num, txt in rows:
        value = num if num is not None else txt
        if value is not None:
            out[code][aid] = value
    return out


def _consume_writes(q: "queue.Queue", flush_fn, errors_out: list):
    """Loop del thread escritor asíncrono: consume lotes en orden FIFO hasta
    el sentinel None. Tras un error registra la excepción y sigue DRENANDO
    (sin escribir) para no dejar bloqueado al productor en la cola acotada.
    A nivel módulo para testearlo con un flush falso."""
    while True:
        item = q.get()
        if item is None:
            return
        if errors_out:
            continue  # drenando: ya hubo un error, no se escribe más
        try:
            flush_fn(*item)
        except Exception as exc:
            logger.exception("signal_backfill_range: flush asíncrono falló")
            errors_out.append(exc)


def run_range(dates, *, only_ids, strategy_id, scope_kind,
              latest_price_date, eval_kind, eval_ref, logged,
              progress_cb=None, force=False, full_wipe=False) -> dict:
    """Equivalente en rango del loop por-fecha de _signal_history_run.
    dates: lista ordenada de fechas a procesar (huecos + última).

    force: rebuild — limpieza ÚNICA al inicio y batches solo-INSERT.
    Borrar por batch sobre una tabla de decenas de millones de filas
    degrada progresivamente (el purge de InnoDB arrastra las filas muertas
    acumuladas toda la corrida: se midió 10s→32s por chunk con conteos
    iguales). full_wipe: force sin horizonte ni alcance — las tablas
    derivadas se vacían enteras (TRUNCATE en MySQL)."""
    s = get_session()

    # ── Contexto invariante de la corrida ─────────────────────────────────
    prep = _prepare_signals(s, only_ids)
    if prep is None:
        return {"total": 0, "success": 0, "errors": []}

    asset_groups = {
        a.id: {
            "sector":          a.sector_id,
            "market":          a.market_id,
            "industry":        a.industry_id,
            "country":         a.country_id,
            "instrument_type": a.instrument_type_id,
        }
        for a in s.query(
            Asset.id, Asset.sector_id, Asset.market_id,
            Asset.industry_id, Asset.country_id, Asset.instrument_type_id,
        ).all()
    }
    asset_meta = asset_groups  # mismo mapa que usa compute_group_scores

    # Estrategias a calcular (con filtro parseado y operandos clasificados)
    if scope_kind == "strategy":
        strategies = s.query(Strategy).filter(Strategy.id == strategy_id).all()
    elif scope_kind is None:
        strategies = s.query(Strategy).all()
    else:  # scope señal: no toca resultados de estrategias
        strategies = []

    strat_ctx = []
    filter_hist_codes: set[str] = set()
    filter_current_codes: set[str] = set()
    filter_signal_keys: set[str] = set()
    for strat in strategies:
        if not strat.components:
            continue
        tree = strategy_filter.parse_tree(strat.filter_conditions)
        operands = strategy_filter.collect_operands(tree) if tree is not None else set()
        for t, key, res in operands:
            if t == "indicator" and res == "current":
                filter_current_codes.add(key)
            elif t == "indicator":
                filter_hist_codes.add(key)
            elif t == "signal":
                filter_signal_keys.add(key)
        strat_ctx.append({
            "id": strat.id,
            # Copias planas: _compute_asset_score accede a estos atributos
            # por activo × estrategia × fecha (el descriptor ORM pesa)
            "components": [
                SimpleNamespace(signal_id=c.signal_id, weight=c.weight,
                                scope=c.scope, group_type=c.group_type,
                                group_id=c.group_id)
                for c in strat.components
            ],
            "signal_ids": {c.signal_id for c in strat.components},
            "tree": tree,
            "operands": operands,
        })

    sig_id_by_key = {sig.key: sig.id for sig in prep["signals"]}

    # Códigos a barrer: señales + tendencias de grupo + filtro (historic)
    sweep_codes = (set(prep["hist_codes"]) | set(_TREND_CODES)
                   | filter_hist_codes)

    # Valores current (una vez: son el estado VIGENTE, no dependen de la fecha)
    current_by_code = _load_current_values(
        s, set(prep["nohist_codes"]) | filter_current_codes)

    need_last_close = "last_close" in prep["virtual_codes"]

    signal_ids_all  = [sig.id for sig in prep["signals"]]
    group_sig_ids   = [sig.id for sig in prep["group_signals"]]
    strat_ids       = [c["id"] for c in strat_ctx]

    # Grupos realmente consumidos: sin señales de grupo esto queda vacío y no
    # se escribe NADA de historia en group_scores/group_signal_value (antes se
    # escribía la agregación de ~200 grupos por fecha aunque nadie la leyera).
    # La derivación mira TODAS las estrategias (no solo las del alcance): el
    # conjunto de grupos de una señal es propiedad de sus consumidores.
    types_with_signals = {sig.group_type for sig in prep["group_signals"]
                          if sig.group_type}
    if types_with_signals:
        _deriv_strats, _gtypes_by_id, _gtypes_by_key = _load_derivation_inputs(s)
        needed_groups = _derive_needed_groups(
            types_with_signals, _deriv_strats, _gtypes_by_id, _gtypes_by_key)
    else:
        needed_groups = {}

    needed_group_types = set(needed_groups)

    def _group_needed(group_type, group_id) -> bool:
        if group_type not in needed_groups:
            return False
        ids = needed_groups[group_type]
        return ids is None or group_id in ids

    total = len(dates)
    errors: list[dict] = []
    done = 0

    is_mysql = s.get_bind().dialect.name in ("mysql", "mariadb")

    # ── Rebuild: limpieza única (después solo INSERTs) ────────────────────
    # Corre en el thread ESCRITOR cuando el modo asíncrono está activo, con
    # la sesión de ese thread (ws). Los DELETE van por VENTANAS DE FECHAS
    # QUE AVANZAN (db_utils.delete_by_ranges, convención CLAUDE.md):
    # - la sentencia única sobre la historia completa corrió 400s+
    #   reteniendo locks/undo;
    # - el loop `DELETE ... LIMIT` sobre el rango completo fue PEOR (17min+
    #   sin terminar): cada lote re-escanea desde el inicio del rango los
    #   tombstones de los lotes anteriores — O(n²).
    # Cada ventana ataca un tramo virgen del índice (signal_id, date).
    _CLEANUP_WINDOW_DATES = 100

    def _cleanup_windows():
        slices = (dates[i:i + _CLEANUP_WINDOW_DATES]
                  for i in range(0, len(dates), _CLEANUP_WINDOW_DATES))
        return [(str(w[0]), str(w[-1])) for w in slices]

    def _initial_cleanup(ws):
        if not force:
            return
        if full_wipe and is_mysql:
            # TRUNCATE: instantáneo y sin filas muertas que purgar.
            # signal_eval_log NO se toca: las fechas siguen evaluadas
            # (se están recalculando ahora mismo) y guarda markers de
            # otros alcances.
            for t in ("signal_value", "group_signal_value", "group_scores",
                      "strategy_result"):
                ws.execute(sa.text(f"TRUNCATE TABLE {t}"))
            ws.commit()
        else:
            windows = _cleanup_windows()
            if signal_ids_all:
                ids = ", ".join(str(int(i)) for i in signal_ids_all)
                delete_by_ranges(ws, "signal_value", "date", windows,
                                 f"signal_id IN ({ids})")
            if group_sig_ids:
                ids = ", ".join(str(int(i)) for i in group_sig_ids)
                delete_by_ranges(ws, "group_signal_value", "date", windows,
                                 f"signal_id IN ({ids})")
            # group_scores: solo los tipos que ESTA corrida reescribe (los
            # demás pueden pertenecer a otras señales de grupo) + la última
            # fecha completa para el mapa de mercado. Un rebuild acotado no
            # debe borrar la historia de tipos que no le corresponden.
            if needed_group_types:
                gts = ", ".join(f"'{t}'" for t in sorted(needed_group_types))
                delete_by_ranges(ws, "group_scores", "date", windows,
                                 f"group_type IN ({gts})")
            if (latest_price_date is not None
                    and dates[0] <= latest_price_date <= dates[-1]):
                ws.execute(sa.delete(GroupScore.__table__).where(
                    GroupScore.date == latest_price_date))
                ws.commit()
            if strat_ids:
                ids = ", ".join(str(int(i)) for i in strat_ids)
                delete_by_ranges(ws, "strategy_result", "date", windows,
                                 f"strategy_id IN ({ids})")
        logger.info("signal_backfill_range: limpieza inicial de rebuild "
                    "completada (%s)",
                    "truncate" if full_wipe else "delete por ventanas")

    # Placeholder del driver: el INSERT masivo va por exec_driver_sql
    # (executemany del DBAPI) — la compilación de SQLAlchemy por fila
    # (construct_params + type processing) pesaba ~15% de la corrida
    _PH = "?" if s.get_bind().dialect.paramstyle == "qmark" else "%s"

    def _bulk_insert(ws, table_name: str, columns: tuple, rows: list):
        if not rows:
            return
        cols = ", ".join(columns)
        ph = ", ".join([_PH] * len(columns))
        ws.connection().exec_driver_sql(
            f"INSERT INTO {table_name} ({cols}) VALUES ({ph})", rows)

    def _flush_once(ws, batch_dates, sv_rows, gsv_rows, gs_rows, sr_rows,
                    marker_rows):
        if not force:
            if signal_ids_all:
                ws.execute(sa.delete(SignalValue.__table__).where(
                    SignalValue.date.in_(batch_dates),
                    SignalValue.signal_id.in_(signal_ids_all)))
            if group_sig_ids:
                ws.execute(sa.delete(GroupSignalValue.__table__).where(
                    GroupSignalValue.date.in_(batch_dates),
                    GroupSignalValue.signal_id.in_(group_sig_ids)))
            # group_scores: solo los tipos reescritos (los demás pueden ser de
            # otras señales) + la última fecha completa (mapa de mercado)
            if needed_group_types:
                ws.execute(sa.delete(GroupScore.__table__).where(
                    GroupScore.date.in_(batch_dates),
                    GroupScore.group_type.in_(needed_group_types)))
            if latest_price_date in batch_dates:
                ws.execute(sa.delete(GroupScore.__table__).where(
                    GroupScore.date == latest_price_date))
            if strat_ids:
                ws.execute(sa.delete(StrategyResult.__table__).where(
                    StrategyResult.date.in_(batch_dates),
                    StrategyResult.strategy_id.in_(strat_ids)))

        _bulk_insert(ws, "group_scores",
                     ("group_type", "group_id", "date", "regime_score_d",
                      "regime_score_w", "regime_score_m", "n_assets"), gs_rows)
        _bulk_insert(ws, "signal_value",
                     ("signal_id", "asset_id", "date", "score"), sv_rows)
        _bulk_insert(ws, "group_signal_value",
                     ("signal_id", "group_type", "group_id", "date", "score"),
                     gsv_rows)
        _bulk_insert(ws, "strategy_result",
                     ("strategy_id", "asset_id", "date", "score", "pct"),
                     sr_rows)
        _bulk_insert(ws, "signal_eval_log",
                     ("scope_kind", "ref_id", "date"), marker_rows)
        ws.commit()

    def _flush(ws, batch_dates, sv_rows, gsv_rows, gs_rows, sr_rows,
               marker_rows):
        """DELETE de las fechas del batch (solo en delta; el rebuild ya
        limpió todo al inicio) + INSERT masivo + commit. Las fechas ya
        flusheadas quedan persistidas aunque un batch posterior falle.

        Reintenta ante lock timeout/deadlock (1205/1213): el DELETE+INSERT es
        idempotente, y la contención con otras escrituras (p.ej. una baja de
        activo borrando en cascada) suele ser transitoria."""
        if not batch_dates:
            return
        for attempt in range(_MAX_LOCK_RETRIES + 1):
            try:
                _flush_once(ws, batch_dates, sv_rows, gsv_rows, gs_rows,
                            sr_rows, marker_rows)
                break
            except OperationalError as exc:
                ws.rollback()
                if attempt < _MAX_LOCK_RETRIES and _is_retryable_lock_error(exc):
                    logger.warning(
                        "signal_backfill_range: lock timeout/deadlock en flush "
                        "%s..%s (intento %d/%d), reintentando...",
                        batch_dates[0], batch_dates[-1], attempt + 1,
                        _MAX_LOCK_RETRIES)
                    time.sleep(0.2 * (attempt + 1) + random.uniform(0, 0.3))
                    continue
                raise
        logged.update(batch_dates)
        _ok_box[0] += len(batch_dates)
        logger.info(
            "signal_backfill_range: %s..%s (%d fechas): %d signal_value, "
            "%d group_signal_value, %d group_scores, %d strategy_result",
            batch_dates[0], batch_dates[-1], len(batch_dates),
            len(sv_rows), len(gsv_rows), len(gs_rows), len(sr_rows))

    # ── Escritor asíncrono (solo MySQL/MariaDB) ───────────────────────────
    # El borrado/inserción es I/O de MariaDB (libera el GIL): corre en un
    # thread propio con SU sesión mientras el productor computa el chunk
    # siguiente en memoria (el barrido as-of no depende del estado de la BD).
    # Cola acotada (1): a lo sumo un lote en espera además del que se computa
    # — memoria acotada por backpressure. La barrera borrar-antes-de-insertar
    # es estructural: limpieza inicial y flushes viven en el MISMO thread, en
    # orden FIFO. sqlite (tests) va sincrónico: misma semántica, sin
    # concurrencia (la paridad cubre el resultado final).
    use_async = is_mysql
    _ok_box = [0]
    _werrors: list = []
    _wq: queue.Queue = queue.Queue(maxsize=1)

    def _writer_main():
        ws = get_session()
        try:
            try:
                _initial_cleanup(ws)
            except Exception as exc:
                logger.exception(
                    "signal_backfill_range: limpieza inicial falló")
                _werrors.append(exc)
            _consume_writes(_wq, lambda *item: _flush(ws, *item), _werrors)
        finally:
            _DbSession.remove()

    _writer = None
    if use_async:
        _writer = threading.Thread(target=_writer_main, daemon=True)
        _writer.start()
    else:
        _initial_cleanup(s)

    def _emit(batch_dates, sv_rows, gsv_rows, gs_rows, sr_rows, marker_rows):
        """Entrega un lote al escritor (asíncrono) o flushea inline (sync).
        Si el escritor ya falló, descarta el lote — el error se reporta al
        cerrar la corrida."""
        if not batch_dates:
            return
        if use_async:
            if not _werrors:
                _wq.put((batch_dates, sv_rows, gsv_rows, gs_rows, sr_rows,
                         marker_rows))
        else:
            _flush(s, batch_dates, sv_rows, gsv_rows, gs_rows, sr_rows,
                   marker_rows)

    # ── Chunks ────────────────────────────────────────────────────────────
    for start in range(0, total, _CHUNK_DATES):
        if _werrors:
            break  # el escritor murió: computar más lotes sería tirarlos
        chunk = dates[start:start + _CHUNK_DATES]
        window_start = chunk[0] - timedelta(days=ASOF_MAX_LOOKBACK_DAYS)
        window_end   = chunk[-1]

        try:
            sweeps = {code: _load_sweep(s, code, window_start, window_end)
                      for code in sweep_codes}

            closes_by_date: dict = {}
            if need_last_close:
                rows = s.query(Price.date, Price.asset_id, Price.close).filter(
                    Price.date >= chunk[0], Price.date <= window_end).all()
                for dt, aid, close in rows:
                    if close is not None:
                        closes_by_date.setdefault(dt, {})[aid] = float(close)

            sv_rows, gsv_rows, gs_rows, sr_rows, marker_rows = [], [], [], [], []
            batch_dates: list = []

            for d in chunk:
                done += 1
                d_str = str(d)
                if progress_cb:
                    progress_cb(done, total, d_str)

                for sw in sweeps.values():
                    sw.advance(d)

                # Scores de grupo (tendencias con fecha EXACTA d)
                asset_trends: dict[int, dict] = {}
                for code in _TREND_CODES:
                    tf = _TF_MAP[code]
                    for aid, val in sweeps[code].exact(d).items():
                        asset_trends.setdefault(aid, {})[tf] = val
                aggregated = aggregate_group_scores(asset_trends, asset_meta)

                # gscores para los EVALUADORES: solo los grupos que alguna
                # estrategia consume — controla group_signal_value y el valor
                # por-activo de las señales de grupo. Sin señales de grupo o
                # sin consumo → queda vacío y no se evalúa ninguno.
                gscores = {
                    key: SimpleNamespace(group_type=key[0], group_id=key[1], **vals)
                    for key, vals in aggregated.items()
                    if _group_needed(key[0], key[1])
                }
                # group_scores a ESCRIBIR: la ÚLTIMA fecha va completa (la lee
                # el mapa de mercado, que muestra todos los grupos); el resto
                # solo los grupos consumidos (la historia que leen las señales
                # de grupo). Divergencia deliberada con el camino por-fecha,
                # que escribe todos los grupos todas las fechas para el mapa.
                write_all_groups = (d == latest_price_date)
                gs_rows.extend(
                    (gt, gid, d_str, vals["regime_score_d"],
                     vals["regime_score_w"], vals["regime_score_m"],
                     vals["n_assets"])
                    for (gt, gid), vals in aggregated.items()
                    if write_all_groups or _group_needed(gt, gid)
                )

                # Snapshots as-of de todos los códigos barridos
                snap = {code: sw.snapshot_asof(d) for code, sw in sweeps.items()}

                # isnaps para señales de activo (hist + current-si-es-hoy + virtual)
                isnaps: dict[int, dict] = {}
                for code in prep["hist_codes"]:
                    for aid, val in snap.get(code, {}).items():
                        isnaps.setdefault(aid, {})[code] = val
                if prep["nohist_codes"] and d == latest_price_date:
                    for code in prep["nohist_codes"]:
                        for aid, val in current_by_code.get(code, {}).items():
                            isnaps.setdefault(aid, {})[code] = val
                if need_last_close:
                    for aid, val in closes_by_date.get(d, {}).items():
                        isnaps.setdefault(aid, {})["last_close"] = val

                sv_scores = _evaluate_asset_signal_scores(
                    signals=prep["signals"], asset_signals=prep["asset_signals"],
                    group_signals=prep["group_signals"],
                    params_by_id=prep["params_by_id"],
                    compiled_by_id=prep["compiled_by_id"], isnaps=isnaps,
                    asset_groups=asset_groups, gscores=gscores)
                sv_rows.extend(
                    (k[0], k[1], d_str, v) for k, v in sv_scores.items())

                gsv_scores = _evaluate_group_signal_scores(
                    group_signals=prep["group_signals"],
                    params_by_id=prep["params_by_id"],
                    gscores=gscores.values())
                gsv_rows.extend(
                    (k[0], k[1], k[2], d_str, v)
                    for k, v in gsv_scores.items())

                # Índice por señal, UNA pasada por fecha: sin esto cada
                # estrategia rebarre los ~8000 scores del día y el costo
                # crece cuadrático con la densidad (lento en la era moderna)
                sv_by_signal: dict[int, dict] = {}
                for (sig_id, aid), sc in sv_scores.items():
                    sv_by_signal.setdefault(sig_id, {})[aid] = sc

                # Estrategias: mismos insumos que el camino por-fecha, pero
                # desde memoria (señales recién calculadas + as-of del barrido)
                for ctx in strat_ctx:
                    aids = set()
                    for sig_id in ctx["signal_ids"]:
                        aids.update(sv_by_signal.get(sig_id, ()))
                    groups_sub = {aid: asset_groups[aid] for aid in aids
                                  if aid in asset_groups}
                    operand_values: dict[tuple, dict] = {}
                    for t, key, res in ctx["operands"]:
                        if t == "indicator" and res == "current":
                            operand_values[(t, key, res)] = current_by_code.get(key, {})
                        elif t == "indicator":
                            operand_values[(t, key, res)] = snap.get(key, {})
                        elif t == "signal":
                            op_id = sig_id_by_key.get(key)
                            operand_values[(t, key, res)] = (
                                sv_by_signal.get(op_id, {})
                                if op_id is not None else {})
                    scored = rank_strategy_assets(
                        components=ctx["components"], asset_groups=groups_sub,
                        signal_scores=sv_scores, group_scores=gsv_scores,
                        filter_tree=ctx["tree"], operand_values=operand_values)
                    pcts = percent_ranks([score for _, score in scored])
                    sr_rows.extend(
                        (ctx["id"], aid, d_str, score, pct)
                        for (aid, score), pct in zip(scored, pcts))

                if d not in logged:
                    marker_rows.append((eval_kind, eval_ref, d_str))
                batch_dates.append(d)

                # Flush intermedio por volumen: en la era densa un chunk
                # entero acumularía ~2M filas (memoria + transacción gigante)
                if (len(sv_rows) + len(gsv_rows) + len(gs_rows)
                        + len(sr_rows)) >= _MAX_ROWS_PER_FLUSH:
                    _emit(batch_dates, sv_rows, gsv_rows, gs_rows,
                          sr_rows, marker_rows)
                    sv_rows, gsv_rows, gs_rows, sr_rows, marker_rows = \
                        [], [], [], [], []
                    batch_dates = []

            _emit(batch_dates, sv_rows, gsv_rows, gs_rows, sr_rows, marker_rows)

        except Exception as exc:
            s.rollback()
            logger.exception(
                "signal_backfill_range: chunk %s..%s falló", chunk[0], chunk[-1])
            errors.append({"date": f"{chunk[0]}..{chunk[-1]}",
                           "error": f"chunk {chunk[0]}..{chunk[-1]}: {exc}"})

    # Cierre del escritor: sentinel + join. Recién acá se sabe cuántas
    # fechas quedaron realmente persistidas (_ok_box lo suma el flush).
    if use_async and _writer is not None:
        if progress_cb:
            progress_cb(total, total, "guardando…")
        _wq.put(None)
        _writer.join()
    if _werrors:
        errors.append({"date": f"{dates[0]}..{dates[-1]}",
                       "error": f"escritor asíncrono: {_werrors[0]}"})

    return {"total": total, "success": _ok_box[0], "errors": errors}
