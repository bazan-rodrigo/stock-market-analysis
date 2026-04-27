from sqlalchemy import Column, Date, Float, ForeignKey, Integer, String, UniqueConstraint
from app.database import Base


class IndicatorSnapshot(Base):
    """Serie temporal de indicadores técnicos por activo y fecha."""

    __tablename__ = "indicator_snapshot"
    __table_args__ = (UniqueConstraint("asset_id", "date"),)

    id       = Column(Integer, primary_key=True)
    asset_id = Column(Integer, ForeignKey("assets.id", ondelete="CASCADE"),
                      nullable=False, index=True)
    date     = Column(Date, nullable=False, index=True)

    # Régimen de tendencia por timeframe
    regime_d = Column(String(30))
    regime_w = Column(String(30))
    regime_m = Column(String(30))

    # Drawdown
    dd_current = Column(Float)
    dd_max1    = Column(Float)

    # Régimen de volatilidad por timeframe
    vol_d     = Column(String(20))
    vol_w     = Column(String(20))
    vol_m     = Column(String(20))
    atr_pct_d = Column(Float)
    atr_pct_w = Column(Float)
    atr_pct_m = Column(Float)

    # RSI por temporalidad
    rsi   = Column(Float)
    rsi_w = Column(Float)
    rsi_m = Column(Float)

    # Variaciones de precio
    var_daily   = Column(Float)
    var_month   = Column(Float)
    var_quarter = Column(Float)
    var_year    = Column(Float)
    var_52w     = Column(Float)

    # Fuerza relativa vs benchmark (var_52w activo - var_52w benchmark)
    rel_strength_52w = Column(Float)

    # Distancia en desv. estándar desde la MA más respetada
    dist_sma_d = Column(Float)
    dist_sma_w = Column(Float)
    dist_sma_m = Column(Float)

    # Distancia % desde SMAs fijas
    vs_sma20  = Column(Float)
    vs_sma50  = Column(Float)
    vs_sma200 = Column(Float)

    # Soporte / Resistencia
    pivot_resist_pct  = Column(Float)
    pivot_support_pct = Column(Float)

    # Precio de cierre
    last_close = Column(Float)
