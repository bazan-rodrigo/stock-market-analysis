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

    La señal siempre lee del indicador del activo (indicator_key). Las señales
    de grupo (source=group, sobre group_scores) se removieron.
    """

    __tablename__ = "signal"

    id            = Column(Integer,     primary_key=True)
    key           = Column(String(50),  nullable=False, unique=True)
    name          = Column(String(100), nullable=False)
    description   = Column(Text)
    indicator_key = Column(String(50))                   # código del indicador ind_*
    formula_type  = Column(String(20),  nullable=False)  # discrete_map|threshold|range
    params        = Column(Text,        nullable=False)  # JSON
    owner_id      = Column(Integer, ForeignKey("users.id", ondelete="SET NULL"))
    is_public     = Column(Boolean,     nullable=False, default=False)
    created_at    = Column(DateTime,    nullable=False, default=datetime.utcnow)
