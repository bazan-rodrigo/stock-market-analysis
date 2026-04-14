from sqlalchemy import Column, Integer, String
from sqlalchemy.orm import relationship

from app.database import Base


class Currency(Base):
    __tablename__ = "currencies"

    id = Column(Integer, primary_key=True)
    name = Column(String(100), nullable=False, unique=True)
    iso_code = Column(String(10), nullable=False, unique=True)

    instrument_types = relationship("InstrumentType", back_populates="default_currency")
    assets = relationship("Asset", back_populates="currency")
