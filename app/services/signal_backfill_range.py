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
- Escritura por `app.models.signal_store`, que despacha entre las tablas
  ANCHAS (default: una columna por señal/estrategia) y las per-entidad
  sig_{id}/strat_res_{id} del flag apagado: el rebuild que cubre toda la
  historia limpia con TRUNCATE (inserción siempre sobre vacío — insertar en
  pobladas midió 3-5× más caro) y las unidades no compiten entre sí.

La MATEMÁTICA no vive acá: los evaluadores compartidos
(_evaluate_asset_signal_scores, rank_strategy_assets) son los mismos que usa
el camino por-fecha — ver tests/test_signal_range_parity.py.

Divergencia deliberada con el camino por-fecha (no es regresión): el DELETE
por fecha elimina filas obsoletas (señales que ya no puntúan ese día) que el
upsert por-fecha dejaría zombies.

group_scores YA NO se escribe acá: el Mapa de Tendencia lo calcula al vuelo
(group_score_service.group_scores_for), así que la tabla no se persiste.
"""
import logging
import queue
import random
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta
from types import SimpleNamespace

import sqlalchemy as sa
from sqlalchemy.exc import OperationalError

from app.database import Session as _DbSession
from app.database import get_session
from app.services import db_compat
from app.services.db_utils import delete_by_ranges
from app.models import (
    SignalEvalLog,
    Strategy,
)
from app.models import signal_store
from app.models.indicator_store import (
    ASOF_MAX_LOOKBACK_DAYS,
    CurrentIndicatorValue,
    get_ind_table,
)
from app.models.price import Price
from app.services import strategy_filter
from app.services.signal_service import (
    _evaluate_asset_signal_scores,
    _prepare_signals,
)
from app.services.strategy_service import percent_ranks, rank_strategy_assets

logger = logging.getLogger(__name__)

_CHUNK_DATES = 250   # ~1 año de ruedas por chunk (unidad de carga del barrido)

# Deadlock/lock-timeout que la app debe reintentar (escrituras concurrentes
# contra las mismas tablas — p.ej. una baja de activo que borra en cascada
# mientras este backfill inserta; ver _fund_worker en fundamental_service,
# mismo patrón). Sin esto un lock timeout abandona el chunk entero (un año
# de fechas), que reaparece como hueco en el próximo delta. Detección por
# dialecto en db_compat (errno InnoDB / SQLSTATE de PostgreSQL).
_is_retryable_lock_error = db_compat.is_retryable_lock_error
_MAX_LOCK_RETRIES = 3


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


def _load_sweep(s, code, window_start, window_end) -> _Sweep:
    try:
        tbl = get_ind_table(code)
    except sa.exc.NoSuchTableError:
        logger.warning("signal_backfill_range: tabla ind_%s no existe", code)
        return _Sweep([])
    rows = s.execute(
        sa.select(tbl.c.asset_id, tbl.c.date, tbl.c.value)
        # value IS NOT NULL: as-of fiel por columna (ver query_values_asof). En
        # una tabla ancha una fila puede tener ESTA columna en NULL (la escribió
        # otro código); sin el filtro entraría a .live y pisaría el último valor
        # válido. En las ind_{code} per-código (sin value NULL) es equivalente.
        .where(tbl.c.date >= window_start, tbl.c.date <= window_end,
               tbl.c.value.isnot(None))
        .order_by(tbl.c.date)
    ).fetchall()
    return _Sweep([(r[0], r[1], r[2]) for r in rows])


def _load_price_closes(s, d0, d1):
    """Filas (date, asset_id, close) del rango — para el virtual last_close."""
    return s.query(Price.date, Price.asset_id, Price.close).filter(
        Price.date >= d0, Price.date <= d1).all()


def _load_stored_scores(s, sig_id, d0, d1):
    """Filas (date, asset_id, score) de sig_{id} en el rango (strategy_only)."""
    t = signal_store.get_sig_table(sig_id)
    return s.execute(
        sa.select(t.c.date, t.c.asset_id, t.c.score)
        .where(t.c.date >= d0, t.c.date <= d1)).fetchall()


# Lectores paralelos: la lectura serial dominaba la corrida (medido 158s
# de 180s en strategy_only) y es I/O que libera el GIL (fetch por socket +
# conversión de filas en C del driver) — una tabla por thread paraleliza
# de verdad. PERO con 8 se midió sobre-paralelización (Codespace, 2 vCPU):
# los lectores le sacaban CPU/disco al propio servidor MariaDB mientras
# insertaba y la corrida con señales pasó de 5m10s a 6m50s (escritor +30%,
# productor 177s esperándolo). 3 mantiene el solape sin ahogar al server.
_READ_WORKERS = 3


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
              progress_cb=None, force=False, full_wipe=False,
              whole_history=False, strategy_only=False) -> dict:
    """Equivalente en rango del loop por-fecha de _signal_history_run.
    dates: lista ordenada de fechas a procesar (huecos + última).

    force: rebuild — limpieza ÚNICA al inicio y batches solo-INSERT.
    Borrar por batch sobre una tabla de decenas de millones de filas
    degrada progresivamente (el purge de InnoDB arrastra las filas muertas
    acumuladas toda la corrida: se midió 10s→32s por chunk con conteos
    iguales). whole_history: force sin horizonte — `dates` cubre TODA la
    historia, así que las tablas sig_{id}/strat_res_{id} del alcance se
    vacían enteras (TRUNCATE en MySQL: inserción siempre sobre tablas
    vacías); con horizonte se cae a ventanas de fechas.

    strategy_only (scope estrategia, elegido por el usuario cuando NO
    cambiaron señales/indicadores): las señales NO se re-evalúan ni se
    reescriben — sus scores se LEEN de sig_{id} por chunk (la historia de
    una señal no depende de la estrategia) — y solo
    se reconstruye strat_res_{id}. Los barridos de indicadores quedan
    reducidos a lo que el FILTRO de la estrategia necesita. Costo ∝ la
    estrategia, no ∝ la historia de sus señales."""
    s = get_session()

    # ── Contexto invariante de la corrida ─────────────────────────────────
    prep = _prepare_signals(s, only_ids)
    if prep is None:
        return {"total": 0, "success": 0, "errors": [], "unit": "fechas"}

    asset_groups = {
        a.id: strategy_filter.attributes_from_asset_row(a)
        for a in strategy_filter.asset_attributes_query(s).all()
    }

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
                SimpleNamespace(signal_id=c.signal_id, weight=c.weight)
                for c in strat.components
            ],
            "signal_ids": {c.signal_id for c in strat.components},
            "tree": tree,
            "operands": operands,
        })

    sig_id_by_key = {sig.key: sig.id for sig in prep["signals"]}

    # Códigos a barrer: señales + filtro (historic). En strategy_only solo el
    # filtro necesita indicadores (las señales se leen de la tabla).
    if strategy_only:
        sweep_codes = set(filter_hist_codes)
    else:
        sweep_codes = set(prep["hist_codes"]) | filter_hist_codes

    # Valores current (una vez: son el estado VIGENTE, no dependen de la fecha)
    current_by_code = _load_current_values(
        s, filter_current_codes if strategy_only
        else set(prep["nohist_codes"]) | filter_current_codes)

    need_last_close = "last_close" in prep["virtual_codes"]

    signal_ids_all  = [sig.id for sig in prep["signals"]]
    strat_ids       = [c["id"] for c in strat_ctx]

    # Ruteo a tablas anchas (design_sig_wide_tables.md). Con el flag OFF todo el
    # camino de escritura/lectura es idéntico al per-entidad de hoy.
    wide = signal_store.use_wide_signal_tables()
    # Rebuild TOTAL (todo el alcance: todas las señales y estrategias) → se puede
    # TRUNCAR la ancha e insertar plano (sin conflicto → sin bloat). Alcance
    # PARCIAL (una estrategia/señal) o delta → NULL de columnas + UPSERT.
    wide_full_rebuild = wide and force and whole_history and scope_kind is None
    _sig_cols   = signal_store.sig_columns(signal_ids_all)
    _strat_cols = signal_store.strat_columns(strat_ids)

    # Estructuras dinámicas del alcance: asegurarlas ANTES de arrancar el
    # escritor asíncrono (el thread escritor nunca hace DDL) y antes de las
    # lecturas de strategy_only. checkfirst: solo inspección si ya existen.
    if wide:
        signal_store.ensure_wide_signal_tables(bind=s.connection())
        for sig_id in signal_ids_all:
            signal_store.ensure_sig_column(sig_id, bind=s.connection())
        for st_id in strat_ids:
            signal_store.ensure_strat_columns(st_id, bind=s.connection())
    else:
        for sig_id in signal_ids_all:
            signal_store.ensure_sig_table(sig_id, bind=s.connection())
        for st_id in strat_ids:
            signal_store.ensure_strat_table(st_id, bind=s.connection())
    s.commit()

    total = len(dates)
    errors: list[dict] = []
    done = 0

    # ── Rebuild: limpieza única al inicio (después solo INSERTs) ──────────
    # whole_history (dates cubre toda la historia): las tablas sig_{id}/
    # strat_res_{id} del alcance se vacían enteras — TRUNCATE en MySQL/PG,
    # instantáneo y sin filas muertas que purgar. Con horizonte: DELETE por
    # VENTANAS DE FECHAS QUE AVANZAN (delete_by_ranges, convención
    # CLAUDE.md): la sentencia única corrió 400s+ reteniendo locks, y el
    # loop DELETE..LIMIT fue peor (O(n²) por re-escaneo de tombstones).
    # En strategy_only se vacía SOLO strat_res_{id}: las señales no se
    # tocan (no dependen de la estrategia).
    _WINDOW_DATES = 100

    def _date_windows():
        slices = (dates[i:i + _WINDOW_DATES]
                  for i in range(0, len(dates), _WINDOW_DATES))
        return [(str(w[0]), str(w[-1])) for w in slices]

    def _wipe_table(ws, name: str):
        db_compat.wipe_table(ws, name)

    def _initial_cleanup(ws):
        if not force:
            return
        windows = None if whole_history else _date_windows()
        # signal_eval_log del ALCANCE en reconstrucción (eval_kind/eval_ref): se
        # borra JUNTO con los datos. Antes se preservaba, pero si la corrida
        # moría a mitad las fechas ya vaciadas quedaban marcadas como evaluadas
        # → el delta las tomaba por hechas y NO las reparaba (hueco permanente y
        # silencioso). Borrándolas, un corte deja esas fechas SIN marcador y el
        # delta las rehace. Los markers de OTROS alcances no se tocan (filtro por
        # scope). Tabla diminuta (una fila por fecha/alcance): el DELETE acotado
        # no retiene locks como las sig_{id}, va directo (sin delete_by_ranges).
        ws.execute(sa.delete(SignalEvalLog.__table__).where(
            SignalEvalLog.scope_kind == eval_kind,
            SignalEvalLog.ref_id == eval_ref,
            SignalEvalLog.date >= dates[0],
            SignalEvalLog.date <= dates[-1]))
        if wide:
            # Rebuild TOTAL: truncar (después INSERT plano, sin bloat). Parcial/
            # horizonte: NULL de las columnas del alcance por ventanas (deja
            # intactas las de otras señales/estrategias); el UPSERT las repuebla.
            if wide_full_rebuild:
                _wipe_table(ws, signal_store.SIG_WIDE_TABLE)
                _wipe_table(ws, signal_store.STRAT_WIDE_TABLE)
            else:
                cols_windows = (
                    [(str(dates[0]), str(dates[-1]))] if whole_history
                    else windows)
                if not strategy_only:
                    signal_store.wide_null_columns_ranges(
                        ws, signal_store.SIG_WIDE_TABLE, _sig_cols, cols_windows)
                signal_store.wide_null_columns_ranges(
                    ws, signal_store.STRAT_WIDE_TABLE, _strat_cols, cols_windows)
            ws.commit()
            logger.info("signal_backfill_range: limpieza inicial de rebuild "
                        "ANCHO completada (%s)",
                        "truncate" if wide_full_rebuild else "null por columnas")
            return
        if not strategy_only:
            for sig_id in signal_ids_all:
                name = signal_store.sig_table_name(sig_id)
                if whole_history:
                    _wipe_table(ws, name)
                else:
                    delete_by_ranges(ws, name, "date", windows)
        for st_id in strat_ids:
            name = signal_store.strat_table_name(st_id)
            if whole_history:
                _wipe_table(ws, name)
            else:
                delete_by_ranges(ws, name, "date", windows)
        ws.commit()
        logger.info("signal_backfill_range: limpieza inicial de rebuild "
                    "completada (%s)",
                    "truncate por tabla" if whole_history
                    else "delete por ventanas")

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

    def _flush_once(ws, batch_dates, sv_by_sig, sr_by_strat, marker_rows):
        if wide:
            # Delta (no force): limpiar las columnas del alcance de las fechas del
            # batch (equivalente al DELETE de fila per-entidad). En rebuild la
            # limpieza ya la hizo _initial_cleanup (truncate o null por rango).
            if not force:
                if not strategy_only:
                    signal_store.wide_null_columns(
                        ws, signal_store.SIG_WIDE_TABLE, _sig_cols, batch_dates)
                signal_store.wide_null_columns(
                    ws, signal_store.STRAT_WIDE_TABLE, _strat_cols, batch_dates)
            # Rebuild total → INSERT plano (post-truncate, sin bloat); resto →
            # UPSERT por (fecha,activo).
            _write = (signal_store.wide_insert if wide_full_rebuild
                      else signal_store.wide_upsert)
            if not strategy_only:
                _write(ws, signal_store.SIG_WIDE_TABLE, _sig_cols,
                       signal_store.sig_wide_rows(sv_by_sig, signal_ids_all))
            _write(ws, signal_store.STRAT_WIDE_TABLE, _strat_cols,
                   signal_store.strat_wide_rows(sr_by_strat, strat_ids))
            _bulk_insert(ws, "signal_eval_log",
                         ("scope_kind", "ref_id", "date"), marker_rows)
            ws.commit()
            return

        if not force:
            dates_in = ", ".join(f"'{d}'" for d in batch_dates)
            for sig_id in signal_ids_all:
                if strategy_only:
                    break
                ws.execute(sa.text(
                    f"DELETE FROM {signal_store.sig_table_name(sig_id)} "
                    f"WHERE date IN ({dates_in})"))
            for st_id in strat_ids:
                ws.execute(sa.text(
                    f"DELETE FROM {signal_store.strat_table_name(st_id)} "
                    f"WHERE date IN ({dates_in})"))

        for sig_id, rows in sv_by_sig.items():
            _bulk_insert(ws, signal_store.sig_table_name(sig_id),
                         ("asset_id", "date", "score"), rows)
        for st_id, rows in sr_by_strat.items():
            _bulk_insert(ws, signal_store.strat_table_name(st_id),
                         ("asset_id", "date", "score", "pct"), rows)
        _bulk_insert(ws, "signal_eval_log",
                     ("scope_kind", "ref_id", "date"), marker_rows)
        ws.commit()

    def _flush(ws, batch_dates, sv_by_sig, sr_by_strat, marker_rows):
        """DELETE de las fechas del batch (solo en delta; el rebuild ya
        limpió todo al inicio) + INSERT masivo + commit. Las fechas ya
        flusheadas quedan persistidas aunque un batch posterior falle.

        Reintenta ante lock timeout/deadlock (db_compat): el DELETE+INSERT es
        idempotente, y la contención con otras escrituras (p.ej. una baja de
        activo borrando en cascada) suele ser transitoria."""
        if not batch_dates:
            return
        _tw0 = time.perf_counter()
        for attempt in range(_MAX_LOCK_RETRIES + 1):
            try:
                _flush_once(ws, batch_dates, sv_by_sig, sr_by_strat, marker_rows)
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
        _t_write[0] += time.perf_counter() - _tw0
        if progress_cb:
            # Fila "escritura" del panel: fechas ya PERSISTIDAS — muestra en
            # vivo cuánto viene retrasado el escritor respecto del productor
            progress_cb(done, total,
                        f"escritura: {_ok_box[0]}/{total} escritor "
                        f"t={_t_write[0]:.0f} "
                        f"retraso: {max(0, done - _ok_box[0])} fechas")
        logger.info(
            "signal_backfill_range: %s..%s (%d fechas): %d filas de señal, "
            "%d filas de estrategia",
            batch_dates[0], batch_dates[-1], len(batch_dates),
            sum(len(r) for r in sv_by_sig.values()),
            sum(len(r) for r in sr_by_strat.values()))

    # ── Escritor asíncrono (motores de producción: MySQL/MariaDB y PG) ────
    # El borrado/inserción es I/O de la base (libera el GIL, con MySQLdb y
    # con psycopg por igual): corre en un thread propio con SU sesión
    # mientras el productor computa el chunk siguiente en memoria (el
    # barrido as-of no depende del estado de la BD). Cola acotada (1): a lo
    # sumo un lote en espera además del que se computa — memoria acotada por
    # backpressure. La barrera borrar-antes-de-insertar es estructural:
    # limpieza inicial y flushes viven en el MISMO thread, en orden FIFO.
    # sqlite (tests) va sincrónico: misma semántica, sin concurrencia (la
    # paridad cubre el resultado final).
    use_async = db_compat.is_mysql(s) or db_compat.is_postgres(s)
    _ok_box = [0]
    _werrors: list = []
    _wq: queue.Queue = queue.Queue(maxsize=1)

    # Instrumentación: desglose lectura / cómputo / escritura para decidir
    # dónde atacar (¿read-bound? ¿escritor como cuello? ¿cómputo?). Celdas
    # de lista: _t_write la suma el thread escritor, el resto el productor.
    _t_read, _t_compute, _t_wait, _t_write = [0.0], [0.0], [0.0], [0.0]

    # Pool de LECTORES (motores reales — MySQL y PostgreSQL liberan el GIL
    # en el I/O por igual): una tabla por thread, cada thread con su propia
    # sesión (scoped session = thread-local). sqlite (tests) lee inline con
    # la sesión única — mismos datos, la paridad cubre el resultado (mismo
    # criterio que el escritor asíncrono).
    _used_readers: set = set()   # threads lectores que trabajaron de verdad
    _readers = (ThreadPoolExecutor(max_workers=_READ_WORKERS,
                                   thread_name_prefix="sigread")
                if use_async else None)

    def _run_reads(tasks):
        """tasks: [(fn, args)] con fn(session, *args) → filas. Devuelve los
        resultados EN ORDEN. Cada task corre con la sesión de su thread y
        la limpia al salir (remove = cierra y devuelve la conexión al pool,
        sin snapshots InnoDB retenidos entre chunks)."""
        if _readers is None:
            return [fn(s, *args) for fn, args in tasks]

        def _wrap(fn, args):
            _used_readers.add(threading.current_thread().name)
            rs = get_session()
            try:
                return fn(rs, *args)
            finally:
                _DbSession.remove()

        futures = [_readers.submit(_wrap, fn, args) for fn, args in tasks]
        return [f.result() for f in futures]

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

    def _emit(batch_dates, sv_by_sig, sr_by_strat, marker_rows):
        """Entrega un lote al escritor (asíncrono) o flushea inline (sync).
        Si el escritor ya falló, descarta el lote — el error se reporta al
        cerrar la corrida."""
        if not batch_dates:
            return
        _te0 = time.perf_counter()
        if use_async:
            if not _werrors:
                # put bloquea si la cola (1) está llena: este tiempo ES la
                # espera del productor al escritor (backpressure)
                _wq.put((batch_dates, sv_by_sig, sr_by_strat, marker_rows))
        else:
            _flush(s, batch_dates, sv_by_sig, sr_by_strat, marker_rows)
        _t_wait[0] += time.perf_counter() - _te0

    # Filas por ETAPA en el panel (protocolo "{fila}: dn/tn tag" de _cb en
    # data_center_callbacks — mismo render que el detalle de indicadores,
    # con la identidad del thread por fila): lectura avanza por chunks,
    # cómputo por fechas evaluadas, escritura por fechas persistidas.
    n_chunks = (total + _CHUNK_DATES - 1) // _CHUNK_DATES
    if progress_cb:
        progress_cb(0, total, f"lectura: 0/{n_chunks} lectores t=0")
        progress_cb(0, total, f"cómputo: 0/{total} productor t=0")
        progress_cb(0, total, f"escritura: 0/{total} escritor t=0")

    # ── Chunks ────────────────────────────────────────────────────────────
    for start in range(0, total, _CHUNK_DATES):
        if _werrors:
            break  # el escritor murió: computar más lotes sería tirarlos
        chunk = dates[start:start + _CHUNK_DATES]
        window_start = chunk[0] - timedelta(days=ASOF_MAX_LOOKBACK_DAYS)
        window_end   = chunk[-1]

        try:
            _tr0 = time.perf_counter()
            # Todas las lecturas del chunk en UN fan-out (una tabla por
            # task): barridos de indicadores + prefetch de cierres +
            # (strategy_only) señales guardadas por tabla — la historia de una
            # señal no depende de la estrategia, por eso en strategy_only se
            # LEE en vez de re-evaluarse.
            read_tasks: list = [
                ("sweep", code, (_load_sweep, (code, window_start, window_end)))
                for code in sorted(sweep_codes)]
            if need_last_close and not strategy_only:
                read_tasks.append(
                    ("closes", None, (_load_price_closes,
                                      (chunk[0], window_end))))
            if strategy_only:
                if wide:
                    # Un scan de la ancha trae todas las señales del alcance (una
                    # columna por señal) en vez de N tablas — as-of fiel por
                    # columna (IS NOT NULL) dentro de load_wide_signal_scores.
                    read_tasks.append(
                        ("sigwide", None,
                         (signal_store.load_wide_signal_scores,
                          (signal_ids_all, chunk[0], chunk[-1]))))
                else:
                    read_tasks.extend(
                        ("sig", sig_id, (_load_stored_scores,
                                         (sig_id, chunk[0], chunk[-1])))
                        for sig_id in signal_ids_all)

            fetched = _run_reads([t[2] for t in read_tasks])

            sweeps: dict = {}
            closes_by_date: dict = {}
            stored_sv_by_date: dict = {}
            for (kind, key, _), rows in zip(read_tasks, fetched):
                if kind == "sweep":
                    sweeps[key] = rows
                elif kind == "closes":
                    for dt, aid, close in rows:
                        if close is not None:
                            closes_by_date.setdefault(dt, {})[aid] = float(close)
                elif kind == "sigwide":
                    for dt, aid, sid, sc in rows:
                        if sc is not None:
                            stored_sv_by_date.setdefault(
                                dt, {})[(sid, aid)] = float(sc)
                else:  # sig (per-entidad)
                    for dt, aid, sc in rows:
                        if sc is not None:
                            stored_sv_by_date.setdefault(
                                dt, {})[(key, aid)] = float(sc)

            if progress_cb:
                n_rd = len(_used_readers)
                rd_tag = (f"w1..w{n_rd}" if n_rd > 1
                          else "w1" if n_rd == 1 else "productor")
                progress_cb(done, total,
                            f"lectura: {start // _CHUNK_DATES + 1}"
                            f"/{n_chunks} {rd_tag} t={_t_read[0]:.0f}"
                            f" {chunk[0]}..{chunk[-1]}")

            _t_read[0] += time.perf_counter() - _tr0

            sv_by_sig: dict[int, list] = {}
            sr_by_strat: dict[int, list] = {}
            marker_rows: list = []
            batch_dates: list = []
            flush_rows = 0  # contador para el flush intermedio por volumen

            _tc0, _w0 = time.perf_counter(), _t_wait[0]
            for d in chunk:
                done += 1
                d_str = str(d)
                if progress_cb:
                    # segundos vivos de cómputo: acumulado + lo que va de
                    # este chunk, descontando esperas al escritor
                    live = (_t_compute[0] + (time.perf_counter() - _tc0)
                            - (_t_wait[0] - _w0))
                    progress_cb(done, total,
                                f"cómputo: {done}/{total} productor "
                                f"t={live:.0f} {d_str}")

                for sw in sweeps.values():
                    sw.advance(d)

                # Snapshots as-of de todos los códigos barridos
                snap = {code: sw.snapshot_asof(d) for code, sw in sweeps.items()}

                if strategy_only:
                    # Señales LEÍDAS (no evaluadas, no escritas)
                    sv_scores = stored_sv_by_date.get(d, {})
                else:
                    # isnaps para señales de activo (hist + current-si-es-hoy
                    # + virtual)
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
                        signals=prep["signals"],
                        asset_signals=prep["asset_signals"],
                        params_by_id=prep["params_by_id"],
                        compiled_by_id=prep["compiled_by_id"], isnaps=isnaps)
                    for (sig_id, aid), v in sv_scores.items():
                        sv_by_sig.setdefault(sig_id, []).append(
                            (aid, d_str, v))
                    flush_rows += len(sv_scores)

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
                        signal_scores=sv_scores,
                        filter_tree=ctx["tree"], operand_values=operand_values)
                    pcts = percent_ranks([score for _, score in scored])
                    sr_by_strat.setdefault(ctx["id"], []).extend(
                        (aid, d_str, score, pct)
                        for (aid, score), pct in zip(scored, pcts))
                    flush_rows += len(scored)

                # En rebuild (force) SIEMPRE se re-marca: _initial_cleanup borró
                # los markers del alcance, así que reinsertarlos por chunk deja
                # marcador y dato en la MISMA transacción — un corte nunca separa
                # "marcado" de "escrito". En delta se respeta `logged` (no
                # reinsertar los que ya estaban).
                if force or d not in logged:
                    marker_rows.append((eval_kind, eval_ref, d_str))
                batch_dates.append(d)

                # Flush intermedio por volumen: en la era densa un chunk
                # entero acumularía ~2M filas (memoria + transacción gigante)
                if flush_rows >= _MAX_ROWS_PER_FLUSH:
                    _emit(batch_dates, sv_by_sig, sr_by_strat, marker_rows)
                    sv_by_sig, sr_by_strat = {}, {}
                    marker_rows = []
                    batch_dates = []
                    flush_rows = 0

            _emit(batch_dates, sv_by_sig, sr_by_strat, marker_rows)
            # cómputo = loop menos lo que _emit pasó bloqueado esperando
            _t_compute[0] += ((time.perf_counter() - _tc0)
                              - (_t_wait[0] - _w0))

        except Exception as exc:
            s.rollback()
            logger.exception(
                "signal_backfill_range: chunk %s..%s falló", chunk[0], chunk[-1])
            errors.append({"date": f"{chunk[0]}..{chunk[-1]}",
                           "error": f"chunk {chunk[0]}..{chunk[-1]}: {exc}"})

    if _readers is not None:
        _readers.shutdown(wait=True)

    # Cierre del escritor: sentinel + join. Recién acá se sabe cuántas
    # fechas quedaron realmente persistidas (_ok_box lo suma el flush).
    if use_async and _writer is not None:
        if progress_cb:
            progress_cb(total, total, "guardando…")
        _tj0 = time.perf_counter()
        _wq.put(None)
        _writer.join()
        _t_wait[0] += time.perf_counter() - _tj0
    if _werrors:
        errors.append({"date": f"{dates[0]}..{dates[-1]}",
                       "error": f"escritor asíncrono: {_werrors[0]}"})

    timings = {"read_s": round(_t_read[0], 1),
               "compute_s": round(_t_compute[0], 1),
               "wait_s": round(_t_wait[0], 1),
               "write_s": round(_t_write[0], 1)}
    # La suma lectura+cómputo+espera ≈ tiempo de pared del productor; la
    # escritura corre SOLAPADA en el thread escritor (solo la parte que
    # asoma en "espera" frenó la corrida). En sqlite (sync) espera ⊇
    # escritura. Con esto se decide dónde atacar: read-bound → lecturas;
    # espera alta → escritores paralelos por tabla; cómputo alto → ProcessPool.
    logger.info(
        "signal_backfill_range: tiempos — lectura %.1fs, cómputo %.1fs, "
        "espera al escritor %.1fs (escritura solapada %.1fs)",
        timings["read_s"], timings["compute_s"], timings["wait_s"],
        timings["write_s"])

    return {"total": total, "success": _ok_box[0], "errors": errors,
            "timings": timings, "unit": "fechas"}
