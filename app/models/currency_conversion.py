from sqlalchemy import Column, ForeignKey, Integer, UniqueConstraint
from sqlalchemy.orm import relationship

from app.database import Base


class CurrencyConversionDivisor(Base):
    __tablename__ = "currency_conversion_divisor"
    __table_args__ = (UniqueConstraint("currency_id", "divisor_asset_id"),)

    id               = Column(Integer, primary_key=True)
    currency_id      = Column(Integer, ForeignKey("currencies.id",  ondelete="CASCADE"), nullable=False)
    divisor_asset_id = Column(Integer, ForeignKey("assets.id",      ondelete="CASCADE"), nullable=False)

    currency      = relationship("Currency", foreign_keys=[currency_id])
    divisor_asset = relationship("Asset",    foreign_keys=[divisor_asset_id])
