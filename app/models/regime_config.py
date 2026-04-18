from sqlalchemy import Column, Float, Integer
from app.database import Base


class RegimeConfig(Base):
    __tablename__ = "regime_config"

    id                 = Column(Integer, primary_key=True, default=1)
    ema_period_d       = Column(Integer, nullable=False, default=200)
    ema_period_w       = Column(Integer, nullable=False, default=50)
    ema_period_m       = Column(Integer, nullable=False, default=20)
    slope_lookback     = Column(Integer, nullable=False, default=20)
    slope_threshold_pct= Column(Float,   nullable=False, default=0.5)
    confirm_bars       = Column(Integer, nullable=False, default=3)
