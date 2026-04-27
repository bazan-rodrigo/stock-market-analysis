from datetime import datetime

from sqlalchemy import Column, DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.orm import relationship
from app.database import Base


class Strategy(Base):
    """Estrategia definida por el usuario: combina señales ponderadas."""

    __tablename__ = "strategy"

    id           = Column(Integer,     primary_key=True)
    name         = Column(String(100), nullable=False)
    description  = Column(Text)
    asset_filter = Column(Text)   # JSON: {"sector_id": 3, "market_id": 1, ...}
    created_by   = Column(Integer, ForeignKey("users.id", ondelete="SET NULL"))
    created_at   = Column(DateTime, nullable=False, default=datetime.utcnow)
    updated_at   = Column(DateTime, nullable=False, default=datetime.utcnow)

    components = relationship("StrategyComponent", back_populates="strategy",
                              cascade="all, delete-orphan", lazy="joined")
