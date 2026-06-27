from sqlalchemy import Column, Integer, String, Text
from sqlalchemy.orm import relationship

from app.database import Base


class IndicatorDefinition(Base):
    """Catálogo de indicadores técnicos del sistema."""

    __tablename__ = "indicator_definitions"

    id          = Column(Integer, primary_key=True)
    code        = Column(String(50),  nullable=False, unique=True, index=True)
    name        = Column(String(100), nullable=False)
    category    = Column(String(50),  nullable=False)
    scale       = Column(String(50))
    type        = Column(String(3),   nullable=False)  # 'num' | 'str'
    description = Column(Text)

    values = relationship("IndicatorValue", back_populates="definition",
                          cascade="all, delete-orphan")
