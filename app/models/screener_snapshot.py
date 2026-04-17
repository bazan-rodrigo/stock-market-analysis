from datetime import datetime

from sqlalchemy import Column, DateTime, Float, ForeignKey, Integer, Text
from sqlalchemy.orm import relationship

from app.database import Base


class ScreenerSnapshot(Base):
    """Métricas pre-calculadas para el screener. Se actualiza tras cada descarga de precios."""

    __tablename__ = "screener_snapshot"

    id = Column(Integer, primary_key=True)
    asset_id = Column(
        Integer,
        ForeignKey("assets.id", ondelete="CASCADE"),
        nullable=False,
        unique=True,
    )
    updated_at = Column(DateTime, nullable=False, default=datetime.utcnow)

    last_close = Column(Float)

    # Variaciones porcentuales
    var_daily = Column(Float)
    var_month = Column(Float)
    var_quarter = Column(Float)
    var_year = Column(Float)
    var_52w = Column(Float)

    # Indicadores (último valor)
    rsi = Column(Float)
    sma20 = Column(Float)
    sma50 = Column(Float)
    sma200 = Column(Float)

    # Distancia porcentual del precio al SMA
    vs_sma20 = Column(Float)
    vs_sma50 = Column(Float)
    vs_sma200 = Column(Float)

    # Drawdown desde el máximo histórico (%)
    dd_current = Column(Float)
    dd_max1 = Column(Float)
    dd_max2 = Column(Float)
    dd_max3 = Column(Float)

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

    asset = relationship("Asset", back_populates="screener_snapshot")
