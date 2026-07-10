from sqlalchemy import Boolean, Column, Integer, String
from app.database import Base


class SchedulerConfig(Base):
    __tablename__ = "scheduler_config"

    id      = Column(Integer, primary_key=True, default=1)
    enabled = Column(Boolean, nullable=False, default=False)
    hour    = Column(Integer, nullable=False, default=18)
    minute  = Column(Integer, nullable=False, default=0)

    # Verificación semanal de datos (asset_verification_flag): horario
    # propio, independiente del de la actualización diaria de precios —
    # nace deshabilitada (a diferencia de la diaria).
    weekly_verify_enabled = Column(Boolean, nullable=False, default=False)
    weekly_verify_day     = Column(String(3), nullable=False, default="sun")
    weekly_verify_hour    = Column(Integer, nullable=False, default=3)
    weekly_verify_minute  = Column(Integer, nullable=False, default=0)
