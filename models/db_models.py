# -*- coding: utf-8 -*-
"""
Modulo: db_models.py
Define las clases ORM de la base de datos usando SQLAlchemy.
Cada Asset tiene una unica fuente (PriceSource).
"""

from datetime import datetime
from sqlalchemy import (
    Column, BigInteger, String, DateTime, Boolean, DECIMAL,
    ForeignKey, Text, Enum, JSON, Date, Integer
)
from sqlalchemy.orm import declarative_base, relationship

Base = declarative_base()

# ==========================================================
# TABLA: USERS
# ==========================================================
class User(Base):
    __tablename__ = "users"

    id = Column(BigInteger, primary_key=True)
    username = Column(String(150), unique=True, nullable=False)
    email = Column(String(255))
    password_hash = Column(String(255), nullable=False)
    role = Column(Enum("admin", "analyst", name="user_roles"), nullable=False, default="analyst")
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, onupdate=datetime.utcnow)

    def __repr__(self):
        return f"<User(username={self.username}, role={self.role})>"


# ==========================================================
# TABLA: PRICE_SOURCES
# ==========================================================
class PriceSource(Base):
    __tablename__ = "price_sources"

    id = Column(BigInteger, primary_key=True)
    name = Column(String(100), unique=True, nullable=False)
    code = Column(String(50), unique=True, nullable=False)
    api_type = Column(String(50))
    base_url = Column(String(255))
    notes = Column(Text)
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    # Relaciones
    assets = relationship("Asset", back_populates="source")
    historical_prices = relationship("HistoricalPrice", back_populates="source")
    failed_updates = relationship("FailedUpdate", back_populates="source")

    def __repr__(self):
        return f"<PriceSource(name={self.name}, code={self.code})>"


# ==========================================================
# TABLA: ASSETS
# ==========================================================
class Asset(Base):
    __tablename__ = "assets"

    id = Column(BigInteger, primary_key=True)
    symbol = Column(String(128), unique=True, nullable=False)
    name = Column(String(255))
    sector = Column(String(128))
    industry = Column(String(128))
    country = Column(String(64))
    currency = Column(String(16))
    source_id = Column(BigInteger, ForeignKey("price_sources.id", ondelete="CASCADE"), nullable=False)
    source_symbol = Column(String(128), nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, onupdate=datetime.utcnow)

    # Relaciones
    source = relationship("PriceSource", back_populates="assets")
    historical_prices = relationship("HistoricalPrice", back_populates="asset", cascade="all, delete-orphan")
    failed_updates = relationship("FailedUpdate", back_populates="asset", cascade="all, delete-orphan")

    def __repr__(self):
        return f"<Asset(symbol={self.symbol}, source={self.source.code})>"


# ==========================================================
# TABLA: HISTORICAL_PRICES
# ==========================================================
class HistoricalPrice(Base):
    __tablename__ = "historical_prices"

    id = Column(BigInteger, primary_key=True)
    asset_id = Column(BigInteger, ForeignKey("assets.id", ondelete="CASCADE"), nullable=False)
    source_id = Column(BigInteger, ForeignKey("price_sources.id", ondelete="CASCADE"), nullable=False)
    date = Column(Date, nullable=False)
    open = Column(DECIMAL(18, 6))
    high = Column(DECIMAL(18, 6))
    low = Column(DECIMAL(18, 6))
    close = Column(DECIMAL(18, 6))
    adj_close = Column(DECIMAL(18, 6))
    volume = Column(BigInteger)
    recorded_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    # Relaciones
    asset = relationship("Asset", back_populates="historical_prices")
    source = relationship("PriceSource", back_populates="historical_prices")

    def __repr__(self):
        return f"<HistoricalPrice(asset={self.asset.symbol}, date={self.trade_date}, close={self.close})>"


# ==========================================================
# TABLA: FAILED_UPDATES
# ==========================================================
class FailedUpdate(Base):
    __tablename__ = "failed_updates"

    id = Column(BigInteger, primary_key=True)
    asset_id = Column(BigInteger, ForeignKey("assets.id", ondelete="SET NULL"))
    source_id = Column(BigInteger, ForeignKey("price_sources.id", ondelete="SET NULL"))
    run_timestamp = Column(DateTime, default=datetime.utcnow, nullable=False)
    run_type = Column(Enum("scheduled", "manual", name="run_type_enum"), nullable=False, default="scheduled")
    attempted_from = Column(Date)
    attempted_to = Column(Date)
    error_message = Column(Text)
    attempt_count = Column(Integer, default=1)
    resolved = Column(Boolean, default=False)
    resolved_at = Column(DateTime)

    # Relaciones
    asset = relationship("Asset", back_populates="failed_updates")
    source = relationship("PriceSource", back_populates="failed_updates")

    def __repr__(self):
        return f"<FailedUpdate(asset_id={self.asset_id}, source_id={self.source_id}, resolved={self.resolved})>"
