"""
Verifica que los valores guardados en ind_{code} (escritos por el sistema
de delta — _DELTA_TAIL_MODE, checksums, huecos, activos "vacíos") coincidan
con un recálculo fresco desde cero, para una muestra de activos reales.

Solo lee de la base (SELECT) — nunca escribe, nunca trunca, no toca
force=True ni ninguna tabla ind_*. Seguro de correr contra producción en
cualquier momento, cuantas veces se quiera.

Cómo funciona: para cada (código, activo), llama a la misma función de
cómputo que usa backfill_indicator (_BACKFILL_FNS[code]) directo en
memoria, sin pasar por el camino rápido/lento — el resultado es
equivalente a lo que produciría un rebuild completo (force=True) para ese
activo puntual. Compara esa serie "fresca" contra lo que hoy está
guardado en ind_{code}, fecha por fecha.

También hace chequeos de cordura (¿el valor tiene sentido, sin importar
cómo se calculó?) — RSI fuera de [0,100], un trend_* que no es ninguna
categoría conocida, un retorno diario de +50000%. Esto es independiente
de la comparación delta-vs-fresco: agarra bugs de FÓRMULA, no de caché
(si la fórmula está mal, el delta y el recálculo fresco van a coincidir
igual, calculando ambos el mismo valor incorrecto).

Y desde la extensión a fundamentales: mismo patrón para
_compute_quarterly_ratios/_compute_daily_ratios (ind_fundamental_*), con
el mismo motivo pero un riesgo distinto — el delta de fundamentales
(_backfill_fund_indicator) no tiene el caché sofisticado de indicadores
técnicos, así que no puede repetir esos bugs, pero tampoco vuelve a
calcular una fecha ya escrita si el trimestre correspondiente se revisa
más tarde (salvo el último trimestre, tratado como "preliminar").

Dos consumidores comparten esta lógica: scripts/verify_delta_correctness.py
(CLI) y app/callbacks/admin_verify_callbacks.py (panel /admin/verify).
"""
import random
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import date as _date_type, timedelta

import numpy as np
import pandas as pd
import sqlalchemy as sa

from app.database import get_session
from app.models import Asset, FundamentalQuarterly, Price
from app.models.indicator_store import get_ind_table
# Valores posibles por indicador categórico: catálogo compartido con el
# constructor de filtros de estrategia (ver indicator_catalog.py).
from app.services.indicator_catalog import CATEGORICAL_VALUES as _CATEGORICAL_VALUES
from app.services.fundamental_service import (
    _ALL_FUND_CODES, _FUND_DAILY_CODES, _Quarter, _compute_daily_ratios,
    _compute_quarterly_ratios, _daily_ratio_series, _ref_1y_ord,
)
# Harness compartido del pool por lotes de activos (ver technical_service /
# process_pool): la verificación reusa la misma decisión threads/procesos y
# el particionador — la unidad de trabajo pasa de "un activo" a "un lote".
from app.services.technical_service import (
    _BACKFILL_FNS, _DELTA_TAIL_MODE, _get_regime_config,
    _get_volatility_config, _n_batches, _partition_assets, _resample_ohlc,
    _series_dates_values, _use_process_pool,
)

# Mismo criterio que _UPDATE_WORKERS en fundamental_service.py: cada activo
# es DB I/O (libera el GIL) + cómputo pandas/numpy (libera el GIL en la
# parte vectorizada) — gana velocidad real con threads, aunque no al nivel
# de multiprocessing puro (mismo techo del GIL ya anotado para el pool de
# cómputo de indicadores real, ver project_pendientes).
_VERIFY_WORKERS = 4

_TOL = 0.01  # tolerancia numérica: mismo redondeo que usa el sistema (.round(2))
# Complementa _TOL para magnitudes grandes: ind_fundamental_* guarda en una
# columna Float (FLOAT de MySQL, precisión simple, ~7 dígitos significativos)
# — un ratio en pesos argentinos/chilenos de 5-6 cifras ya pierde más de
# 0.01 de precisión en el redondeo de la propia columna, sin que eso sea
# un bug de cálculo. _TOL solo alcanza para valores chicos.
_REL_TOL = 1e-4

# ── Chequeos de cordura: ¿el valor tiene sentido, sin importar cómo se
# calculó? Límites deliberadamente laxos — el objetivo es atrapar lo
# obviamente roto (inf, signo invertido, error de unidades), no discutir
# si un valor extremo pero real es "razonable". Un activo genuinamente
# muy volátil no tiene que disparar un falso positivo acá.
_NUMERIC_BOUNDS: dict[str, tuple[float, float]] = {
    "rsi_daily": (0, 100), "rsi_weekly": (0, 100), "rsi_monthly": (0, 100),
    "atr_percentile_daily": (0, 100), "atr_percentile_weekly": (0, 100),
    "atr_percentile_monthly": (0, 100),
    # dist_sma20/50/200: (precio-sma)/sma*100 — distancia PORCENTUAL, no
    # z-score. Para activos volátiles (small caps, cripto) puede pasar
    # cómodamente 100-200% sin ser un bug — límite generoso.
    "dist_sma20": (-500, 2000), "dist_sma50": (-500, 2000), "dist_sma200": (-500, 2000),
    # dist_optimal_sma_*: (precio-sma)/desvío — esto sí es un z-score,
    # límite ajustado tiene sentido acá.
    "dist_optimal_sma_daily": (-50, 50), "dist_optimal_sma_weekly": (-50, 50),
    "dist_optimal_sma_monthly": (-50, 50),
    "return_daily": (-100, 2000),
    "return_monthly": (-100, 5000), "return_quarterly": (-100, 5000),
    "return_yearly": (-100, 20000), "return_52w": (-100, 20000),
    "relative_strength_52w": (-20000, 20000),
    # fundamentales: _safe_div_r devuelve fracciones (0.1 = 10%), no %
    "fundamental_net_margin": (-100, 100), "fundamental_gross_margin": (-100, 100),
    "fundamental_operating_margin": (-100, 100), "fundamental_roic": (-100, 100),
    "fundamental_debt_to_equity": (-10000, 10000),
    "fundamental_revenue_growth_yoy": (-1000, 100000),
    "fundamental_eps_growth_yoy": (-1000, 100000),
    "fundamental_net_income_growth_yoy": (-1000, 100000),
    "fundamental_pe_growth_yoy": (-1000, 100000),
    "fundamental_pe_ttm": (-100000, 100000), "fundamental_pb": (-100000, 100000),
    "fundamental_ps_ttm": (-100000, 100000),
}



# Categoría de cada fila de diferencia — separa dos cosas distintas que
# antes quedaban mezcladas en la misma lista:
#   "calc"   → guardado != recalculado: el propósito real de esta
#              herramienta, sospecha de bug de caché/delta.
#   "sanity" → guardado == recalculado pero el valor no tiene sentido
#              (fuera de rango / categoría desconocida): la fórmula
#              calculó lo mismo que ya estaba guardado, así que NO es un
#              bug de caché — es un dato de entrada raro (o, más raro
#              todavía, un bug en la fórmula misma, pero tampoco algo que
#              el sistema de delta pueda "cachear mal"). Ver hallazgos
#              reales: ITX.MC (precio corrupto en la fuente) y CMPC.SN
#              (P/E TTM con <4 trimestres — ya no se calcula, ver
#              _compute_daily_ratios).
_CALC_REASONS = frozenset({
    "solo en DB (¿debería haberse borrado?)",
    "falta en DB (¿el delta no la escribió?)",
    "valor distinto",
})


def _diff_category(kind: str) -> str:
    return "calc" if kind in _CALC_REASONS else "sanity"


def check_sanity(code: str, value) -> str | None:
    """None si el valor es razonable para ese código; si no, una
    descripción corta de qué límite violó."""
    if value is None:
        return None
    if code in _CATEGORICAL_VALUES:
        if str(value) not in _CATEGORICAL_VALUES[code]:
            return f"categoría desconocida para {code}: {value!r}"
        return None
    bounds = _NUMERIC_BOUNDS.get(code)
    if bounds is None:
        return None
    try:
        v = float(value)
    except (TypeError, ValueError):
        return f"se esperaba numérico para {code}, vino {value!r}"
    lo, hi = bounds
    if not (lo <= v <= hi):
        return f"fuera de rango [{lo},{hi}] para {code}: {v}"
    return None


def _load_price_df(session, asset_id: int) -> pd.DataFrame:
    rows = session.execute(
        sa.select(Price.date, Price.close, Price.high, Price.low)
        .where(Price.asset_id == asset_id)
        .order_by(Price.date.asc())
    ).all()
    return pd.DataFrame(rows, columns=["date", "close", "high", "low"])


def _prefetch_stored(session, codes: list, asset_ids: list) -> dict:
    """Una query por código (no por combinación código×activo, ver
    _stored_values) — para una corrida completa (24 códigos x 500 activos)
    esto es 24 queries en vez de 12000. code -> {asset_id: {date: value}}."""
    out: dict = {}
    if not asset_ids:
        return {code: {} for code in codes}
    for code in codes:
        t = get_ind_table(code)
        rows = session.execute(
            sa.select(t.c.asset_id, t.c.date, t.c.value)
            .where(t.c.asset_id.in_(asset_ids))
            .where(t.c.value.isnot(None))  # tabla ancha: ignorar filas donde
                                           # esta columna es NULL (la escribió
                                           # otro código de la cadencia); en
                                           # per-código es no-op
        ).all()
        by_asset: dict = {}
        for aid, d, v in rows:
            by_asset.setdefault(aid, {})[d] = v
        out[code] = by_asset
    return out


def _values_equal(fresh, stored) -> bool:
    try:
        f, s = float(fresh), float(stored)
    except (TypeError, ValueError):
        return str(fresh) == str(stored)
    diff = abs(f - s)
    return diff <= _TOL or diff <= _REL_TOL * max(abs(f), abs(s))


def verify_asset_code(session, code: str, asset_id: int, df, df_w, df_m,
                      regime_cfg, vol_cfg, stored: dict) -> list:
    """Devuelve la lista de diferencias (fecha, motivo, guardado, fresco,
    categoría) — ver _diff_category. df_w/df_m y stored se calculan una
    sola vez por activo (ver _verify_one_asset) en vez de por cada código."""
    compute_fn = _BACKFILL_FNS[code]
    values = compute_fn(
        df=df, df_w=df_w, df_m=df_m,
        regime_cfg=regime_cfg, vol_cfg=vol_cfg,
        session=session, asset_id=asset_id,
        price_cache=None, best_sma_cache=None,
    )
    dates_list, vals_list = _series_dates_values(values, df)
    fresh = {d: v for d, v in zip(dates_list, vals_list) if pd.notna(v)}

    diffs = []
    for d in sorted(set(fresh) | set(stored)):
        fv, sv = fresh.get(d), stored.get(d)
        if fv is None and sv is not None:
            kind = "solo en DB (¿debería haberse borrado?)"
            diffs.append((d, kind, sv, fv, _diff_category(kind)))
        elif fv is not None and sv is None:
            kind = "falta en DB (¿el delta no la escribió?)"
            diffs.append((d, kind, sv, fv, _diff_category(kind)))
        elif not _values_equal(fv, sv):
            kind = "valor distinto"
            diffs.append((d, kind, sv, fv, _diff_category(kind)))
        if fv is not None:
            sanity = check_sanity(code, fv)
            if sanity:
                diffs.append((d, sanity, sv, fv, _diff_category(sanity)))
    return diffs


def pick_sample_ids(session, sample: int | None) -> list:
    """sample=None: todos los activos (usado por run_full_verification_and_store,
    no por el panel /admin/verify — ahí siempre se pasa un número)."""
    all_ids = [r[0] for r in session.execute(sa.select(Asset.id)).all()]
    if sample is None:
        return all_ids
    return random.sample(all_ids, min(sample, len(all_ids)))


def ids_from_tickers(session, tickers: list) -> tuple[list, list]:
    """Devuelve (asset_ids, tickers_no_encontrados)."""
    rows = session.execute(
        sa.select(Asset.id, Asset.ticker).where(Asset.ticker.in_(tickers))
    ).all()
    found = {t: aid for aid, t in rows}
    missing = [t for t in tickers if t not in found]
    return list(found.values()), missing


def _verify_one_asset(asset_id: int, ticker: str, codes: list,
                      regime_cfg, vol_cfg, stored_by_code: dict,
                      session=None) -> list:
    """Verifica TODOS los codes para un único activo. df_w/df_m se resamplean
    una sola vez por activo, no una vez por código (antes verify_asset_code
    lo repetía).

    session: si se pasa (desde _verify_batch), NO abre ni cierra sesión
    propia — el LOTE la administra (una sola sesión por lote, para que
    regime_cfg/vol_cfg sigan vivos y no se reabra por activo). Sin session
    (uso directo, p.ej. tests) abre y libera su propia sesión."""
    own = session is None
    s = session or get_session()
    try:
        df = _load_price_df(s, asset_id)
        if df.empty:
            return []
        df_w = _resample_ohlc(df, "W")
        df_m = _resample_ohlc(df, "M")
        out = []
        for code in codes:
            stored = stored_by_code.get(code, {}).get(asset_id, {})
            diffs = verify_asset_code(s, code, asset_id, df, df_w, df_m,
                                      regime_cfg, vol_cfg, stored)
            if diffs:
                out.append({"code": code, "asset_id": asset_id,
                           "ticker": ticker, "diffs": diffs})
        return out
    finally:
        if own:
            from app.database import Session as _ScopedSession
            _ScopedSession.remove()


def _verify_batch(batch_asset_ids: list, ticker_map: dict, codes: list) -> dict:
    """Unidad de trabajo del pool: verifica un LOTE de activos (todos los
    códigos). Auto-contenido — carga sus PROPIOS regime/vol cfg y el prefetch
    del lote — así corre idéntico en un thread del padre o en un proceso hijo
    (spawn), sin recibir cachés completos por pickle ni objetos ORM. Una sola
    sesión para todo el lote.

    A propósito NO atrapa excepciones: un error debe PROPAGAR y cortar toda
    la corrida (como el código por-activo anterior), no devolver resultados
    vacíos. Si no, update_flags_for_assets leería "sin resultados" como "sin
    hallazgos" y BORRARÍA la marca de activos que en realidad no se
    verificaron. Mejor una corrida abortada (marcas intactas) que marcas
    silenciosamente incorrectas."""
    from app.database import Session as _ScopedSession
    s = get_session()
    try:
        regime_cfg = _get_regime_config()
        vol_cfg    = _get_volatility_config()
        stored_by_code = _prefetch_stored(s, codes, batch_asset_ids)
        out = []
        for aid in batch_asset_ids:
            out.extend(_verify_one_asset(
                aid, ticker_map.get(aid, "?"), codes,
                regime_cfg, vol_cfg, stored_by_code, session=s))
        return {"results": out, "n_assets": len(batch_asset_ids)}
    finally:
        _ScopedSession.remove()


def _run_batched(asset_ids: list, codes: list, ticker_map: dict, batch_fn,
                 progress_cb, total_work: int) -> list:
    """Corre batch_fn sobre LOTES de asset_ids, en threads o procesos según
    _use_process_pool (mismo criterio y harness que el backfill de
    indicadores). Cada lote es auto-contenido; el padre solo particiona y
    agrega. Progreso GRUESO por lote completado. Devuelve la lista plana de
    results.

    Un lote que falla (incluido BrokenProcessPool) PROPAGA y corta la corrida
    —no se traga— para que update_flags_for_assets nunca marque como
    'verificados sin hallazgos' activos que en realidad no se procesaron."""
    n = len(asset_ids)
    if n == 0:
        return []
    use_procs, n_procs = _use_process_pool(n)
    workers = n_procs if use_procs else _VERIFY_WORKERS
    batches = _partition_assets(asset_ids, {aid: 1 for aid in asset_ids},
                                _n_batches(n, workers))
    results: list = []
    done = [0]
    lock = threading.Lock()

    def _consume(out: dict) -> None:
        if not out:
            return
        results.extend(out.get("results", []))
        with lock:
            done[0] += out.get("n_assets", 0) * len(codes)
            d = done[0]
        if progress_cb:
            progress_cb(d, max(total_work, 1), "")

    def _tm(b):
        return {aid: ticker_map.get(aid, "?") for aid in b}

    if use_procs:
        from app.config import BASE_DIR, Config
        from app.services import process_pool as _pp
        with _pp.make_executor(min(len(batches), n_procs), str(BASE_DIR),
                               Config.IND_CHILD_DB_POOL, Config.LOG_LEVEL) as pool:
            futures = [pool.submit(batch_fn, b, _tm(b), codes) for b in batches]
            for f in as_completed(futures):
                _consume(f.result())   # propaga si el lote/hijo falló
    else:
        with ThreadPoolExecutor(max_workers=min(len(batches), _VERIFY_WORKERS)) as pool:
            futures = [pool.submit(batch_fn, b, _tm(b), codes) for b in batches]
            for f in as_completed(futures):
                _consume(f.result())
    return results


def run_verification(codes: list | None = None, sample: int | None = 30,
                     tickers: list | None = None, asset_ids: list | None = None,
                     progress_cb=None) -> dict:
    """Corre la verificación completa.

    codes: lista de códigos a chequear (default: todos los de _DELTA_TAIL_MODE
    que tengan función de backfill).
    asset_ids: si se pasa, verifica exactamente esos activos (tal cual,
    sin resolver tickers ni muestrear) — usado por update_flags_for_assets
    para re-verificar un subconjunto puntual (p. ej. los ya marcados).
    tickers: si se pasa (y asset_ids no), verifica esos activos puntuales
    en vez de una muestra al azar (sample se ignora).
    progress_cb(cur, tot, label): opcional, para barra de progreso en UI.

    Devuelve {"codes", "asset_ids", "missing_tickers", "combos", "results"}
    — "results" es una lista de {"code", "asset_id", "ticker", "diffs"}
    solo para las combinaciones que SÍ tuvieron diferencias."""
    s = get_session()
    codes = [c for c in (codes or list(_DELTA_TAIL_MODE)) if c in _BACKFILL_FNS]

    missing_tickers = []
    if asset_ids is not None:
        pass
    elif tickers:
        asset_ids, missing_tickers = ids_from_tickers(s, tickers)
    else:
        asset_ids = pick_sample_ids(s, sample)

    ticker_map = {a.id: a.ticker for a in
                  s.query(Asset).filter(Asset.id.in_(asset_ids)).all()}

    total_work = len(codes) * len(asset_ids)
    if progress_cb:
        progress_cb(0, max(total_work, 1), "")

    # El prefetch de valores guardados ya NO se carga acá (era un dict enorme
    # en el padre): cada lote carga su propio slice. Pero SÍ se aseguran las
    # filas de regime/vol config una sola vez —_get_*_config crea un default
    # si falta— para que los lotes concurrentes no choquen al crearlo cada uno.
    _get_regime_config()
    _get_volatility_config()
    results = _run_batched(asset_ids, codes, ticker_map, _verify_batch,
                           progress_cb, total_work)

    return {
        "codes": codes, "asset_ids": asset_ids,
        "missing_tickers": missing_tickers,
        "combos": total_work, "results": results,
    }


# ── Fundamentales: mismo patrón, otra fuente de cómputo ──────────────────────

def _load_quarters(session, asset_id: int) -> list:
    rows = (session.query(FundamentalQuarterly)
            .filter_by(asset_id=asset_id)
            .order_by(FundamentalQuarterly.period_date.asc())
            .all())
    return [_Quarter(**{f: getattr(q, f) for f in _Quarter._fields}) for q in rows]


def _load_fund_price_rows(session, asset_id: int) -> list:
    rows = session.execute(
        sa.select(Price.date, Price.close)
        .where(Price.asset_id == asset_id, Price.close.isnot(None))
        .order_by(Price.date.asc())
    ).all()
    return [(d, float(c)) for d, c in rows]


def _current_ratio_fresh(quarters: list, price_rows: list) -> dict:
    """Reproduce _compute_current_ratios (fundamental_service.py) en modo
    solo lectura, a partir de quarters/price_rows ya cargados.

    _compute_current_ratios escribe TODOS los ratios (trimestrales y
    diarios) con fecha de HOY usando el último trimestre + último precio
    disponible, sea o no hoy un cierre de trimestre o una fecha con precio
    propio — es el equivalente fundamental de compute_current_indicators
    del lado técnico. Sin reproducir este cálculo acá, la fila "vigente"
    de cualquier activo/código aparece como diferencia fantasma ("solo en
    DB") porque ni el camino trimestral ni el diario de abajo la generan."""
    if not quarters:
        return {}
    idx    = len(quarters) - 1
    values = dict(_compute_quarterly_ratios(quarters, idx))

    price = price_rows[-1][1] if price_rows else None
    if price:
        today   = _date_type.today()
        ref_ord = _ref_1y_ord(today)
        target  = today - timedelta(days=365)
        px_1y   = next((c for d, c in reversed(price_rows) if d <= target), None)
        if px_1y:
            p_ords, p_closes = np.array([ref_ord]), np.array([float(px_1y)])
        else:
            p_ords, p_closes = np.array([], dtype=np.int64), np.array([])
        q_ords = np.array([q.period_date.toordinal() for q in quarters])
        values.update(_compute_daily_ratios(
            float(price), quarters, q_ords, idx, p_ords, p_closes, ref_ord,
        ))
    return {k: v for k, v in values.items() if v is not None}


def _current_ratio_diff_entry(current_val, stored: dict, today):
    """Bajo qué fecha agregar el valor "vigente" recalculado a `fresh`
    para que el loop de comparación de verify_asset_ratio_code lo evalúe.
    None solo si no hay valor vigente que comparar.

    El vigente se reescribe con la fecha del día en que corrió
    producción, no una fecha fija — comparar contra "hoy" a secas daría
    una diferencia falsa cada vez que la verificación no corre el mismo
    día que el último refresh de producción (prácticamente siempre). Por
    eso se apunta a la fecha más reciente YA guardada (si existe): el
    loop de abajo compara los VALORES con _values_equal, así que si
    coinciden no genera ningún diff pase lo que pase con la fecha —
    NO hay que "saltearse" el agregado cuando coinciden (eso dejaría la
    fecha de `stored` sin contraparte en `fresh` y el loop la marcaría
    como "solo en DB" igual)."""
    if current_val is None:
        return None
    target = max(stored) if stored else today
    return target, current_val


def _compute_quarterly_by_idx(quarters: list) -> list:
    """Todos los ratios trimestrales de cada trimestre, calculados una sola
    vez (ver _verify_one_fund_asset) — antes verify_asset_ratio_code llamaba
    a _compute_quarterly_ratios(quarters, idx) una vez POR CÓDIGO para cada
    idx, aunque esa función ya calcula los 7 códigos trimestrales juntos."""
    return [_compute_quarterly_ratios(quarters, idx) for idx in range(len(quarters))]


def _compute_daily_series_by_code(quarters: list, q_ords, price_rows: list) -> dict:
    """Series diarias de los 4 códigos _FUND_DAILY_CODES, calculadas una
    sola vez por activo (_daily_ratio_series ya las devuelve juntas) —
    antes se recalculaban las 4 series completas por cada código individual."""
    if not price_rows:
        return {code: {} for code in _FUND_DAILY_CODES}
    dates_seq       = [d for d, _ in price_rows]
    price_dates_ord = np.array([d.toordinal() for d, _ in price_rows])
    price_closes    = np.array([c for _, c in price_rows])
    series = _daily_ratio_series(quarters, q_ords, dates_seq, price_dates_ord, price_closes)
    return {
        code: {d: v for d, v in zip(dates_seq, series[code]) if not np.isnan(v)}
        for code in _FUND_DAILY_CODES
    }


def verify_asset_ratio_code(code: str, asset_id: int, quarters: list,
                            quarterly_by_idx: list, daily_series: dict,
                            current_ratios: dict, stored: dict) -> list:
    """Equivalente a verify_asset_code, para un código fundamental.
    quarterly_by_idx/daily_series/current_ratios/stored ya vienen
    calculados una sola vez por activo (ver _verify_one_fund_asset) —
    antes se recomputaban por cada código individual."""
    if not quarters:
        return []

    if code in _FUND_DAILY_CODES:
        fresh = dict(daily_series.get(code, {}))
    else:
        fresh = {}
        for idx, q in enumerate(quarters):
            val = quarterly_by_idx[idx].get(code)
            if val is not None:
                fresh[q.period_date] = val

    current_val = current_ratios.get(code)
    entry = _current_ratio_diff_entry(current_val, stored, _date_type.today())
    if entry is not None:
        fresh[entry[0]] = entry[1]

    diffs = []
    for d in sorted(set(fresh) | set(stored)):
        fv, sv = fresh.get(d), stored.get(d)
        if fv is None and sv is not None:
            kind = "solo en DB (¿debería haberse borrado?)"
            diffs.append((d, kind, sv, fv, _diff_category(kind)))
        elif fv is not None and sv is None:
            kind = "falta en DB (¿el delta no la escribió?)"
            diffs.append((d, kind, sv, fv, _diff_category(kind)))
        elif not _values_equal(fv, sv):
            kind = "valor distinto"
            diffs.append((d, kind, sv, fv, _diff_category(kind)))
        if fv is not None:
            sanity = check_sanity(code, fv)
            if sanity:
                diffs.append((d, sanity, sv, fv, _diff_category(sanity)))
    return diffs


def pick_fund_sample_ids(session, sample: int | None) -> list:
    """Solo activos con al menos un trimestre cargado (sin eso no hay
    nada que comparar). sample=None: todos (ver pick_sample_ids)."""
    all_ids = [r[0] for r in session.execute(
        sa.select(FundamentalQuarterly.asset_id).distinct()
    ).all()]
    if sample is None:
        return all_ids
    return random.sample(all_ids, min(sample, len(all_ids)))


def _verify_one_fund_asset(asset_id: int, ticker: str, codes: list,
                           stored_by_code: dict, session=None) -> list:
    """Equivalente a _verify_one_asset, para ratios fundamentales.
    quarterly_by_idx/daily_series/current_ratios se calculan una sola vez
    acá (no por cada código, ver verify_asset_ratio_code). session: ver
    _verify_one_asset (el lote administra la sesión si se pasa)."""
    own = session is None
    s = session or get_session()
    try:
        quarters   = _load_quarters(s, asset_id)
        price_rows = _load_fund_price_rows(s, asset_id)
        if not quarters:
            return []
        q_ords = np.array([q.period_date.toordinal() for q in quarters])
        quarterly_by_idx = _compute_quarterly_by_idx(quarters)
        daily_series     = _compute_daily_series_by_code(quarters, q_ords, price_rows)
        current_ratios   = _current_ratio_fresh(quarters, price_rows)
        out = []
        for code in codes:
            stored = stored_by_code.get(code, {}).get(asset_id, {})
            diffs = verify_asset_ratio_code(code, asset_id, quarters, quarterly_by_idx,
                                            daily_series, current_ratios, stored)
            if diffs:
                out.append({"code": code, "asset_id": asset_id,
                           "ticker": ticker, "diffs": diffs})
        return out
    finally:
        if own:
            from app.database import Session as _ScopedSession
            _ScopedSession.remove()


def _verify_fund_batch(batch_asset_ids: list, ticker_map: dict, codes: list) -> dict:
    """Unidad de trabajo del pool para fundamentales (ver _verify_batch): un
    LOTE de activos, auto-contenido, una sola sesión. NO atrapa excepciones a
    propósito (ver _verify_batch: propagar evita marcas incorrectas)."""
    from app.database import Session as _ScopedSession
    s = get_session()
    try:
        stored_by_code = _prefetch_stored(s, codes, batch_asset_ids)
        out = []
        for aid in batch_asset_ids:
            out.extend(_verify_one_fund_asset(
                aid, ticker_map.get(aid, "?"), codes,
                stored_by_code, session=s))
        return {"results": out, "n_assets": len(batch_asset_ids)}
    finally:
        _ScopedSession.remove()


def run_fund_verification(codes: list | None = None, sample: int | None = 30,
                          tickers: list | None = None, asset_ids: list | None = None,
                          progress_cb=None) -> dict:
    """Equivalente a run_verification, para ratios fundamentales
    (ind_fundamental_*) — ver verify_asset_ratio_code. asset_ids: ver
    run_verification (activos exactos, sin resolver tickers ni muestrear)."""
    s = get_session()
    codes = [c for c in (codes or sorted(_ALL_FUND_CODES)) if c in _ALL_FUND_CODES]

    missing_tickers = []
    if asset_ids is not None:
        pass
    elif tickers:
        asset_ids, missing_tickers = ids_from_tickers(s, tickers)
    else:
        asset_ids = pick_fund_sample_ids(s, sample)

    ticker_map = {a.id: a.ticker for a in
                  s.query(Asset).filter(Asset.id.in_(asset_ids)).all()}

    total_work = len(codes) * len(asset_ids)
    if progress_cb:
        progress_cb(0, max(total_work, 1), "")

    results = _run_batched(asset_ids, codes, ticker_map, _verify_fund_batch,
                           progress_cb, total_work)

    return {
        "codes": codes, "asset_ids": asset_ids,
        "missing_tickers": missing_tickers,
        "combos": total_work, "results": results,
    }


# ── Marcado de activos con hallazgos (job programado, ver scheduler_service) ──
# Persiste el resultado de una corrida COMPLETA (todos los activos, no una
# muestra) para poder marcar en los selectores de activo de la app
# (Análisis de Activo, RRG, Evolución, Pares, Retornos) los que tienen
# posibles errores de datos de origen o discrepancias de cálculo, sin
# recalcular nada en vivo cada vez que alguien abre un dropdown.

def _aggregate_flags(*results: dict) -> dict:
    """Agrupa los resultados de run_verification/run_fund_verification
    (uno o más, típicamente indicadores + fundamentales) por activo:
    cuántas diferencias "calc"/"sanity" tiene en total y qué códigos están
    involucrados. Pura — no toca la base, no sabe nada de tickers."""
    by_asset: dict = {}
    for result in results:
        for r in result["results"]:
            agg = by_asset.setdefault(r["asset_id"], {"calc": 0, "sanity": 0, "codes": set()})
            for d in r["diffs"]:
                agg[d[4]] += 1
            agg["codes"].add(r["code"])
    return by_asset


def _flag_actions(scope: set, by_asset: dict, existing_ids: set) -> tuple[set, set]:
    """De los activos en `scope` (los que se acaban de re-verificar),
    cuáles hay que upsertear (siguen con algún hallazgo) y cuáles borrar
    (tenían fila guardada pero la corrida fresca ya no encontró nada).
    Pura — no toca la base. Activos fuera de `scope` no se tocan: la
    marca de un activo se reescribe exactamente cuando ESE activo se
    vuelve a verificar, nunca por otro motivo."""
    to_upsert = {aid for aid in scope if aid in by_asset}
    to_delete = {aid for aid in scope if aid not in by_asset and aid in existing_ids}
    return to_upsert, to_delete


def update_flags_for_assets(asset_ids: list | None = None, progress_cb=None) -> dict:
    """Verifica indicadores + fundamentales (todos los códigos) para
    `asset_ids` — o TODOS los activos si asset_ids es None — y actualiza
    asset_verification_flag solo para esos activos: upsert si sigue con
    hallazgos, borra la fila si ya no tiene ninguno. Los activos fuera de
    ese conjunto no se tocan.

    asset_ids=None: corrida completa (job semanal, ver scheduler_service
    y run_full_verification_and_store). asset_ids=<lista>: re-verificación
    puntual — p. ej. "solo los ya marcados" desde /admin/verify, para
    confirmar si un hallazgo sigue vigente sin pagar el costo de una
    corrida completa.

    A la escala actual (~500 activos) una corrida completa tarda similar
    a un rebuild completo de indicadores (paralelizada con
    _VERIFY_WORKERS threads, ver run_verification/run_fund_verification);
    si el universo crece a 10000 activos (project_scaling_target) el
    techo del GIL para el cómputo pandas/numpy va a pedir migrar a
    ProcessPoolExecutor, mismo tema ya anotado para el pool de indicadores.

    progress_cb(cur, tot, label): cur/tot en base 100 (50 indicadores +
    50 fundamentales).

    Guarda duración y resultado en verification_run_log (fila única,
    id=1) — es lo que muestra /admin/verify como "última corrida", para
    no depender de leer logs de servidor para saber cuánto tardó."""
    import time as _time
    from datetime import datetime as _dt
    from app.models import AssetVerificationFlag, VerificationRunLog

    s = get_session()
    t0 = _time.monotonic()
    started_at = _dt.utcnow()

    def _split_cb(base, span):
        def _cb(cur, tot, label=""):
            if progress_cb:
                progress_cb(base + int(cur / max(tot, 1) * span), 100, label)
        return _cb

    ind_result  = run_verification(sample=None, asset_ids=asset_ids, progress_cb=_split_cb(0, 50))
    fund_result = run_fund_verification(sample=None, asset_ids=asset_ids, progress_cb=_split_cb(50, 50))

    by_asset = _aggregate_flags(ind_result, fund_result)
    scope = set(asset_ids) if asset_ids is not None else set(ind_result["asset_ids"])

    existing = {f.asset_id: f for f in
                s.query(AssetVerificationFlag)
                 .filter(AssetVerificationFlag.asset_id.in_(scope)).all()} if scope else {}
    to_upsert, to_delete = _flag_actions(scope, by_asset, set(existing))

    now = _dt.utcnow()
    for asset_id in to_delete:
        s.delete(existing[asset_id])
    for asset_id in to_upsert:
        agg = by_asset[asset_id]
        flag = existing.get(asset_id) or AssetVerificationFlag(asset_id=asset_id)
        flag.n_calc_diffs   = agg["calc"]
        flag.n_sanity_diffs = agg["sanity"]
        flag.detail         = ", ".join(sorted(agg["codes"]))
        flag.checked_at     = now
        if asset_id not in existing:
            s.add(flag)

    result = {
        "checked_assets": len(scope),
        "flagged_assets": len(to_upsert),
        "cleared_assets": len(to_delete),
        "indicators_combos":   ind_result["combos"],
        "fundamentals_combos": fund_result["combos"],
        "seconds": round(_time.monotonic() - t0, 1),
        # detalle completo (indicadores + fundamentales combinados), para
        # que /admin/verify pueda mostrar las mismas pestañas de
        # discrepancias/datos de origen que un run_verification suelto —
        # no lo usa el job programado, solo lo lee el botón manual.
        "results": ind_result["results"] + fund_result["results"],
    }

    log = s.get(VerificationRunLog, 1) or VerificationRunLog(id=1)
    log.mode           = "all" if asset_ids is None else "marked"
    log.started_at     = started_at
    log.seconds        = result["seconds"]
    log.checked_assets = result["checked_assets"]
    log.flagged_assets = result["flagged_assets"]
    log.cleared_assets = result["cleared_assets"]
    s.merge(log)
    s.commit()

    return result


def run_full_verification_and_store(progress_cb=None) -> dict:
    """Corrida completa (todos los activos) — ver update_flags_for_assets.
    Nombre separado porque es el que llama el job programado
    (scheduler_service._weekly_verification_job); conviene distinguir en
    el código "corrida completa" de "reverificar un subconjunto puntual"
    aunque sea la misma función por debajo."""
    return update_flags_for_assets(asset_ids=None, progress_cb=progress_cb)


def get_flagged_asset_ids() -> dict:
    """asset_id -> texto corto para el tooltip del selector de activos.
    Lectura liviana (una query a la tabla ya poblada por
    run_full_verification_and_store) — llamar libremente desde cualquier
    callback que arme un dropdown de activos, no recalcula nada."""
    from app.models import AssetVerificationFlag

    s = get_session()
    rows = s.execute(sa.select(
        AssetVerificationFlag.asset_id,
        AssetVerificationFlag.n_calc_diffs,
        AssetVerificationFlag.n_sanity_diffs,
    )).all()
    out = {}
    for asset_id, n_calc, n_sanity in rows:
        parts = []
        if n_calc:
            parts.append(f"{n_calc} discrepancia(s) de cálculo")
        if n_sanity:
            parts.append(f"{n_sanity} posible(s) error(es) de datos de origen")
        out[asset_id] = " + ".join(parts)
    return out


def get_last_verification_run() -> dict | None:
    """Última corrida de update_flags_for_assets (botón manual o job
    semanal) — None si nunca corrió. Ver verification_run_log."""
    from app.models import VerificationRunLog

    s = get_session()
    log = s.get(VerificationRunLog, 1)
    if log is None:
        return None
    return {
        "mode": log.mode, "started_at": log.started_at, "seconds": log.seconds,
        "checked_assets": log.checked_assets, "flagged_assets": log.flagged_assets,
        "cleared_assets": log.cleared_assets,
    }
