from sqlalchemy import Column, ForeignKey, Integer, UniqueConstraint
from sqlalchemy.orm import relationship

from app.database import Base


class SyntheticAssetConfig(Base):
    __tablename__ = "synthetic_asset_config"
    __table_args__ = (UniqueConstraint("asset_id"),)

    id                   = Column(Integer, primary_key=True)
    asset_id             = Column(Integer, ForeignKey("assets.id", ondelete="CASCADE"),   nullable=False)
    numerator_asset_id   = Column(Integer, ForeignKey("assets.id", ondelete="RESTRICT"),  nullable=False)
    denominator_asset_id = Column(Integer, ForeignKey("assets.id", ondelete="RESTRICT"),  nullable=False)

    asset       = relationship("Asset", foreign_keys=[asset_id])
    numerator   = relationship("Asset", foreign_keys=[numerator_asset_id])
    denominator = relationship("Asset", foreign_keys=[denominator_asset_id])
