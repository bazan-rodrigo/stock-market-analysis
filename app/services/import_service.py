"""
Servicio de importación masiva de activos desde Excel.
"""
import logging
from datetime import datetime
from io import BytesIO
import openpyxl
import pandas as pd

from app.database import get_session
from app.models import Asset, ImportLog, PriceSource
from app.sources.registry import get_source

logger = logging.getLogger(__name__)

TEMPLATE_COLUMNS = [
    "ticker",
    "fuente_precios",
    "nombre",
    "pais_iso",
    "mercado",
    "tipo_instrumento",
    "moneda_iso",
    "sector",
    "industria",
    "benchmark_ticker",
]


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
            a.price_source.name          if a.price_source    else "",
            a.name                       or "",
            a.country.iso_code           if a.country         else "",
            a.market.name                if a.market          else "",
            a.instrument_type.name       if a.instrument_type else "",
            a.currency.iso_code          if a.currency        else "",
            a.sector.name                if a.sector          else "",
            a.industry.name              if a.industry        else "",
            ticker_by_id.get(a.benchmark_id, "") if a.benchmark_id else "",
        ])
    buf = BytesIO()
    wb.save(buf)
    return buf.getvalue()


def import_from_excel(file_bytes: bytes, progress_cb=None) -> list[dict]:
    """
    Procesa el archivo Excel y devuelve una lista de resultados por ticker.
    Cada elemento tiene: ticker, status ("imported"|"skipped"|"error"), detail.
    Persiste el resultado en import_log (upsert por ticker).
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

    # benchmark_ticker de cada fila, para la segunda pasada
    pending_benchmarks: list[tuple[str, str]] = []  # [(ticker, benchmark_ticker)]

    for i, (_, row) in enumerate(df.iterrows()):
        if progress_cb:
            progress_cb(i + 1, total)
        ticker = str(row.get("ticker", "")).strip().upper()
        if not ticker or ticker.startswith("──") or ticker.startswith("--"):
            continue

        source_name = str(row.get("fuente_precios", "")).strip()
        status = "error"
        detail = ""

        try:
            # Validar fuente
            source_obj = s.query(PriceSource).filter(
                PriceSource.name == source_name, PriceSource.active == True
            ).first()
            if source_obj is None:
                raise ValueError(f"Fuente '{source_name}' no encontrada o inactiva")

            # Verificar duplicado
            exists = s.query(Asset).filter(Asset.ticker == ticker).first()
            if exists:
                status = "skipped"
                detail = "Ticker ya existe en la base de datos"
                raise _Skipped(detail)

            # Validar y autocompletar desde la fuente
            source = get_source(source_name)
            val_result = source.validate_ticker(ticker)
            if not val_result.valid:
                raise ValueError(f"Ticker inválido: {val_result.error}")

            meta = val_result.metadata

            # Resolver campos opcionales del Excel (tienen prioridad sobre autocompletado)
            name = _first_nonempty(row.get("nombre"), getattr(meta, "name", None), ticker)

            # Resolver FKs — Excel tiene prioridad, meta de la fuente como fallback
            country_val  = _first_nonempty(row.get("pais_iso"),         getattr(meta, "country",       None))
            market_val   = _first_nonempty(row.get("mercado"),           getattr(meta, "exchange_name", None), getattr(meta, "exchange", None))
            currency_val = _first_nonempty(row.get("moneda_iso"),        getattr(meta, "currency_iso",  None))
            itype_val    = _first_nonempty(row.get("tipo_instrumento"),  getattr(meta, "quote_type",    None))
            sector_val   = _first_nonempty(row.get("sector"),            getattr(meta, "sector",        None))
            industry_val = _first_nonempty(row.get("industria"),         getattr(meta, "industry",      None))

            country_id  = _resolve_country(country_val)
            market_id   = _resolve_market(market_val)
            currency_id = _resolve_currency(currency_val)
            itype_id    = _resolve_instrument_type(itype_val)
            sector_id   = _resolve_sector(sector_val)
            industry_id = _resolve_industry(industry_val, sector_id)

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
            )
            s.add(asset)
            s.flush()
            status = "imported"
            detail = "Importado correctamente"

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
        try:
            log = s.query(ImportLog).filter(ImportLog.ticker == ticker).first()
            if log is None:
                log = ImportLog(ticker=ticker, status=status, detail=detail)
                s.add(log)
            else:
                log.status = status
                log.detail = detail
                log.attempted_at = datetime.utcnow()
            s.commit()
        except Exception as log_exc:
            s.rollback()
            logger.warning("Error guardando log para %s: %s", ticker, log_exc)

        results.append({"ticker": ticker, "status": status, "detail": detail})

    # Segunda pasada: asignar benchmarks una vez que todos los activos están creados
    if pending_benchmarks:
        result_map = {r["ticker"]: r for r in results}
        for ticker, bm_ticker in pending_benchmarks:
            try:
                asset = s.query(Asset).filter(Asset.ticker == ticker).first()
                bm    = s.query(Asset).filter(Asset.ticker == bm_ticker).first()
                if asset is None:
                    continue
                if bm is None:
                    detail = result_map[ticker]["detail"]
                    result_map[ticker]["detail"] = f"{detail} (benchmark '{bm_ticker}' no encontrado)"
                    _update_log(s, ticker, result_map[ticker]["status"],
                                result_map[ticker]["detail"])
                else:
                    asset.benchmark_id = bm.id
                    s.commit()
            except Exception as exc:
                s.rollback()
                logger.warning("Error asignando benchmark %s → %s: %s", ticker, bm_ticker, exc)

    return results


def _update_log(s, ticker: str, status: str, detail: str) -> None:
    try:
        log = s.query(ImportLog).filter(ImportLog.ticker == ticker).first()
        if log:
            log.status = status
            log.detail = detail
            log.attempted_at = datetime.utcnow()
            s.commit()
    except Exception as exc:
        s.rollback()
        logger.warning("Error actualizando log %s: %s", ticker, exc)


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


def _resolve_country(name):
    if not _valid(name):
        return None
    from app.services.reference_service import get_or_create_country
    obj, _ = get_or_create_country(name)
    return obj.id


def _resolve_market(name, country_id=None):
    if not _valid(name):
        return None
    from app.services.reference_service import get_or_create_market
    obj, _ = get_or_create_market(name, country_id=country_id)
    return obj.id


def _resolve_currency(iso):
    if not _valid(iso):
        return None
    from app.services.reference_service import get_or_create_currency
    obj, _ = get_or_create_currency(iso)
    return obj.id


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


