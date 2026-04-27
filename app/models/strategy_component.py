from sqlalchemy import Column, Float, ForeignKey, Integer, String
from sqlalchemy.orm import relationship
from app.database import Base


class StrategyComponent(Base):
    """
    Componente ponderado de una estrategia.

    scope:
      None          — señal de activo (source=asset), no aplica grupo
      own_group     — usa el grupo al que pertenece el activo (sector, market, etc.)
      specific_group — usa un grupo fijo definido por group_type + group_id
    """

    __tablename__ = "strategy_component"

    id          = Column(Integer,    primary_key=True)
    strategy_id = Column(Integer,    ForeignKey("strategy.id", ondelete="CASCADE"),
                         nullable=False, index=True)
    signal_id   = Column(Integer,    ForeignKey("signal.id",   ondelete="RESTRICT"),
                         nullable=False)
    weight      = Column(Float,      nullable=False, default=1.0)
    scope       = Column(String(20))   # None | own_group | specific_group
    group_type  = Column(String(30))   # solo si scope=specific_group
    group_id    = Column(Integer)      # solo si scope=specific_group

    strategy = relationship("Strategy",          back_populates="components")
    signal   = relationship("SignalDefinition")
