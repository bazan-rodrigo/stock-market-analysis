from datetime import datetime

from sqlalchemy import Boolean, Column, DateTime, ForeignKey, Integer, String, Text
from app.database import Base


class SignalDefinition(Base):
    """
    Definición de una señal técnica creada por el usuario.

    owner_id / is_public (ver app/services/visibility.py):
      owner_id   — quién la creó; controla la EDICIÓN (solo admin o dueño).
                   NULL = sin dueño (editable solo por admin).
      is_public  — solo VISIBILIDAD: pública la ven todos, privada solo su
                   dueño y el admin. El pipeline de cálculo ignora ambas.

    formula_type:
      discrete_map — mapea un string indicator a score via dict (params.map)
      threshold    — aplica umbrales ordenados desc sobre valor numérico (params.thresholds)
      range        — normaliza valor numérico entre min/max a [-100,100] (params.min/max/clamp)

    source:
      asset  — la señal lee de indicator_values del activo
      group  — la señal lee de group_scores del grupo del activo
    """

    __tablename__ = "signal"

    id            = Column(Integer,     primary_key=True)
    key           = Column(String(50),  nullable=False, unique=True)
    name          = Column(String(100), nullable=False)
    description   = Column(Text)
    source        = Column(String(10),  nullable=False)  # asset | group
    group_type    = Column(String(30))                   # sector|market|industry|... (solo si source=group)
    indicator_key = Column(String(50))                   # campo en indicator/group_scores
    formula_type  = Column(String(20),  nullable=False)  # discrete_map|threshold|range
    params        = Column(Text,        nullable=False)  # JSON
    owner_id      = Column(Integer, ForeignKey("users.id", ondelete="SET NULL"))
    is_public     = Column(Boolean,     nullable=False, default=False)
    created_at    = Column(DateTime,    nullable=False, default=datetime.utcnow)
