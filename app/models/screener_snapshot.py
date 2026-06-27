from datetime import datetime

from sqlalchemy import Column, DateTime, Float, ForeignKey, Integer, Text
from sqlalchemy.orm import relationship

from app.database import Base


class ScreenerSnapshot(Base):
    """Caché de cálculos pesados para gráficos. Se actualiza tras cada descarga de precios."""

    __tablename__ = "screener_snapshot"

    id = Column(Integer, primary_key=True)
    asset_id = Column(
        Integer,
        ForeignKey("assets.id", ondelete="CASCADE"),
        nullable=False,
        unique=True,
    )
    updated_at = Column(DateTime, nullable=False, default=datetime.utcnow)

    # SMAs absolutas (usadas en renders de gráfico)
    sma20  = Column(Float)
    sma50  = Column(Float)
    sma200 = Column(Float)

    # MA más respetada por timeframe (período óptimo)
    best_sma_d = Column(Integer)
    best_ema_d = Column(Integer)
    best_sma_w = Column(Integer)
    best_ema_w = Column(Integer)
    best_sma_m = Column(Integer)
    best_ema_m = Column(Integer)

    # Zonas de régimen por timeframe (JSON: [{start, end, regime}, ...])
    regime_zones_d = Column(Text)
    regime_zones_w = Column(Text)
    regime_zones_m = Column(Text)

    # Eventos de drawdown significativos (JSON: [{start, trough, end, depth}, ...])
    dd_events = Column(Text)

    # Zonas de régimen de volatilidad ATR por timeframe (JSON)
    vol_zones_d = Column(Text)
    vol_zones_w = Column(Text)
    vol_zones_m = Column(Text)

    asset = relationship("Asset", back_populates="screener_snapshot")
