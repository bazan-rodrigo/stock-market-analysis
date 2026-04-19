from sqlalchemy import Column, Float, Integer
from app.database import Base


class SRConfig(Base):
    __tablename__ = "sr_config"

    id           = Column(Integer, primary_key=True, default=1)
    lookback_days = Column(Integer, nullable=False, default=252)
    pivot_window  = Column(Integer, nullable=False, default=5)
    cluster_pct   = Column(Float,   nullable=False, default=0.5)
    min_touches   = Column(Integer, nullable=False, default=2)
