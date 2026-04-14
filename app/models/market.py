from sqlalchemy import Column, ForeignKey, Integer, String
from sqlalchemy.orm import relationship

from app.database import Base


class Market(Base):
    __tablename__ = "markets"

    id = Column(Integer, primary_key=True)
    name = Column(String(100), nullable=False, unique=True)
    country_id = Column(
        Integer, ForeignKey("countries.id", ondelete="RESTRICT"), nullable=True
    )

    country = relationship("Country", back_populates="markets")
    assets = relationship("Asset", back_populates="market")
