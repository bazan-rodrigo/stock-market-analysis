"""
Servicio de importación masiva de eventos de mercado desde Excel.
"""
import logging
from datetime import datetime, date
from io import BytesIO

import openpyxl
import pandas as pd

from app.database import get_session
from app.models import MarketEvent

logger = logging.getLogger(__name__)

TEMPLATE_COLUMNS = [
    "nombre",
    "fecha_inicio",
    "fecha_fin",
    "alcance",
    "pais",
    "color",
]


def generate_template() -> bytes:
    """Exporta los eventos actuales de la BD como Excel descargable."""
    from app.models import Country
    s = get_session()
    events = s.query(MarketEvent).order_by(MarketEvent.start_date).all()
    countries = {c.id: c.name for c in s.query(Country).all()}

    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "Eventos"
    ws.append(TEMPLATE_COLUMNS)
    for e in events:
        ws.append([
            e.name,
            e.start_date.isoformat() if e.start_date else "",
            e.end_date.isoformat()   if e.end_date   else "",
            e.scope,
            countries.get(e.country_id, "") if e.country_id else "",
            e.color or "#ff9800",
        ])
    buf = BytesIO()
    wb.save(buf)
    return buf.getvalue()


def import_from_excel(file_bytes: bytes) -> list[dict]:
    try:
        df = pd.read_excel(BytesIO(file_bytes), dtype=str)
    except Exception as exc:
        raise ValueError(f"Error leyendo el archivo Excel: {exc}") from exc

    df.columns = [c.strip().lower() for c in df.columns]

    required = {"nombre", "fecha_inicio", "fecha_fin", "alcance"}
    missing = required - set(df.columns)
    if missing:
        raise ValueError(f"Columnas obligatorias faltantes: {missing}")

    results = []
    s = get_session()

    for _, row in df.iterrows():
        nombre = str(row.get("nombre", "")).strip()
        if not nombre or nombre.startswith("──") or nombre.startswith("--"):
            continue

        status = "error"
        detail = ""

        try:
            start = _parse_date(row.get("fecha_inicio"))
            end   = _parse_date(row.get("fecha_fin"))
            if start is None or end is None:
                raise ValueError("Fechas inválidas o faltantes")
            if end < start:
                raise ValueError("fecha_fin debe ser >= fecha_inicio")

            alcance = str(row.get("alcance", "global")).strip().lower()
            if alcance not in ("global", "country", "asset"):
                raise ValueError(f"Alcance inválido: '{alcance}' — usá global, country o asset")

            color = str(row.get("color", "#ff9800")).strip() or "#ff9800"

            country_id = None
            if alcance == "country":
                pais = str(row.get("pais", "")).strip()
                if not pais:
                    raise ValueError("pais es obligatorio cuando alcance=country")
                from app.services.reference_service import get_or_create_country
                country, _ = get_or_create_country(pais)
                country_id = country.id

            event = MarketEvent(
                name=nombre,
                start_date=start,
                end_date=end,
                scope=alcance,
                country_id=country_id,
                color=color,
            )
            s.add(event)
            s.flush()
            s.commit()
            status = "imported"
            detail = "Importado correctamente"

        except Exception as exc:
            s.rollback()
            status = "error"
            detail = str(exc)
            logger.warning("Import error para evento '%s': %s", nombre, exc)

        results.append({"nombre": nombre, "status": status, "detail": detail})

    return results


def _parse_date(value) -> date | None:
    if value is None:
        return None
    s = str(value).strip()
    if s.lower() in ("nan", "none", ""):
        return None
    for fmt in ("%Y-%m-%d", "%d/%m/%Y", "%m/%d/%Y"):
        try:
            return datetime.strptime(s, fmt).date()
        except ValueError:
            continue
    return None
