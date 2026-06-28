from sqlalchemy import Boolean, Column, Integer, String, Text

from app.database import Base


class IndicatorDefinition(Base):
    """Catálogo de indicadores técnicos del sistema."""

    __tablename__ = "indicator_definitions"

    id           = Column(Integer, primary_key=True)
    code         = Column(String(50),  nullable=False, unique=True, index=True)
    name         = Column(String(100), nullable=False)
    category     = Column(String(50),  nullable=False)
    scale        = Column(String(50))
    type         = Column(String(3),   nullable=False)  # 'num' | 'str' — usado para formateo en UI
    description  = Column(Text)
    keep_history = Column(Boolean,     nullable=False, default=True)
