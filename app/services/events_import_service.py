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
    "pais_iso",
    "color",
]

# alcance: global | country | asset
# pais_iso: código ISO del país (solo cuando alcance=country)
# color: código hex (opcional, default #ff9800)

_SEED_EVENTS = [
    # ── Global ────────────────────────────────────────────────────────────────
    ("Burbuja dot-com",                     "2000-03-10", "2002-10-09", "global", "",    "#ef5350"),
    ("Atentados 11-Sep",                    "2001-09-11", "2001-09-17", "global", "",    "#ef5350"),
    ("Crisis financiera global 2008",       "2008-09-15", "2009-06-30", "global", "",    "#ef5350"),
    ("Crisis deuda eurozona",               "2010-04-23", "2012-09-06", "global", "",    "#ff9800"),
    ("Flash Crash",                         "2010-05-06", "2010-05-06", "global", "",    "#ef5350"),
    ("Taper Tantrum Fed",                   "2013-05-22", "2013-12-18", "global", "",    "#ff9800"),
    ("Desplome petróleo",                   "2014-06-01", "2016-01-20", "global", "",    "#ff9800"),
    ("Crash mercados chinos",               "2015-06-12", "2016-02-11", "global", "",    "#ff9800"),
    ("Guerra comercial EEUU-China",         "2018-03-22", "2020-01-15", "global", "",    "#ff9800"),
    ("COVID-19 pandemia",                   "2020-03-11", "2021-12-31", "global", "",    "#ef5350"),
    ("Inflación global post-COVID",         "2021-01-01", "2023-06-30", "global", "",    "#ff9800"),
    ("Invasión Rusia-Ucrania",              "2022-02-24", "2022-12-31", "global", "",    "#ef5350"),
    ("Crisis bancaria SVB",                 "2023-03-10", "2023-05-01", "global", "",    "#ff9800"),
    # ── Estados Unidos ────────────────────────────────────────────────────────
    ("Crisis hipotecaria subprime",         "2007-07-01", "2008-09-14", "country", "USA", "#ff9800"),
    ("Cuantitative Easing QE1",             "2008-11-25", "2010-03-31", "country", "USA", "#2196f3"),
    ("Cuantitative Easing QE3",             "2012-09-13", "2014-10-29", "country", "USA", "#2196f3"),
    ("Elecciones USA 2016 — Trump",         "2016-11-08", "2016-11-09", "country", "USA", "#2196f3"),
    ("Shutdown gobierno USA",               "2018-12-22", "2019-01-25", "country", "USA", "#ff9800"),
    ("Elecciones USA 2020 — Biden",         "2020-11-03", "2020-11-07", "country", "USA", "#2196f3"),
    ("Asalto al Capitolio",                 "2021-01-06", "2021-01-06", "country", "USA", "#ef5350"),
    ("Ciclo de subas de tasas Fed 2022",    "2022-03-16", "2023-07-26", "country", "USA", "#ff9800"),
    ("Elecciones USA 2024 — Trump",         "2024-11-05", "2024-11-06", "country", "USA", "#2196f3"),
    ("Aranceles Trump 2025",                "2025-02-01", "2025-12-31", "country", "USA", "#ff9800"),
    # ── Argentina ────────────────────────────────────────────────────────────
    ("Crisis 2001 — Corralito",             "2001-12-01", "2002-06-30", "country", "ARG", "#ef5350"),
    ("Default 2001",                        "2001-12-23", "2005-02-28", "country", "ARG", "#ef5350"),
    ("Pesificación asimétrica",             "2002-01-06", "2002-12-31", "country", "ARG", "#ef5350"),
    ("Estatización AFJP",                   "2008-10-21", "2008-11-21", "country", "ARG", "#ff9800"),
    ("Cepo cambiario 2011",                 "2011-10-31", "2015-12-16", "country", "ARG", "#ff9800"),
    ("Default técnico 2014",                "2014-07-30", "2016-04-22", "country", "ARG", "#ef5350"),
    ("Fin cepo — Macri",                    "2015-12-17", "2015-12-17", "country", "ARG", "#4caf50"),
    ("Crisis cambiaria 2018",               "2018-04-25", "2018-09-30", "country", "ARG", "#ef5350"),
    ("Acuerdo FMI 2018",                    "2018-06-07", "2018-06-07", "country", "ARG", "#2196f3"),
    ("PASO 2019 — derrota Macri",           "2019-08-11", "2019-08-12", "country", "ARG", "#ef5350"),
    ("Reperfilamiento deuda 2019",          "2019-08-28", "2020-08-31", "country", "ARG", "#ef5350"),
    ("Cepo cambiario 2019",                 "2019-09-01", "2023-12-13", "country", "ARG", "#ff9800"),
    ("Elecciones presidenciales 2019",      "2019-10-27", "2019-10-27", "country", "ARG", "#2196f3"),
    ("Reestructuración deuda 2020",         "2020-08-04", "2020-08-31", "country", "ARG", "#4caf50"),
    ("Acuerdo FMI 2022",                    "2022-03-25", "2022-03-25", "country", "ARG", "#2196f3"),
    ("PASO 2023 — Milei sorpresa",          "2023-08-13", "2023-08-14", "country", "ARG", "#ff9800"),
    ("Elecciones presidenciales 2023",      "2023-11-19", "2023-11-19", "country", "ARG", "#2196f3"),
    ("Devaluación Milei — dic 2023",        "2023-12-13", "2023-12-13", "country", "ARG", "#ef5350"),
    ("Desregulación y DNU Milei",           "2023-12-20", "2024-06-30", "country", "ARG", "#ff9800"),
    ("Levantamiento cepo cambiario 2025",   "2025-04-11", "2025-04-11", "country", "ARG", "#4caf50"),
]


def generate_template() -> bytes:
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "Eventos"
    ws.append(TEMPLATE_COLUMNS)
    for row in _SEED_EVENTS:
        ws.append(list(row))
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
