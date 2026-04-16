"""
Servicio de importación masiva de activos desde Excel.
"""
import logging
from datetime import datetime
from io import BytesIO
from typing import Optional

import openpyxl
import pandas as pd

from app.database import get_session
from app.models import Asset, Currency, ImportLog, Industry, Market, PriceSource, Sector
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
    "activo",
]


def generate_template() -> bytes:
    """Genera un archivo Excel vacío con las columnas de importación."""
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "Activos"
    ws.append(TEMPLATE_COLUMNS)
    # Fila de ejemplo
    ws.append([
        "AAPL",
        "Yahoo Finance",
        "Apple Inc.",
        "US",
        "NASDAQ",
        "Acción",
        "USD",
        "Technology",
        "Consumer Electronics",
        "SI",
    ])
    buf = BytesIO()
    wb.save(buf)
    return buf.getvalue()


def import_from_excel(file_bytes: bytes) -> list[dict]:
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

    for _, row in df.iterrows():
        ticker = str(row.get("ticker", "")).strip().upper()
        if not ticker:
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
            active_str = str(row.get("activo", "SI")).strip().upper()
            active = active_str not in ("NO", "0", "FALSE", "N")

            # Resolver FKs opcionales
            country_id = _resolve_country(row.get("pais_iso"), s)
            market_id = _resolve_market(row.get("mercado"), s)
            currency_id = _resolve_currency(
                row.get("moneda_iso") or getattr(meta, "currency_iso", None), s
            )
            itype_id = _resolve_instrument_type(row.get("tipo_instrumento"), s)
            sector_id = _resolve_sector(
                row.get("sector") or getattr(meta, "sector", None), s
            )
            industry_id = _resolve_industry(
                row.get("industria") or getattr(meta, "industry", None), s
            )

            if not all([country_id, market_id, currency_id, itype_id]):
                raise ValueError(
                    "Faltan datos obligatorios: país, mercado, moneda o tipo de instrumento"
                )

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
                active=active,
            )
            s.add(asset)
            s.flush()
            status = "imported"
            detail = "Importado correctamente"

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


def _resolve_country(iso, session):
    from app.models import Country
    if not iso or str(iso).strip().lower() in ("nan", "none", ""):
        return None
    return _id_or_none(
        session.query(Country).filter(Country.iso_code == str(iso).strip().upper()).first()
    )


def _resolve_market(name, session):
    if not name or str(name).strip().lower() in ("nan", "none", ""):
        return None
    return _id_or_none(
        session.query(Market).filter(Market.name == str(name).strip()).first()
    )


def _resolve_currency(iso, session):
    if not iso or str(iso).strip().lower() in ("nan", "none", ""):
        return None
    return _id_or_none(
        session.query(Currency).filter(Currency.iso_code == str(iso).strip().upper()).first()
    )


def _resolve_instrument_type(name, session):
    from app.models import InstrumentType
    if not name or str(name).strip().lower() in ("nan", "none", ""):
        return None
    return _id_or_none(
        session.query(InstrumentType).filter(
            InstrumentType.name == str(name).strip()
        ).first()
    )


def _resolve_sector(name, session):
    if not name or str(name).strip().lower() in ("nan", "none", ""):
        return None
    obj = session.query(Sector).filter(Sector.name == str(name).strip()).first()
    if obj is None:
        obj = Sector(name=str(name).strip())
        session.add(obj)
        session.flush()
    return obj.id


def _resolve_industry(name, session):
    if not name or str(name).strip().lower() in ("nan", "none", ""):
        return None
    obj = session.query(Industry).filter(Industry.name == str(name).strip()).first()
    return _id_or_none(obj)


def _id_or_none(obj) -> Optional[int]:
    return obj.id if obj else None
