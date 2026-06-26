from datetime import datetime

from sqlalchemy import Column, DateTime, Float, ForeignKey, Integer, UniqueConstraint
from sqlalchemy.orm import relationship

from app.database import Base


class FundamentalSnapshot(Base):
    __tablename__ = "fundamental_snapshot"
    __table_args__ = (UniqueConstraint("asset_id"),)

    id                  = Column(Integer, primary_key=True)
    asset_id            = Column(Integer, ForeignKey("assets.id", ondelete="CASCADE"), nullable=False)
    updated_at          = Column(DateTime, nullable=False, default=datetime.utcnow)

    # Valuación
    pe_ttm              = Column(Float)   # Price / TTM EPS
    pb                  = Column(Float)   # Price / Book Value per Share
    ps_ttm              = Column(Float)   # Price / TTM Revenue per Share
    ev_ebitda           = Column(Float)   # EV / TTM EBITDA (si disponible)

    # Márgenes (último trimestre disponible)
    net_margin          = Column(Float)
    gross_margin        = Column(Float)
    operating_margin    = Column(Float)

    # Apalancamiento
    debt_to_equity      = Column(Float)

    # Crecimiento YoY (Q vs Q-4)
    revenue_growth_yoy  = Column(Float)
    eps_growth_yoy      = Column(Float)
    pe_growth_yoy       = Column(Float)   # P/E TTM actual vs P/E TTM hace 1 año

    asset = relationship("Asset", back_populates="fundamental_snapshot")
