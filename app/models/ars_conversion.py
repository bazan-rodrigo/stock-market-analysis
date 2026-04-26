from sqlalchemy import Column, ForeignKey, Integer, UniqueConstraint
from sqlalchemy.orm import relationship

from app.database import Base


class ARSConversionDivisor(Base):
    __tablename__ = "ars_conversion_divisor"
    __table_args__ = (UniqueConstraint("divisor_asset_id"),)

    id               = Column(Integer, primary_key=True)
    divisor_asset_id = Column(Integer, ForeignKey("assets.id", ondelete="CASCADE"), nullable=False)

    divisor_asset = relationship("Asset", foreign_keys=[divisor_asset_id])
