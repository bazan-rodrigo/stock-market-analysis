from datetime import datetime

from sqlalchemy import Boolean, Column, DateTime, ForeignKey, Integer, Text, UniqueConstraint
from sqlalchemy.orm import relationship

from app.database import Base


class FundamentalUpdateLog(Base):
    __tablename__ = "fundamental_update_log"
    __table_args__ = (UniqueConstraint("asset_id"),)

    id              = Column(Integer, primary_key=True)
    asset_id        = Column(Integer, ForeignKey("assets.id", ondelete="CASCADE"), nullable=False)
    last_attempt_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    success         = Column(Boolean, nullable=False)
    error_detail    = Column(Text)

    asset = relationship("Asset", back_populates="fundamental_update_log")
