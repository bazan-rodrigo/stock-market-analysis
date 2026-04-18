from sqlalchemy import Column, Float, Integer
from app.database import Base


class DrawdownConfig(Base):
    __tablename__ = "drawdown_config"

    id            = Column(Integer, primary_key=True, default=1)
    min_depth_pct = Column(Float, nullable=False, default=20.0)
