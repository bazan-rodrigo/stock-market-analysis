from sqlalchemy import Column, Float, Integer
from app.database import Base


class RegimeConfig(Base):
    __tablename__ = "regime_config"

    id               = Column(Integer, primary_key=True, default=1)
    fast_period      = Column(Integer, nullable=False, default=50)
    slow_period      = Column(Integer, nullable=False, default=200)
    lateral_band_pct = Column(Float,   nullable=False, default=2.0)
