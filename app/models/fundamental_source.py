from sqlalchemy import Column, Integer, String, Text
from sqlalchemy.orm import relationship

from app.database import Base


class FundamentalSource(Base):
    __tablename__ = "fundamental_sources"

    id          = Column(Integer, primary_key=True)
    name        = Column(String(100), nullable=False, unique=True)
    description = Column(Text)

    assets = relationship("Asset", back_populates="fundamental_source",
                          foreign_keys="[Asset.fundamental_source_id]")
