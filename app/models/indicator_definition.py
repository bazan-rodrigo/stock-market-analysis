from sqlalchemy import (Boolean, Column, Float, Index, Integer, String, Text,
                        UniqueConstraint)

from app.database import Base


class IndicatorDefinition(Base):
    """Catálogo de indicadores técnicos del sistema."""

    __tablename__ = "indicator_definitions"
    # Estructura que dejó la cadena de migraciones: UNIQUE con nombre 'code'
    # (así lo nombró MySQL) + índice no-unique aparte. Con unique=True +
    # index=True en la columna, create_all generaría UN índice unique con
    # otro nombre y el autogenerate-diff contra la base migrada no da vacío.
    __table_args__ = (
        UniqueConstraint("code", name="code"),
        Index("ix_indicator_definitions_code", "code"),
    )

    id           = Column(Integer, primary_key=True)
    code         = Column(String(50),  nullable=False)
    name         = Column(String(100), nullable=False)
    category     = Column(String(50),  nullable=False)
    scale        = Column(String(50))
    type         = Column(String(3),   nullable=False)  # 'num' | 'str' — usado para formateo en UI
    description  = Column(Text)
    keep_history = Column(Boolean, nullable=False, default=True)
    full_sample  = Column(Boolean, nullable=False, default=False)  # requiere force en backfill histórico
    # Duración medida de la última corrida: ordena la cola LPT de la próxima
    # (los indicadores nuevos, sin medición, van primero). Dos campos porque
    # un delta (reescribe 1 fila/activo) y un rebuild completo (reescribe
    # toda la historia) tienen costos muy distintos para el mismo código —
    # ver migración 0056.
    last_backfill_seconds = Column(Float)  # delta (force=False)
    last_rebuild_seconds  = Column(Float)  # rebuild completo (force=True)
