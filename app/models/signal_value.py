from sqlalchemy import Column, Date, Float, ForeignKey, Integer, UniqueConstraint
from app.database import Base


class SignalValue(Base):
    """Score calculado de una señal para un activo en una fecha."""

    __tablename__ = "signal_value"
    __table_args__ = (UniqueConstraint("signal_id", "asset_id", "date"),)

    id        = Column(Integer, primary_key=True)
    signal_id = Column(Integer, ForeignKey("signal.id",  ondelete="CASCADE"),
                       nullable=False, index=True)
    asset_id  = Column(Integer, ForeignKey("assets.id",  ondelete="CASCADE"),
                       nullable=False, index=True)
    date      = Column(Date,    nullable=False, index=True)
    score     = Column(Float,   nullable=False)
