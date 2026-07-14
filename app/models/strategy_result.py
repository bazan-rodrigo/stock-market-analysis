from sqlalchemy import Column, Date, Float, ForeignKey, Integer, UniqueConstraint
from app.database import Base


class StrategyResult(Base):
    """Score final de una estrategia para un activo en una fecha (el orden por
    score desc ya es el ranking; no se persiste una columna rank aparte)."""

    __tablename__ = "strategy_result"
    __table_args__ = (UniqueConstraint("strategy_id", "asset_id", "date"),)

    id          = Column(Integer, primary_key=True)
    strategy_id = Column(Integer, ForeignKey("strategy.id", ondelete="CASCADE"),
                         nullable=False, index=True)
    asset_id    = Column(Integer, ForeignKey("assets.id",   ondelete="CASCADE"),
                         nullable=False, index=True)
    date        = Column(Date,    nullable=False, index=True)
    score       = Column(Float)
