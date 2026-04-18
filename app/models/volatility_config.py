from sqlalchemy import Column, Float, Integer
from app.database import Base


class VolatilityConfig(Base):
    __tablename__ = "volatility_config"

    id             = Column(Integer, primary_key=True, default=1)
    atr_period     = Column(Integer, nullable=False, default=14)
    pct_low        = Column(Float,   nullable=False, default=25.0)
    pct_high       = Column(Float,   nullable=False, default=75.0)
    pct_extreme    = Column(Float,   nullable=False, default=90.0)
    confirm_bars   = Column(Integer, nullable=False, default=3)
    dur_short_pct  = Column(Float,   nullable=False, default=33.0)
    dur_long_pct   = Column(Float,   nullable=False, default=67.0)
