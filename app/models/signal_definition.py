from datetime import datetime

from sqlalchemy import Boolean, Column, DateTime, Integer, String, Text
from app.database import Base


class SignalDefinition(Base):
    """
    Definición de una señal técnica creada por el usuario.

    formula_type:
      discrete_map — mapea un string indicator a score via dict (params.map)
      threshold    — aplica umbrales ordenados desc sobre valor numérico (params.thresholds)
      range        — normaliza valor numérico entre min/max a [-100,100] (params.min/max/clamp)
      composite    — promedio ponderado de otras señales (params.components)

    source:
      asset  — la señal lee de indicator_snapshot del activo
      group  — la señal lee de group_indicator_snapshot del grupo del activo
    """

    __tablename__ = "signal"

    id            = Column(Integer,     primary_key=True)
    key           = Column(String(50),  nullable=False, unique=True)
    name          = Column(String(100), nullable=False)
    description   = Column(Text)
    source        = Column(String(10),  nullable=False)  # asset | group
    group_type    = Column(String(30))                   # sector|market|industry|... (solo si source=group)
    indicator_key = Column(String(50))                   # campo en indicator/group_indicator_snapshot
    formula_type  = Column(String(20),  nullable=False)  # discrete_map|threshold|range|composite
    params        = Column(Text,        nullable=False)  # JSON
    is_system     = Column(Boolean,     nullable=False, default=False)
    created_at    = Column(DateTime,    nullable=False, default=datetime.utcnow)
