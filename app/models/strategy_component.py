from sqlalchemy import Column, Float, ForeignKey, Integer, String
from sqlalchemy.orm import relationship
from app.database import Base


class StrategyComponent(Base):
    """
    Componente ponderado de una estrategia: aporta el score de una señal
    (evaluada sobre el activo) al score final, con su peso.
    """

    __tablename__ = "strategy_component"

    id          = Column(Integer,    primary_key=True)
    strategy_id = Column(Integer,    ForeignKey("strategy.id", ondelete="CASCADE"),
                         nullable=False, index=True)
    signal_id   = Column(Integer,    ForeignKey("signal.id",   ondelete="RESTRICT"),
                         nullable=False, index=True)   # ix de la migración 0041
    weight      = Column(Float,      nullable=False, default=1.0)

    strategy = relationship("Strategy",          back_populates="components")
    signal   = relationship("SignalDefinition")
