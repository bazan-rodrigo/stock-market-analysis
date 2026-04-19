from sqlalchemy import Boolean, Column, ForeignKey, Integer, String
from sqlalchemy.orm import relationship

from app.database import Base


class Asset(Base):
    __tablename__ = "assets"

    id = Column(Integer, primary_key=True)
    ticker = Column(String(20), nullable=False, unique=True)
    name = Column(String(200), nullable=True)
    country_id = Column(
        Integer, ForeignKey("countries.id", ondelete="RESTRICT"), nullable=True
    )
    market_id = Column(
        Integer, ForeignKey("markets.id", ondelete="RESTRICT"), nullable=True
    )
    instrument_type_id = Column(
        Integer, ForeignKey("instrument_types.id", ondelete="RESTRICT"), nullable=True
    )
    currency_id = Column(
        Integer, ForeignKey("currencies.id", ondelete="RESTRICT"), nullable=True
    )
    sector_id = Column(
        Integer, ForeignKey("sectors.id", ondelete="RESTRICT"), nullable=True
    )
    industry_id = Column(
        Integer, ForeignKey("industries.id", ondelete="RESTRICT"), nullable=True
    )
    price_source_id = Column(
        Integer, ForeignKey("price_sources.id", ondelete="RESTRICT"), nullable=False
    )
    active = Column(Boolean, nullable=False, default=True)
    benchmark_id = Column(
        Integer, ForeignKey("assets.id", ondelete="SET NULL"), nullable=True
    )

    country = relationship("Country", back_populates="assets")
    market  = relationship("Market", back_populates="assets", foreign_keys="[Asset.market_id]")
    instrument_type = relationship("InstrumentType", back_populates="assets")
    currency = relationship("Currency", back_populates="assets")
    sector = relationship("Sector", back_populates="assets")
    industry = relationship("Industry", back_populates="assets")
    price_source = relationship("PriceSource", back_populates="assets")

    prices = relationship(
        "Price", back_populates="asset", cascade="all, delete-orphan"
    )
    update_log = relationship(
        "PriceUpdateLog",
        back_populates="asset",
        uselist=False,
        cascade="all, delete-orphan",
    )
    screener_snapshot = relationship(
        "ScreenerSnapshot",
        back_populates="asset",
        uselist=False,
        cascade="all, delete-orphan",
    )
