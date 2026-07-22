"""
Servicio de importación masiva de activos desde Excel.
"""
import logging
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime
from io import BytesIO
import openpyxl
import pandas as pd

from app.database import get_session
from app.models import Asset, FundamentalSource, ImportLog, PriceSource

logger = logging.getLogger(__name__)


class _ValidationFailure:
    """Resultado duck-typed compatible con TickerValidationResult para el
    camino de error del prefetch. NO se importa app.sources acá arriba a
    propósito: este módulo evita cargar yfinance en el import (los tests y
    esta PC de desarrollo no lo tienen) — todo import de fuentes es diferido.
    """
    valid = False
    metadata = None

    def __init__(self, error: str):
        self.error = error

TEMPLATE_COLUMNS = [
    "ticker",
    "fuente_precios",
    "nombre",
    "pais_iso",
    "mercado",
    "tipo_instrumento",
    "moneda",
    "sector",
    "industria",
    "benchmark_ticker",
    "fuente_fundamentales",
]

# Validación contra la fuente en paralelo (fase 1 del import): es red pura —
# el GIL no molesta — y era el costo dominante del import secuencial.
_VALIDATE_WORKERS = 6
_VALIDATE_RETRIES = 2    # reintentos ante error transitorio (rate-limit/red)
_BACKOFF_BASE_S   = 2.0  # espera del primer reintento; exponencial (2s, 4s…)

# Campos del Excel que la metadata de la fuente puede autocompletar. Si la
# fila ya los trae todos (caso típico: re-import de una planilla exportada),
# no hace falta pedir metadata — alcanza el chequeo barato de existencia.
_AUTOCOMPLETE_COLS = ("nombre", "pais_iso", "mercado", "moneda",
                      "tipo_instrumento", "sector", "industria")


def _needs_metadata(row) -> bool:
    """True si a la fila le falta algún campo autocompletable → hay que
    pedirle la metadata a la fuente (el .info lento de Yahoo)."""
    return any(not _valid(row.get(c)) for c in _AUTOCOMPLETE_COLS)


def _is_transient_error(error: str | None) -> bool:
    """Errores de validación que ameritan reintento (no significan
    'el ticker no existe'): rate-limit y problemas de red."""
    if not error:
        return False
    e = error.lower()
    return any(t in e for t in ("429", "rate limit", "timeout", "timed out",
                                "connection", "temporarily"))


def _validate_with_retry(source, ticker: str, need_metadata: bool):
    """validate_ticker con reintentos y backoff exponencial ante errores
    transitorios — con el pool paralelo, un 429 aislado de Yahoo no debe
    marcar el ticker como inválido."""
    result = source.validate_ticker(ticker, need_metadata=need_metadata)
    for attempt in range(_VALIDATE_RETRIES):
        if result.valid or not _is_transient_error(result.error):
            return result
        time.sleep(_BACKOFF_BASE_S * (2 ** attempt))
        result = source.validate_ticker(ticker, need_metadata=need_metadata)
    return result


def _row_ticker(row) -> str:
    """Ticker normalizado de la fila; '' para filas vacías o separadores."""
    ticker = str(row.get("ticker", "") or "").strip().upper()
    if not ticker or ticker.startswith("──") or ticker.startswith("--"):
        return ""
    return ticker


def _prefetch_validations(rows_list, price_sources, existing_tickers,
                          progress_cb=None) -> dict:
    """Fase 1 del import: resuelve validate_ticker en paralelo para las filas
    que van a intentar el alta (ticker nuevo + fuente conocida). Red pura —
    acá no se toca la BD: toda la escritura queda en el hilo principal.

    Devuelve {(fuente, ticker): TickerValidationResult}. Un mismo ticker
    repetido en el archivo se valida una sola vez; si alguna de sus filas
    necesita metadata, se pide para el grupo (la más exigente gana).
    """
    jobs: dict[tuple[str, str], bool] = {}
    for row in rows_list:
        ticker = _row_ticker(row)
        if not ticker or ticker in existing_tickers:
            continue
        source_name = str(row.get("fuente_precios", "")).strip()
        if source_name not in price_sources:
            continue  # el pase de alta reporta el error sin gastar red
        key = (source_name, ticker)
        jobs[key] = jobs.get(key, False) or _needs_metadata(row)

    if not jobs:
        return {}

    # Instanciar las fuentes en el hilo principal: get_source importa
    # yfinance la primera vez — mejor fuera de los threads. Se envuelve por
    # nombre: una fuente que está en la tabla PriceSource pero NO en el
    # registry de implementaciones (dada de alta o renombrada desde el ABM)
    # hace fallar get_source. Sin este try la excepción volteaba el import
    # entero (0 filas, 0 logs); ahora esos jobs se dejan sin prefetch y el
    # fallback del pase de alta —dentro del try por fila— los reporta como
    # error de esa fila, sin arrastrar al resto del archivo.
    from app.sources.registry import get_source
    sources: dict[str, object] = {}
    for name in {n for n, _ in jobs}:
        try:
            sources[name] = get_source(name)
        except Exception as exc:
            logger.warning("Fuente '%s' sin implementación en el registry: "
                           "sus filas se validarán en el pase de alta (%s)",
                           name, exc)

    results: dict[tuple[str, str], object] = {}
    with ThreadPoolExecutor(max_workers=_VALIDATE_WORKERS) as pool:
        futures = {
            pool.submit(_validate_with_retry, sources[name], ticker, need_meta):
                (name, ticker)
            for (name, ticker), need_meta in jobs.items()
            if name in sources
        }
        total = len(futures)
        done = 0
        for fut in as_completed(futures):
            key = futures[fut]
            try:
                results[key] = fut.result()
            except Exception as exc:
                # Una validación rota no voltea el import: la fila termina
                # en error con el detalle, como siempre.
                results[key] = _ValidationFailure(str(exc))
            done += 1
            if progress_cb:
                progress_cb(done, total, "Validando tickers...")
    return results


def generate_template() -> bytes:
    """Exporta los activos actuales de la BD como Excel descargable."""
    s = get_session()
    assets = s.query(Asset).order_by(Asset.ticker).all()

    # Mapa id → ticker para resolver benchmark
    ticker_by_id = {a.id: a.ticker for a in assets}

    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "Activos"
    ws.append(TEMPLATE_COLUMNS)
    for a in assets:
        ws.append([
            a.ticker,
            a.price_source.name          if a.price_source          else "",
            a.name                       or "",
            a.country.iso_code           if a.country               else "",
            a.market.name                if a.market                else "",
            a.instrument_type.name       if a.instrument_type       else "",
            a.currency.name              if a.currency              else "",
            a.sector.name                if a.sector                else "",
            a.industry.name              if a.industry              else "",
            ticker_by_id.get(a.benchmark_id, "") if a.benchmark_id  else "",
            a.fundamental_source.name    if a.fundamental_source    else "",
        ])
    buf = BytesIO()
    wb.save(buf)
    return buf.getvalue()


def import_from_excel(file_bytes: bytes, progress_cb=None) -> list[dict]:
    """
    Procesa el archivo Excel y devuelve una lista de resultados por ticker.
    Cada elemento tiene: ticker, status ("imported"|"skipped"|"error"), detail.
    Persiste el resultado en import_log (upsert por ticker).

    Dos fases: primero la validación contra la fuente en paralelo (la parte
    lenta — ver _prefetch_validations), después el alta en BD secuencial.
    progress_cb(actual, total, mensaje) se reinicia al cambiar de fase.
    """
    try:
        df = pd.read_excel(BytesIO(file_bytes), dtype=str)
    except Exception as exc:
        raise ValueError(f"Error leyendo el archivo Excel: {exc}") from exc

    df.columns = [c.strip().lower() for c in df.columns]

    required = {"ticker", "fuente_precios"}
    missing = required - set(df.columns)
    if missing:
        raise ValueError(f"Columnas obligatorias faltantes en el archivo: {missing}")

    results = []
    s = get_session()
    total = len(df)

    # Pre-cargar fuentes y tickers existentes (evita N+1 queries por fila)
    price_sources = {ps.name: ps for ps in s.query(PriceSource).all()}
    fund_sources  = {fs.name: fs for fs in s.query(FundamentalSource).all()}
    existing_tickers = {t for (t,) in s.query(Asset.ticker).all()}

    # Logs precargados en un mapa (1 query) — antes había un SELECT por fila.
    # El commit por fila se conserva: es la durabilidad del log ante un
    # error a mitad de archivo.
    logs_by_ticker = {l.ticker: l for l in s.query(ImportLog).all()}

    # Caché por corrida de los resolvers de referencia (país/mercado/moneda/
    # tipo/sector/industria) — ver _cached_resolve.
    resolve_cache: dict = {}

    # benchmark_ticker de cada fila, para la segunda pasada
    pending_benchmarks: list[tuple[str, str]] = []  # [(ticker, benchmark_ticker)]

    rows_list = df.to_dict("records")

    # ── Fase 1: validación de red en paralelo ────────────────────────────
    val_results = _prefetch_validations(
        rows_list, price_sources, existing_tickers, progress_cb)

    # ── Fase 2: alta en BD (secuencial, hilo principal) ──────────────────
    for i, row in enumerate(rows_list):
        if progress_cb:
            progress_cb(i + 1, total, "Importando...")
        ticker = _row_ticker(row)
        if not ticker:
            continue

        source_name = str(row.get("fuente_precios", "")).strip()
        status = "error"
        detail = ""

        try:
            # Validar fuente (precargada)
            source_obj = price_sources.get(source_name)
            if source_obj is None:
                raise ValueError(f"Fuente '{source_name}' no encontrada")

            # Verificar duplicado (precargado)
            if ticker in existing_tickers:
                status = "skipped"
                detail = "Ticker ya existe en la base de datos"
                raise _Skipped(detail)

            # Resultado de la validación prefetcheada. El prefetch cubre toda
            # fila con fuente conocida y ticker nuevo; cae acá el caso de una
            # fuente que está en PriceSource pero no en el registry (ver
            # _prefetch_validations): get_source lanza y esta fila queda en
            # error sin voltear el resto del archivo.
            val_result = val_results.get((source_name, ticker))
            if val_result is None:
                from app.sources.registry import get_source
                val_result = _validate_with_retry(
                    get_source(source_name), ticker, _needs_metadata(row))
            if not val_result.valid:
                raise ValueError(f"Ticker inválido: {val_result.error}")

            meta = val_result.metadata

            # Resolver campos opcionales del Excel (tienen prioridad sobre autocompletado)
            name = _first_nonempty(row.get("nombre"), getattr(meta, "name", None), ticker)

            # Resolver FKs — Excel tiene prioridad, meta de la fuente como fallback
            country_val  = _first_nonempty(row.get("pais_iso"),         getattr(meta, "country",       None))
            market_val   = _first_nonempty(row.get("mercado"),           getattr(meta, "exchange_name", None), getattr(meta, "exchange", None))
            currency_val = row.get("moneda", "")
            currency_iso = getattr(meta, "currency_iso", None)
            itype_val    = _first_nonempty(row.get("tipo_instrumento"),  getattr(meta, "quote_type",    None))
            sector_val   = _first_nonempty(row.get("sector"),            getattr(meta, "sector",        None))
            industry_val = _first_nonempty(row.get("industria"),         getattr(meta, "industry",      None))

            country_id  = _cached_resolve(resolve_cache, "country", country_val, _resolve_country)
            market_id   = _cached_resolve(resolve_cache, "market", market_val, _resolve_market)
            currency_id = _cached_resolve(resolve_cache, "currency", currency_val, _resolve_currency, currency_iso)
            itype_id    = _cached_resolve(resolve_cache, "itype", itype_val, _resolve_instrument_type)
            sector_id   = _cached_resolve(resolve_cache, "sector", sector_val, _resolve_sector)
            industry_id = _cached_resolve(resolve_cache, "industry", industry_val, _resolve_industry, sector_id)

            # _first_nonempty y no str(...) directo: una celda vacía del Excel
            # llega como NaN y str(NaN) es "nan" — disparaba la advertencia
            # de fuente inexistente en toda fila sin fundamentales.
            fund_source_name = _first_nonempty(row.get("fuente_fundamentales"))
            fund_source_id   = fund_sources[fund_source_name].id if fund_source_name in fund_sources else None
            # A diferencia de fuente_precios (que da error), un nombre de fuente
            # de fundamentales que no matchea dejaba el activo sin fuente y sin
            # avisar. La fila se importa igual, pero se anota la advertencia.
            fund_warn = (f"Fuente de fundamentales '{fund_source_name}' no "
                         f"encontrada: el activo queda sin fundamentales."
                         if fund_source_name and fund_source_id is None else None)

            asset = Asset(
                ticker=ticker,
                name=name,
                country_id=country_id,
                market_id=market_id,
                instrument_type_id=itype_id,
                currency_id=currency_id,
                price_source_id=source_obj.id,
                sector_id=sector_id,
                industry_id=industry_id,
                fundamental_source_id=fund_source_id,
            )
            s.add(asset)
            s.flush()
            existing_tickers.add(ticker)  # evita duplicados dentro del mismo archivo
            status = "imported"
            detail = ("Importado correctamente" if not fund_warn
                      else f"Importado con advertencia: {fund_warn}")

            bm_ticker = _first_nonempty(row.get("benchmark_ticker"))
            if bm_ticker:
                pending_benchmarks.append((ticker, bm_ticker))

        except _Skipped:
            pass
        except Exception as exc:
            s.rollback()
            status = "error"
            detail = str(exc)
            logger.warning("Import error para ticker %s: %s", ticker, exc)

        # Upsert en import_log y commit por ticker para que los errores
        # de un ticker no anulen los logs de los anteriores.
        log_created = False
        try:
            log = logs_by_ticker.get(ticker)
            if log is None:
                log = ImportLog(ticker=ticker, status=status, detail=detail)
                s.add(log)
                logs_by_ticker[ticker] = log
                log_created = True
            else:
                log.status = status
                log.detail = detail
                log.attempted_at = datetime.utcnow()
            s.commit()
        except Exception as log_exc:
            s.rollback()
            if log_created:
                # el add se deshizo — que otra fila del mismo ticker lo recree
                logs_by_ticker.pop(ticker, None)
            logger.warning("Error guardando log para %s: %s", ticker, log_exc)

        results.append({"ticker": ticker, "status": status, "detail": detail})

    # Segunda pasada: asignar benchmarks una vez que todos los activos están
    # creados — mapa ticker→id precargado (1 query) y un solo commit, en vez
    # de 2 SELECTs + commit por cada benchmark.
    if pending_benchmarks:
        result_map = {r["ticker"]: r for r in results}
        ids_by_ticker = {t: i for (t, i) in s.query(Asset.ticker, Asset.id).all()}
        updates = []
        for ticker, bm_ticker in pending_benchmarks:
            asset_id = ids_by_ticker.get(ticker)
            if asset_id is None:
                continue
            # Normalizado como se almacenan los tickers (el lookup exacto de
            # antes dependía de la collation case-insensitive de MySQL)
            bm_id = ids_by_ticker.get(bm_ticker.strip().upper())
            if bm_id is None:
                detail = result_map[ticker]["detail"]
                result_map[ticker]["detail"] = f"{detail} (benchmark '{bm_ticker}' no encontrado)"
                log = logs_by_ticker.get(ticker)
                if log is not None:
                    log.status = result_map[ticker]["status"]
                    log.detail = result_map[ticker]["detail"]
                    log.attempted_at = datetime.utcnow()
            else:
                updates.append({"id": asset_id, "benchmark_id": bm_id})
        try:
            if updates:
                s.bulk_update_mappings(Asset, updates)
            s.commit()
        except Exception as exc:
            s.rollback()
            logger.warning("Error asignando benchmarks en batch: %s", exc)

    return results


def get_import_logs() -> list[ImportLog]:
    s = get_session()
    return s.query(ImportLog).order_by(ImportLog.attempted_at.desc()).all()


def clear_import_logs() -> None:
    s = get_session()
    s.query(ImportLog).delete()
    s.commit()


# ---------------------------------------------------------------------------
# Helpers internos
# ---------------------------------------------------------------------------

class _Skipped(Exception):
    pass


def _first_nonempty(*values) -> str:
    for v in values:
        if v and str(v).strip() and str(v).strip().lower() not in ("nan", "none"):
            return str(v).strip()
    return ""


def _cached_resolve(cache: dict, kind: str, value, fn, *args):
    """Memoiza por corrida el resultado de un _resolve_* — misma cadena de
    entrada (case-insensitive, igual que la resolución por alias/ilike) y
    mismos args extra → mismo id. Sin esto, un archivo de 10k filas repetía
    hasta 6 queries de catálogo por fila."""
    key = (kind, str(value).strip().lower(), args)
    if key not in cache:
        cache[key] = fn(value, *args)
    return cache[key]


def _resolve_country(name):
    if not _valid(name):
        return None
    # La columna se llama `pais_iso` y el export escribe el CÓDIGO ISO, pero el
    # autocompletado de la fuente pasa el NOMBRE. Se intenta primero por código
    # ISO: sin esto, reimportar una planilla exportada creaba países llamados
    # "US", "AR"… (el resolver por nombre no encontraba "US" y lo daba de alta).
    from app.database import get_session
    from app.models import Country
    from app.services.db_compat import ci_equals
    from app.services.reference_service import get_or_create_country
    value = str(name).strip()
    s = get_session()
    by_iso = s.query(Country).filter(ci_equals(Country.iso_code, value)).first()
    if by_iso is not None:
        return by_iso.id
    obj, _ = get_or_create_country(value)
    return obj.id


def _resolve_market(name, country_id=None):
    if not _valid(name):
        return None
    from app.services.reference_service import get_or_create_market
    obj, _ = get_or_create_market(name, country_id=country_id)
    return obj.id


def _resolve_currency(name, iso=None):
    from app.services.reference_service import get_or_create_currency, get_or_create_currency_by_name
    if _valid(name):
        obj, _ = get_or_create_currency_by_name(name)
        return obj.id
    if _valid(iso):
        obj, _ = get_or_create_currency(iso)
        return obj.id
    return None


def _resolve_instrument_type(name):
    if not _valid(name):
        return None
    from app.services.reference_service import get_or_create_instrument_type
    obj, _ = get_or_create_instrument_type(name)
    return obj.id


def _resolve_sector(name):
    if not _valid(name):
        return None
    from app.services.reference_service import get_or_create_sector
    obj, _ = get_or_create_sector(name)
    return obj.id


def _resolve_industry(name, sector_id=None):
    if not _valid(name):
        return None
    from app.services.reference_service import get_or_create_industry
    obj, _ = get_or_create_industry(name, sector_id=sector_id)
    return obj.id


def _valid(v) -> bool:
    return bool(v) and str(v).strip().lower() not in ("nan", "none", "")


