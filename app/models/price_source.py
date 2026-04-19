from sqlalchemy import Column, Integer, String, Text
from sqlalchemy.orm import relationship

from app.database import Base


class PriceSource(Base):
    __tablename__ = "price_sources"

    id = Column(Integer, primary_key=True)
    name = Column(String(100), nullable=False, unique=True)
    description = Column(Text)
    assets = relationship("Asset", back_populates="price_source")
