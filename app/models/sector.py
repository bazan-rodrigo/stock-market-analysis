from sqlalchemy import Column, Integer, String
from sqlalchemy.orm import relationship

from app.database import Base


class Sector(Base):
    __tablename__ = "sectors"

    id = Column(Integer, primary_key=True)
    name = Column(String(100), nullable=False, unique=True)

    industries = relationship("Industry", back_populates="sector")
    assets = relationship("Asset", back_populates="sector")
