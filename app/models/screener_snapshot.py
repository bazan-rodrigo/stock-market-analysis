from datetime import datetime

from sqlalchemy import Column, DateTime, Float, ForeignKey, Integer
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

    asset = relationship("Asset", back_populates="screener_snapshot")
