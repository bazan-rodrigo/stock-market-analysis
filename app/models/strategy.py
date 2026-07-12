from datetime import datetime

from sqlalchemy import Boolean, Column, DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.orm import relationship
from app.database import Base


class Strategy(Base):
    """Estrategia definida por el usuario: combina señales ponderadas.

    filter_conditions (JSON, nullable): árbol de condiciones de elegibilidad
    que se evalúa ANTES del scoring — el activo que no cumple no aparece en
    strategy_result. Ver strategy_filter.py para el esquema del árbol.

    owner_id / is_public (ver app/services/visibility.py): igual que en
    SignalDefinition — owner_id controla la edición (solo admin o dueño,
    NULL = solo admin), is_public solo la visibilidad.
    """

    __tablename__ = "strategy"

    id                = Column(Integer,     primary_key=True)
    name              = Column(String(100), nullable=False)
    description       = Column(Text)
    filter_conditions = Column(Text)   # JSON: árbol AND/OR (strategy_filter.py)
    owner_id     = Column(Integer, ForeignKey("users.id", ondelete="SET NULL"))
    is_public    = Column(Boolean,  nullable=False, default=False)
    created_at   = Column(DateTime, nullable=False, default=datetime.utcnow)
    updated_at   = Column(DateTime, nullable=False, default=datetime.utcnow)

    components = relationship("StrategyComponent", back_populates="strategy",
                              cascade="all, delete-orphan", lazy="joined")
