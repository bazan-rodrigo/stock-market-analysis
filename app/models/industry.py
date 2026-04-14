from sqlalchemy import Column, ForeignKey, Integer, String
from sqlalchemy.orm import relationship

from app.database import Base


class Industry(Base):
    __tablename__ = "industries"

    id = Column(Integer, primary_key=True)
    name = Column(String(100), nullable=False, unique=True)
    sector_id = Column(
        Integer, ForeignKey("sectors.id", ondelete="RESTRICT"), nullable=False
    )

    sector = relationship("Sector", back_populates="industries")
    assets = relationship("Asset", back_populates="industry")
