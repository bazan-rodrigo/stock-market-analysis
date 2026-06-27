from sqlalchemy import (
    Column, Date, Float, ForeignKey, Integer, String, UniqueConstraint,
)
from sqlalchemy.orm import relationship

from app.database import Base


class IndicatorValue(Base):
    """Valor de un indicador para un activo en una fecha (EAV)."""

    __tablename__ = "indicator_values"
    __table_args__ = (
        UniqueConstraint("asset_id", "indicator_id", "date"),
    )

    id           = Column(Integer, primary_key=True)
    asset_id     = Column(Integer, ForeignKey("assets.id", ondelete="CASCADE"),
                          nullable=False, index=True)
    indicator_id = Column(Integer, ForeignKey("indicator_definitions.id", ondelete="CASCADE"),
                          nullable=False, index=True)
    date         = Column(Date, nullable=False, index=True)
    value_num    = Column(Float)
    value_str    = Column(String(50))

    definition = relationship("IndicatorDefinition", back_populates="values")
