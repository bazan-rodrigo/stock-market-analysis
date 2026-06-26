import logging

logger = logging.getLogger(__name__)

_BUILTIN_SOURCES = [
    {"name": "Yahoo Finance", "description": "Fuente de precios de Yahoo Finance (yfinance)."},
    {"name": "Ambito",        "description": "Riesgo País Argentina (EMBI JP Morgan) vía Ámbito Financiero. Ticker: RIESGO_PAIS_AR."},
    {"name": "Calculado",     "description": "Fuente interna para activos sintéticos calculados."},
]


def ensure_builtin_data() -> None:
    from app.database import get_session
    from app.models import PriceSource
    s = get_session()
    for src in _BUILTIN_SOURCES:
        exists = s.query(PriceSource).filter(PriceSource.name == src["name"]).first()
        if not exists:
            s.add(PriceSource(name=src["name"], description=src["description"]))
            logger.info("Creada fuente de precio integrada: %s", src["name"])
    s.commit()
