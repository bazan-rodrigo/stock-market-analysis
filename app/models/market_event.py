from sqlalchemy import Column, Date, ForeignKey, Integer, String
from app.database import Base


class MarketEvent(Base):
    __tablename__ = "market_event"

    id         = Column(Integer, primary_key=True)
    name       = Column(String(200), nullable=False)
    start_date = Column(Date, nullable=False)
    end_date   = Column(Date, nullable=False)
    scope      = Column(String(10), nullable=False, default="global")  # global | country | asset
    country_id = Column(Integer, ForeignKey("countries.id"), nullable=True)
    asset_id   = Column(Integer, ForeignKey("asset.id"),     nullable=True)
    color      = Column(String(20), nullable=True, default="#ff9800")
