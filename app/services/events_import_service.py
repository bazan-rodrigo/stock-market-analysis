"""
Servicio de importación masiva de eventos de mercado desde Excel.
"""
import logging
from datetime import datetime, date
from io import BytesIO
from pathlib import Path

import pandas as pd

from app.database import get_session
from app.models import MarketEvent

logger = logging.getLogger(__name__)

TEMPLATE_COLUMNS = [
    "nombre",
    "fecha_inicio",
    "fecha_fin",
    "alcance",
    "pais_iso",
    "color",
]

_TEMPLATE_FILE = Path(__file__).resolve().parent.parent.parent / "eventos_prueba.xlsx"


def generate_template() -> bytes:
    if _TEMPLATE_FILE.exists():
        return _TEMPLATE_FILE.read_bytes()
    raise FileNotFoundError(f"Template no encontrado: {_TEMPLATE_FILE}")


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
        if not nombre:
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
                pais_iso = str(row.get("pais_iso", "")).strip().upper()
                if not pais_iso:
                    raise ValueError("pais_iso es obligatorio cuando alcance=country")
                from app.models import Country
                country = s.query(Country).filter(Country.iso_code == pais_iso).first()
                if country is None:
                    raise ValueError(f"País con ISO '{pais_iso}' no encontrado en el catálogo")
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
