from sqlalchemy import Column, ForeignKey, Integer, String
from sqlalchemy.orm import relationship

from app.database import Base


class InstrumentType(Base):
    __tablename__ = "instrument_types"

    id = Column(Integer, primary_key=True)
    name = Column(String(100), nullable=False, unique=True)
    default_currency_id = Column(
        Integer, ForeignKey("currencies.id", ondelete="RESTRICT"), nullable=False
    )

    default_currency = relationship("Currency", back_populates="instrument_types")
    assets = relationship("Asset", back_populates="instrument_type")
