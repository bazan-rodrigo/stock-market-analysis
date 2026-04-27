from sqlalchemy import Column, Date, Float, ForeignKey, Integer, String, UniqueConstraint
from app.database import Base


class GroupSignalValue(Base):
    """Score calculado de una señal para un grupo en una fecha."""

    __tablename__ = "group_signal_value"
    __table_args__ = (UniqueConstraint("signal_id", "group_type", "group_id", "date"),)

    id         = Column(Integer,    primary_key=True)
    signal_id  = Column(Integer,    ForeignKey("signal.id", ondelete="CASCADE"),
                        nullable=False, index=True)
    group_type = Column(String(30), nullable=False)
    group_id   = Column(Integer,    nullable=False)
    date       = Column(Date,       nullable=False, index=True)
    score      = Column(Float,      nullable=False)
