from datetime import datetime

from sqlalchemy import Column, DateTime, ForeignKey, Integer, Text
from sqlalchemy.orm import relationship

from app.database import Base


class AssetVerificationFlag(Base):
    """Hallazgos de la corrida completa de verificación (ver
    verification_service.run_full_verification_and_store) para un activo.
    Solo existe fila para activos CON algún hallazgo — se trunca y
    repuebla entera en cada corrida, no hay upsert incremental."""
    __tablename__ = "asset_verification_flag"

    asset_id = Column(
        Integer,
        ForeignKey("assets.id", ondelete="CASCADE"),
        primary_key=True,
    )
    n_calc_diffs   = Column(Integer, nullable=False, default=0)
    n_sanity_diffs = Column(Integer, nullable=False, default=0)
    detail         = Column(Text, nullable=True)
    checked_at     = Column(DateTime, nullable=False, default=datetime.utcnow)

    asset = relationship("Asset", back_populates="verification_flag")
