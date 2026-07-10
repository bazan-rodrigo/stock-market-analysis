from sqlalchemy import Column, DateTime, Float, Integer, String

from app.database import Base


class VerificationRunLog(Base):
    """Fila única (id=1): última corrida de update_flags_for_assets
    (botón manual "Todos los activos"/"Solo los ya marcados" en
    /admin/verify, o el job semanal de scheduler_service). Se sobreescribe
    entera en cada corrida — no es historial, es "cuándo fue la última
    vez y cuánto tardó"."""
    __tablename__ = "verification_run_log"

    id             = Column(Integer, primary_key=True, default=1)
    mode           = Column(String(20), nullable=False)  # "all" | "marked"
    started_at     = Column(DateTime, nullable=False)
    seconds        = Column(Float, nullable=False)
    checked_assets = Column(Integer, nullable=False)
    flagged_assets = Column(Integer, nullable=False)
    cleared_assets = Column(Integer, nullable=False)
