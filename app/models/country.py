from sqlalchemy import Column, Integer, String
from sqlalchemy.orm import relationship

from app.database import Base


class Country(Base):
    __tablename__ = "countries"

    id = Column(Integer, primary_key=True)
    name = Column(String(100), nullable=False, unique=True)
    iso_code = Column(String(3), nullable=False, unique=True)

    markets = relationship("Market", back_populates="country")
    assets = relationship("Asset", back_populates="country")
