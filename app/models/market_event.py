from sqlalchemy import Column, Date, Index, Integer, String
from app.database import Base


class MarketEvent(Base):
    __tablename__ = "market_event"
    # Índices de la migración 0028 — declarados para que create_all
    # produzca el mismo esquema que la cadena
    __table_args__ = (
        Index("ix_market_event_asset_id", "asset_id"),
        Index("ix_market_event_scope", "scope"),
    )

    id         = Column(Integer, primary_key=True)
    name       = Column(String(200), nullable=False)
    start_date = Column(Date, nullable=False)
    end_date   = Column(Date, nullable=False)
    scope      = Column(String(10), nullable=False, default="global")  # global | country | asset
    country_id = Column(Integer, nullable=True)
    asset_id   = Column(Integer, nullable=True)
    color      = Column(String(20), nullable=True, default="#ff9800")
