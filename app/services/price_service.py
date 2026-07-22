"""
Servicio de descarga y actualización de precios históricos.
Lógica principal:
  - Si el activo no tiene precios: descarga toda la historia.
  - Si ya tiene precios: borra el último día y descarga desde ese día inclusive.
"""
import logging
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime
from types import SimpleNamespace

import pandas as pd
import yfinance as yf
from sqlalchemy import func, inspect as sa_inspect

from app.database import get_session, Session as _ScopedSession
from app.models import Asset, Price, PriceUpdateLog
from app.services.technical_service import (
    backfill_asset_history,
    compute_current_indicators,
    _get_drawdown_config,
    _get_regime_config,
    _get_volatility_config,
    _save_indicator_log,
)
from app.services import sr_service
from app.sources.registry import get_source

logger = logging.getLogger(__name__)

# Activos procesados en paralelo (DB write + indicadores por activo)
_UPDATE_WORKERS = 6


def _snapshot_cfgs(*cfgs):
    """Copia PLANA (SimpleNamespace) de los objetos de configuración ORM, con
    los mismos nombres de atributo — drop-in donde antes iba la instancia.

    Dos motivos:

    1. Sobreviven al cierre de la sesión. _bulk_download_assets suelta su
       sesión antes de la fase larga para no dejar una transacción abierta
       (ver ahí); un objeto ORM expirado que se lee después dispararía un
       refresh contra una sesión muerta.
    2. Se pueden leer desde otro thread. Estos cfgs se le pasan a los workers
       del ThreadPool, y una instancia ORM sigue atada a la sesión del thread
       que la cargó — la Session de SQLAlchemy no es thread-safe, así que un
       refresh disparado desde un worker era una race latente.

    Las columnas salen del mapper, no de una lista escrita a mano: si mañana
    se agrega un campo a alguna config, viaja solo. Si el objeto no está
    mapeado (o ya es plano), se devuelve tal cual.
    """
    out = []
    for cfg in cfgs:
        if cfg is None:
            out.append(None)
            continue
        try:
            cols = sa_inspect(type(cfg)).columns.keys()
            out.append(SimpleNamespace(**{c: getattr(cfg, c) for c in cols}))
        except Exception:
            out.append(cfg)
    return tuple(out)


def _get_last_price_date(asset_id: int, session):
    result = (
        session.query(func.max(Price.date))
        .filter(Price.asset_id == asset_id)
        .scalar()
    )
    return result  # datetime.date o None


def _delete_from_date(asset_id: int, from_date, session) -> None:
    session.query(Price).filter(
        Price.asset_id == asset_id, Price.date >= from_date
    ).delete(synchronize_session=False)


_PRICE_BATCH = 500  # filas por INSERT — evita superar max_allowed_packet de MariaDB


def _upsert_prices(asset_id: int, df, session) -> int:
    """Inserta filas del DataFrame en la tabla de precios en batches. Devuelve cantidad insertada."""
    if df.empty:
        return 0
    import math
    from app.services import db_compat
    from app.services.db_compat import INSERTED

    def _f(v):
        """Convierte NaN/None a None para columnas float."""
        try:
            return None if (v is None or math.isnan(float(v))) else float(v)
        except (TypeError, ValueError):
            return None

    mappings = [
        {
            "asset_id": asset_id,
            "date":     row.date,
            "open":     _f(row.open),
            "high":     _f(row.high),
            "low":      _f(row.low),
            "close":    _f(row.close),
            "volume":   int(row.volume) if (row.volume is not None and not math.isnan(float(row.volume))) else None,
        }
        for row in df.itertuples(index=False)
    ]

    for i in range(0, len(mappings), _PRICE_BATCH):
        chunk = mappings[i : i + _PRICE_BATCH]
        stmt  = db_compat.upsert(session, Price, chunk, {
            "open": INSERTED, "high": INSERTED, "low": INSERTED,
            "close": INSERTED, "volume": INSERTED,
        })
        session.execute(stmt)

    return len(mappings)


def _save_update_log(asset_id: int, success: bool, error: str | None, session) -> None:
    log = session.query(PriceUpdateLog).filter(
        PriceUpdateLog.asset_id == asset_id
    ).first()
    if log is None:
        log = PriceUpdateLog(asset_id=asset_id, success=success, error_detail=error)
        session.add(log)
    else:
        log.last_attempt_at = datetime.utcnow()
        log.success = success
        log.error_detail = error


def update_asset_prices(
    asset_id: int,
    *,
    full: bool = False,
    skip_indicators: bool = False,
    _dd_cfg=None,
    _regime_cfg=None,
    _vol_cfg=None,
    _sr_cfg=None,
) -> None:
    """
    Actualiza los precios de un activo.
    Si el activo es sintético (fuente Calculado), delega al synthetic_service.
    Si falla, registra el error en price_update_log y relanza la excepción.
    full=True fuerza redescarga de la historia completa; el borrado del historial
    ocurre dentro de la misma transacción, por lo que un fallo de descarga no
    pierde los datos existentes.
    Los parámetros _*_cfg permiten reutilizar configs pre-cargadas en llamadas masivas.

    skip_indicators=True: no calcula indicadores/ratios acá (lo usan las
    corridas masivas — update_all_active_assets/update_new_assets_prices/
    redownload_prices — que después encadenan update_indicator_history +
    la cadena de fundamentales una sola vez para todos los activos, en vez
    de recalcular activo por activo con este camino rápido). Los
    llamadores puntuales (botón "Recalcular indicadores" de la página de
    Precios, alta de activo nuevo) siguen usando el default False.
    """
    from app.services.synthetic_service import compute_synthetic_prices

    s  = get_session()
    asset = s.get(Asset, asset_id)
    if asset is None:
        raise ValueError(f"Activo id={asset_id} no encontrado")

    if asset.price_source.name == "Calculado":
        try:
            compute_synthetic_prices(asset_id, full=full)
            _save_update_log(asset_id, success=True, error=None, session=s)
            s.commit()
        except Exception as exc:
            s.rollback()
            error_msg = str(exc)
            logger.error("Error calculando precios sintéticos de %s: %s", asset.ticker, error_msg)
            _save_update_log(asset_id, success=False, error=error_msg, session=s)
            s.commit()
        return

    source = get_source(asset.price_source.name)
    last_date = None if full else _get_last_price_date(asset_id, s)

    try:
        if last_date is None:
            # Limpiar historia previa dentro de la transacción: si la descarga
            # falla, el rollback la restaura
            s.query(Price).filter(Price.asset_id == asset_id).delete(synchronize_session=False)
            df = source.download_history(asset.ticker)
        else:
            _delete_from_date(asset_id, last_date, s)
            df = source.download_history(asset.ticker, start=last_date)

        if df.empty:
            raise ValueError(f"No se encontraron datos de precio para '{asset.ticker}'. Verificá que el ticker sea válido en Yahoo Finance.")

        count = _upsert_prices(asset_id, df, s)
        _save_update_log(asset_id, success=True, error=None, session=s)
        s.commit()
        logger.info("Activo %s: %d filas importadas", asset.ticker, count)

        if not skip_indicators:
            # Recalcular indicadores vigentes (técnicos + ratios fundamentales)
            ind_errors = []
            try:
                compute_current_indicators(
                    asset_id,
                    _dd_cfg=_dd_cfg,
                    _regime_cfg=_regime_cfg,
                    _vol_cfg=_vol_cfg,
                    _sr_cfg=_sr_cfg,
                    quick=True,
                )
            except Exception as ind_exc:
                logger.warning(
                    "Error calculando indicadores para %s: %s", asset.ticker, ind_exc
                )
                ind_errors.append(f"técnico: {ind_exc}")
            try:
                from app.services.fundamental_service import recompute_ratios_for_asset
                recompute_ratios_for_asset(asset_id)
            except Exception as fund_exc:
                logger.warning("Error recomputo ratios fundamentales %s: %s", asset.ticker, fund_exc)
                ind_errors.append(f"fundamental: {fund_exc}")
            if last_date is None:
                # Historia de precios nueva o reconstruida → completar también la
                # historia de indicadores (el quick solo escribe el último día)
                try:
                    backfill_asset_history(asset_id)
                except Exception as bf_exc:
                    logger.warning("Error backfill indicadores %s: %s", asset.ticker, bf_exc)
                    ind_errors.append(f"backfill: {bf_exc}")
            _save_indicator_log(asset_id, success=not ind_errors,
                                error="; ".join(ind_errors) or None, session=s)

    except NotImplementedError:
        # Fuente válida pero sin descarga externa — no es un error operativo
        logger.info("Activo %s: fuente '%s' no requiere descarga externa, omitido.",
                    asset.ticker, asset.price_source.name)
        _save_update_log(asset_id, success=True,
                         error=f"Fuente '{asset.price_source.name}' no requiere descarga.", session=s)
        s.commit()
    except Exception as exc:
        s.rollback()
        error_msg = str(exc)
        logger.error("Error actualizando precios de %s: %s", asset.ticker, error_msg)
        _save_update_log(asset_id, success=False, error=error_msg, session=s)
        s.commit()
        raise


_YF_COLS = ["date", "open", "high", "low", "close", "volume"]

# Tickers por yf.download(): con miles de activos, un solo call con todos los
# tickers es candidato a timeout o rate-limit de Yahoo Finance.
_YF_CHUNK_SIZE = 200


def _yf_batch_download(tickers: list, start=None) -> "pd.DataFrame | None":
    """
    Un solo yf.download(). start=None → period='max', start=date → desde esa fecha.
    Retorna el DataFrame crudo o None si falla.
    """
    try:
        kwargs = dict(auto_adjust=True, group_by="ticker", progress=False, threads=True)
        if start is None:
            return yf.download(tickers, period="max", **kwargs)
        else:
            return yf.download(tickers, start=start.isoformat(), **kwargs)
    except Exception as exc:
        logger.warning("Batch yfinance download falló (%s): %s", tickers, exc)
        return None


def _extract_ticker_df(raw, ticker: str) -> "pd.DataFrame":
    """Extrae y normaliza el sub-DataFrame de un ticker del resultado batch."""
    _rename = {"Date": "date", "Open": "open", "High": "high",
               "Low": "low", "Close": "close", "Volume": "volume"}
    df = raw[ticker].copy() if isinstance(raw.columns, pd.MultiIndex) else raw.copy()
    df = df.reset_index()
    df.rename(columns=_rename, inplace=True)
    df["date"] = pd.to_datetime(df["date"]).dt.date
    present = [c for c in _YF_COLS if c in df.columns]
    return df[present].dropna(subset=["close"])


def _yf_download_chunked(tickers: list, start=None) -> dict:
    """Descarga por chunks de _YF_CHUNK_SIZE tickers y devuelve {ticker: df}
    ya extraído/normalizado. Si un chunk falla (timeout, rate-limit), solo se
    pierden sus tickers en vez de todo el grupo."""
    out = {}
    for i in range(0, len(tickers), _YF_CHUNK_SIZE):
        chunk = tickers[i : i + _YF_CHUNK_SIZE]
        raw = _yf_batch_download(chunk, start=start)
        if raw is None:
            continue
        for ticker in chunk:
            try:
                out[ticker] = _extract_ticker_df(raw, ticker)
            except Exception as exc:
                logger.warning("Error procesando batch para %s: %s", ticker, exc)
    return out


def _bulk_prefetch_yfinance(assets_with_dates: list) -> dict:
    """
    Descarga precios de múltiples tickers en el menor número de llamadas posible.
    assets_with_dates: lista de (asset_id, ticker, last_date) — datos PLANOS,
    nunca objetos ORM: el llamador cierra su transacción antes de entrar acá
    (ver _bulk_download_assets), así que no queda sesión viva de la que
    recargar atributos.
    Retorna dict {asset_id: DataFrame}.

    Separación en dos grupos para manejar fechas distintas correctamente:
    - Sin last_date (primera vez): necesitan historia completa → batch con period='max'.
    - Con last_date: incrementales → batch desde min(last_dates) del grupo.
      Cada ticker recibe solo las filas >= su propio last_date (filtro en memoria).
    Cada grupo se descarga en chunks de _YF_CHUNK_SIZE tickers (ver _yf_download_chunked).
    """
    if not assets_with_dates:
        return {}

    first_time  = [(i, t, d) for i, t, d in assets_with_dates if d is None]
    incremental = [(i, t, d) for i, t, d in assets_with_dates if d is not None]
    result = {}

    # --- Grupo 1: primera descarga (historia completa) ---
    if first_time:
        tickers   = [t for _, t, _ in first_time]
        by_ticker = _yf_download_chunked(tickers, start=None)
        for asset_id, ticker, _ in first_time:
            if ticker in by_ticker:
                result[asset_id] = by_ticker[ticker]

    # --- Grupo 2: actualizaciones incrementales ---
    if incremental:
        min_start = min(d for _, _, d in incremental)
        tickers   = [t for _, t, _ in incremental]
        by_ticker = _yf_download_chunked(tickers, start=min_start)
        for asset_id, ticker, last_date in incremental:
            df = by_ticker.get(ticker)
            if df is None:
                continue
            # Cada ticker solo recibe filas desde su propio last_date
            result[asset_id] = df[df["date"] >= last_date].reset_index(drop=True)

    return result


def _process_yf_asset_worker(
    asset_id: int,
    ticker: str,
    df,
    last_date,
    _dd_cfg, _regime_cfg, _vol_cfg, _sr_cfg,
    skip_indicators: bool = False,
    full: bool = False,
) -> tuple[bool, dict | None]:
    """Procesa un activo Yahoo Finance en su propio thread: escribe precios y
    calcula indicadores (salvo skip_indicators=True, ver update_asset_prices).
    full=True (redescarga): borra la historia previa completa en la MISMA
    transacción que el insert — el chequeo de df vacío es previo, así que si
    la descarga vino sin datos la historia existente queda intacta."""
    s = get_session()
    try:
        if df.empty:
            raise ValueError(
                f"No se encontraron datos de precio para '{ticker}'. "
                "Verificá que el ticker sea válido en Yahoo Finance."
            )
        if full:
            s.query(Price).filter(Price.asset_id == asset_id).delete(
                synchronize_session=False)
        elif last_date is not None:
            _delete_from_date(asset_id, last_date, s)
        count = _upsert_prices(asset_id, df, s)
        _save_update_log(asset_id, success=True, error=None, session=s)
        s.commit()
        logger.info("Activo %s: %d filas importadas (batch)", ticker, count)
        if not skip_indicators:
            ind_errors = []
            try:
                compute_current_indicators(
                    asset_id,
                    _dd_cfg=_dd_cfg, _regime_cfg=_regime_cfg,
                    _vol_cfg=_vol_cfg, _sr_cfg=_sr_cfg,
                    quick=True,
                )
            except Exception as ind_exc:
                logger.warning("Error indicadores %s: %s", ticker, ind_exc)
                ind_errors.append(f"técnico: {ind_exc}")
            try:
                from app.services.fundamental_service import recompute_ratios_for_asset
                recompute_ratios_for_asset(asset_id)
            except Exception as fund_exc:
                logger.warning("Error recomputo ratios fundamentales %s: %s", ticker, fund_exc)
                ind_errors.append(f"fundamental: {fund_exc}")
            if last_date is None:
                # Primera descarga del activo → completar la historia de indicadores
                try:
                    backfill_asset_history(asset_id)
                except Exception as bf_exc:
                    logger.warning("Error backfill indicadores %s: %s", ticker, bf_exc)
                    ind_errors.append(f"backfill: {bf_exc}")
            _save_indicator_log(asset_id, success=not ind_errors,
                                error="; ".join(ind_errors) or None, session=s)
        return True, None
    except Exception as exc:
        s.rollback()
        error_msg = str(exc)
        logger.error("Error actualizando precios de %s: %s", ticker, error_msg)
        _save_update_log(asset_id, success=False, error=error_msg, session=s)
        s.commit()
        return False, {"ticker": ticker, "error": error_msg}
    finally:
        _ScopedSession.remove()


def _process_other_asset_worker(
    asset_id: int,
    ticker: str,
    _dd_cfg, _regime_cfg, _vol_cfg, _sr_cfg,
    skip_indicators: bool = False,
    full: bool = False,
) -> tuple[bool, dict | None]:
    """Procesa un activo no-YF (otra fuente o sintético) en su propio thread."""
    try:
        update_asset_prices(
            asset_id,
            full=full,
            _dd_cfg=_dd_cfg, _regime_cfg=_regime_cfg,
            _vol_cfg=_vol_cfg, _sr_cfg=_sr_cfg,
            skip_indicators=skip_indicators,
        )
        return True, None
    except Exception as exc:
        return False, {"ticker": ticker, "error": str(exc)}
    finally:
        _ScopedSession.remove()


def _chain_to_indicator_and_ratio_delta(progress_cb, download_summary: dict) -> dict:
    """Encadena update_indicator_history() + el delta de ratios fundamentales
    (force=False) después de una descarga/redescarga masiva de precios (ver
    skip_indicators en update_asset_prices: las corridas masivas ya no
    recalculan indicadores/ratios activo por activo, lo hacen acá una sola
    vez para todos). La barra se reacomoda al pasar de fase — el mensaje
    aclara cuál está corriendo.

    Si no se tocó ningún activo (ej. "solo nuevos" sin nada nuevo), no vale
    la pena pagar un delta completo de ~2 minutos por nada — se salta.

    Solo la usan los jobs globales (update_new_assets_prices/
    update_all_active_assets) — redownload_prices con selección puntual
    usa _rebuild_indicators_for_assets en su lugar (rebuild completo por
    activo, no delta: ver esa función para el motivo)."""
    if download_summary.get("total", 0) == 0:
        return download_summary

    from app.services.fundamental_service import _run_ratios_and_backfill
    from app.services.technical_service import update_indicator_history

    if progress_cb:
        progress_cb(0, 1, "Precios actualizados. Calculando indicadores...")
    ind_result = update_indicator_history(progress_cb=progress_cb)
    if progress_cb:
        progress_cb(0, 1, "Recalculando ratios...")
    ratio_result = _run_ratios_and_backfill(progress_cb, force=False)
    # Acumulado, no solo el de precios: success + len(errors) tiene que
    # dar total, si no el resumen final ("X/Y OK") no cierra.
    download_summary["total"]   += ind_result.get("total", 0) + ratio_result.get("total", 0)
    download_summary["success"] += ind_result.get("success", 0) + ratio_result.get("success", 0)
    download_summary["errors"].extend(ind_result.get("errors", []))
    download_summary["errors"].extend(ratio_result.get("errors", []))
    return download_summary


def _rebuild_indicators_for_assets(progress_cb, asset_ids: list) -> dict:
    """Recalculo COMPLETO (no delta) de indicadores técnicos + ratios
    fundamentales para una selección puntual de activos — usado tras un
    redescargo de precios puntual (ver redownload_prices): como los
    precios son enteramente nuevos (posible corrección retroactiva de la
    fuente, ej. un split/dividendo re-ajustado), un delta podría no
    detectar el cambio para los códigos sin compuerta de checksum (ver
    _CHECKSUM_DEP_CODES en technical_service.py); el rebuild por activo no
    tiene atajos, así que siempre queda consistente. El costo es
    aceptable porque esta selección siempre es chica (uso puntual desde
    /admin/prices, no la corrida global)."""
    from app.services.fundamental_service import (
        backfill_asset_fund_history, recompute_ratios_for_asset,
    )
    from app.services.technical_service import (
        backfill_asset_history, compute_current_indicators,
    )
    total  = len(asset_ids)
    errors = []
    for i, aid in enumerate(asset_ids, 1):
        if progress_cb:
            progress_cb(i, total, f"Recalculando indicadores id={aid}...")
        try:
            compute_current_indicators(aid)
            backfill_asset_history(aid)
            recompute_ratios_for_asset(aid)
            backfill_asset_fund_history(aid)
        except Exception as exc:
            errors.append({"ticker": str(aid), "error": str(exc)})
    return {"total": total, "success": total - len(errors), "errors": errors}


def update_new_assets_prices(progress_cb=None) -> dict:
    """Solo activos sin PriceUpdateLog previo (nunca descargados).

    Va por el mismo camino batch que update_all_active_assets (antes era un
    loop secuencial con una descarga individual por activo — horas para una
    importación masiva): los recién importados no tienen precios, así que
    caen enteros en el grupo first_time del prefetch (historia completa por
    chunks de _YF_CHUNK_SIZE)."""
    s = get_session()
    logged_ids = {r[0] for r in s.query(PriceUpdateLog.asset_id).all()}
    assets = [a for a in s.query(Asset).all() if a.id not in logged_ids]
    summary = _bulk_download_assets(assets, progress_cb)
    return _chain_to_indicator_and_ratio_delta(progress_cb, summary)


def _bulk_download_assets(assets, progress_cb=None, full: bool = False) -> dict:
    """Descarga precios de una lista de activos por el camino batch: split
    Yahoo/otras fuentes+sintéticos, prefetch de últimas fechas en una sola
    query, _bulk_prefetch_yfinance por chunks y escritura en ThreadPool.
    Siempre con skip_indicators=True — el llamador encadena el delta (o el
    rebuild) UNA vez para todos los activos al terminar.

    full=True (redescarga global): ignora las últimas fechas → todos los
    tickers van al grupo first_time (historia completa) y cada worker borra
    la historia previa dentro de su propia transacción, solo si la descarga
    trajo datos.

    Devuelve el resumen {"total", "success", "errors"} de la fase de
    descarga (sin encadenar indicadores)."""
    from app.models import SyntheticFormula, PriceSource

    total   = len(assets)
    summary = {"total": total, "success": 0, "errors": []}
    if not assets:
        return summary

    s = get_session()

    # Fix N+1: un solo query para IDs sintéticos
    synthetic_ids = {r[0] for r in s.query(SyntheticFormula.asset_id).all()}
    regular   = [a for a in assets if a.id not in synthetic_ids]
    synthetic = [a for a in assets if a.id in synthetic_ids]

    # Pre-cargar configs de indicadores una sola vez (evita N × 4 queries)
    _dd_cfg     = _get_drawdown_config()
    _regime_cfg = _get_regime_config()
    _vol_cfg    = _get_volatility_config()
    _sr_cfg     = sr_service._get_sr_config()

    # Separar activos Yahoo Finance para batch download
    yf_src = s.query(PriceSource).filter(PriceSource.name == "Yahoo Finance").first()
    yf_src_id = yf_src.id if yf_src else None

    yf_assets   = [a for a in regular if yf_src_id and a.price_source_id == yf_src_id]
    other_regular = [a for a in regular if not (yf_src_id and a.price_source_id == yf_src_id)]

    # Prefetch de last_dates en una sola query GROUP BY.
    # full=True ignora lo existente: todos descargan la historia completa.
    yf_ids = [a.id for a in yf_assets]
    if yf_ids and not full:
        _max_dates = {
            r[0]: r[1]
            for r in s.query(Price.asset_id, func.max(Price.date))
                      .filter(Price.asset_id.in_(yf_ids))
                      .group_by(Price.asset_id)
                      .all()
        }
    else:
        _max_dates = {}
    yf_last_dates = {a.id: _max_dates.get(a.id) for a in yf_assets}

    # Colectar (id, ticker) ANTES de soltar la sesión: los commits expiran los
    # objetos ORM y acceder a sus atributos después podría fallar si fueron
    # eliminados en otro thread.
    yf_pairs        = [(a.id, a.ticker) for a in yf_assets]
    other_pairs     = [(a.id, a.ticker) for a in other_regular + synthetic]
    prefetch_args   = [(aid, tick, yf_last_dates[aid]) for aid, tick in yf_pairs]

    # CERRAR la transacción antes de la fase larga (descarga de red + pool de
    # escritura). SQLAlchemy abre transacción en la primera query y la sostiene
    # hasta el commit/close: sin esto, esta sesión quedaba 'idle in transaction'
    # los ~15 minutos que dura la descarga. En PostgreSQL eso FIJA EL XMIN
    # HORIZON — autovacuum no puede reclamar ninguna tupla muerta mientras
    # tanto, y esta misma corrida borra cientos de miles de filas de `prices`
    # (ver el _delete_from_date de cada worker) → bloat y checkpoints
    # disparados por WAL. Además retiene una conexión del pool sin usarla.
    #
    # remove() y no commit(): close() detacha los objetos pero NO expira sus
    # atributos ya cargados, así que los `assets` que nos pasó el llamador
    # siguen siendo legibles. Un commit() los expiraría y cualquier lectura
    # posterior dispararía un refresh contra una sesión que ya no existe.
    # De acá en adelante SOLO se usan datos planos (pairs/prefetch_args/cfgs
    # desprendidos); los workers abren su propia sesión en su propio thread.
    _detach_cfgs = _snapshot_cfgs(_dd_cfg, _regime_cfg, _vol_cfg, _sr_cfg)
    _ScopedSession.remove()
    _dd_cfg, _regime_cfg, _vol_cfg, _sr_cfg = _detach_cfgs

    prefetched = _bulk_prefetch_yfinance(prefetch_args)

    cfgs = dict(
        _dd_cfg=_dd_cfg, _regime_cfg=_regime_cfg,
        _vol_cfg=_vol_cfg, _sr_cfg=_sr_cfg,
    )

    futures: dict = {}
    with ThreadPoolExecutor(max_workers=_UPDATE_WORKERS) as pool:
        for asset_id, asset_ticker in yf_pairs:
            if asset_id in prefetched:
                futures[pool.submit(
                    _process_yf_asset_worker,
                    asset_id, asset_ticker, prefetched[asset_id], yf_last_dates[asset_id],
                    **cfgs, skip_indicators=True, full=full,
                )] = asset_ticker
            else:
                futures[pool.submit(
                    _process_other_asset_worker, asset_id, asset_ticker, **cfgs,
                    skip_indicators=True, full=full,
                )] = asset_ticker

        for asset_id, asset_ticker in other_pairs:
            futures[pool.submit(
                _process_other_asset_worker, asset_id, asset_ticker, **cfgs,
                skip_indicators=True, full=full,
            )] = asset_ticker

        done = 0
        for future in as_completed(futures):
            done += 1
            if progress_cb:
                progress_cb(done, total)
            ok, err = future.result()
            if ok:
                summary["success"] += 1
            elif err:
                summary["errors"].append(err)

    logger.info(
        "Descarga batch: %d/%d exitosos, %d errores",
        summary["success"],
        summary["total"],
        len(summary["errors"]),
    )
    return summary


def update_all_active_assets(progress_cb=None) -> dict:
    """
    Actualiza todos los activos activos. Primero los regulares, luego los sintéticos.
    Tolerante a fallos individuales. Devuelve un resumen con éxitos y errores.
    """
    s = get_session()
    all_assets = s.query(Asset).all()
    summary = _bulk_download_assets(all_assets, progress_cb)

    # Los precios ya están, pero los indicadores/ratios de cada activo
    # todavía no (skip_indicators=True arriba) — se encadena acá el
    # sistema de delta (mismo que usa el panel "Indicadores Técnicos"/
    # "Ratios fundamentales" del Centro de Datos) en vez de recalcular
    # activo por activo: una sola pasada, con las compuertas de checksum/
    # huecos ya validadas, y visible con su propia barra+tabla por código.
    from app.services.technical_service import update_indicator_history
    if progress_cb:
        progress_cb(0, 1, "Precios actualizados. Calculando indicadores...")
    ind_result = update_indicator_history(progress_cb=progress_cb)
    # Acumulado, no solo el de precios: success + len(errors) tiene que
    # dar total, si no el resumen final ("X/Y OK") no cierra.
    summary["total"]   += ind_result.get("total", 0)
    summary["success"] += ind_result.get("success", 0)
    summary["errors"].extend(ind_result.get("errors", []))

    # Actualizar fundamentales para activos con fuente configurada — ahora
    # encadena internamente a _run_ratios_and_backfill (ver
    # update_all_fundamentals/skip_ratios en fundamental_service.py).
    try:
        from app.services.fundamental_service import update_all_fundamentals
        if progress_cb:
            progress_cb(0, 1, "Actualizando fundamentales...")
        fund_result = update_all_fundamentals(progress_cb=progress_cb)
        summary["total"]   += fund_result.get("total", 0)
        summary["success"] += fund_result.get("success", 0)
        summary["errors"].extend(fund_result.get("errors", []))
    except Exception as exc:
        logger.warning("Error actualizando fundamentales: %s", exc)

    # Refrescar agregados de tendencia por grupo (mapa de mercado)
    from app.services.technical_service import _refresh_group_scores
    _refresh_group_scores()

    return summary


def redownload_prices(asset_ids: list[int] | None = None, progress_cb=None) -> dict:
    """Redescarga el historial de precios completo desde la fuente.
    El historial existente solo se borra si la descarga nueva tiene datos.
    Si asset_ids es None, aplica a todos los activos activos.

    Con una selección puntual, el recálculo de indicadores/ratios que sigue
    a la descarga es un rebuild COMPLETO por activo
    (_rebuild_indicators_for_assets), no el delta que usan los jobs
    globales (_chain_to_indicator_and_ratio_delta) — los precios son
    enteramente nuevos, así que conviene recalcular todo en vez de confiar
    en atajos que podrían no detectar una corrección retroactiva de un
    precio viejo. Antes esto además recorría el universo entero (~2 min)
    aunque se hubiese redescargado un solo ticker puntual desde
    /admin/prices ("Redescargar seleccionados").

    La redescarga GLOBAL va por el camino batch (full=True: historia completa
    para todos, borrado por-activo dentro de cada transacción). La selección
    puntual sigue el camino secuencial por activo — siempre es chica."""
    from app.services.asset_service import get_assets

    if asset_ids is None:
        summary = _bulk_download_assets(get_assets(), progress_cb, full=True)
        return _chain_to_indicator_and_ratio_delta(progress_cb, summary)

    s = get_session()
    assets = s.query(Asset).filter(Asset.id.in_(asset_ids)).all()

    total   = len(assets)
    summary = {"total": total, "success": 0, "errors": []}
    for i, asset in enumerate(assets, 1):
        if progress_cb:
            progress_cb(i, total, asset.ticker)
        try:
            update_asset_prices(asset.id, full=True, skip_indicators=True)
            summary["success"] += 1
        except Exception as exc:
            summary["errors"].append({"ticker": asset.ticker, "error": str(exc)})

    if summary.get("total", 0) == 0:
        return summary
    if progress_cb:
        progress_cb(0, 1, "Precios actualizados. Recalculando indicadores...")
    ind_result = _rebuild_indicators_for_assets(progress_cb, asset_ids)
    summary["total"]   += ind_result["total"]
    summary["success"] += ind_result["success"]
    summary["errors"].extend(ind_result["errors"])
    return summary


def get_prices_df(asset_id: int):
    """Devuelve todos los precios del activo como DataFrame ordenado por fecha."""
    s = get_session()
    rows = (
        s.query(Price.date, Price.open, Price.high, Price.low, Price.close, Price.volume)
        .filter(Price.asset_id == asset_id)
        .order_by(Price.date)
        .all()
    )
    if not rows:
        return pd.DataFrame(columns=["date", "open", "high", "low", "close", "volume"])
    return pd.DataFrame(rows, columns=["date", "open", "high", "low", "close", "volume"])


def get_all_assets_with_log() -> list[dict]:
    """Devuelve todos los activos activos con su último log de actualización (si existe)."""
    from app.models import IndicatorUpdateLog

    s = get_session()
    assets = s.query(Asset).order_by(Asset.ticker).all()
    logs     = {log.asset_id: log for log in s.query(PriceUpdateLog).all()}
    ind_logs = {log.asset_id: log for log in s.query(IndicatorUpdateLog).all()}
    result = []
    for asset in assets:
        log     = logs.get(asset.id)
        ind_log = ind_logs.get(asset.id)
        result.append({
            "ticker": asset.ticker,
            "asset_name": asset.name,
            "last_attempt_at": str(log.last_attempt_at)[:19] if log else "—",
            "result": ("Éxito" if log.success else "Error") if log else "—",
            "error_detail": (log.error_detail or "") if log else "",
            "last_indicator_at": str(ind_log.last_attempt_at)[:19] if ind_log else "—",
            "indicator_result": ("Éxito" if ind_log.success else "Error") if ind_log else "—",
            "indicator_error_detail": (ind_log.error_detail or "") if ind_log else "",
        })
    return result


def clear_update_logs() -> None:
    s = get_session()
    s.query(PriceUpdateLog).delete()
    s.commit()


def get_latest_prices_all() -> list[dict]:
    """Devuelve el último precio (OHLCV) de cada activo con sus datos de referencia."""
    from sqlalchemy import func
    from app.models import Currency, InstrumentType, Country, Market, PriceSource

    s = get_session()
    subq = (
        s.query(Price.asset_id, func.max(Price.date).label("max_date"))
        .group_by(Price.asset_id)
        .subquery()
    )
    rows = (
        s.query(Price, Asset, Currency, InstrumentType, Country, Market, PriceSource)
        .join(subq, (Price.asset_id == subq.c.asset_id) & (Price.date == subq.c.max_date))
        .join(Asset,          Price.asset_id == Asset.id)
        .outerjoin(Currency,       Asset.currency_id        == Currency.id)
        .outerjoin(InstrumentType, Asset.instrument_type_id == InstrumentType.id)
        .outerjoin(Country,        Asset.country_id         == Country.id)
        .outerjoin(Market,         Asset.market_id          == Market.id)
        .join(PriceSource,         Asset.price_source_id    == PriceSource.id)
        .order_by(Asset.ticker)
        .all()
    )
    return [
        {
            "ticker":          asset.ticker,
            "name":            asset.name,
            "date":            str(price.date),
            "open":            price.open,
            "high":            price.high,
            "low":             price.low,
            "close":           price.close,
            "volume":          price.volume,
            "currency":        currency.name        if currency        else "",
            "instrument_type": instrument_type.name if instrument_type else "",
            "country":         country.name         if country         else "",
            "market":          market.name          if market          else "",
            "price_source":    price_source.name    if price_source    else "",
        }
        for price, asset, currency, instrument_type, country, market, price_source in rows
    ]
