from sqlalchemy import (
    BigInteger,
    Column,
    Date,
    Float,
    ForeignKey,
    Index,
    Integer,
)
from sqlalchemy.orm import relationship

from app.database import Base


class Price(Base):
    __tablename__ = "prices"

    # PK compuesta (asset_id, date): la identidad real de un precio. La columna
    # `id` sustituta se DROPEÓ (migración 0089) — era una PK autoincremental
    # heredada de InnoDB (donde la PK ES el índice clusterizado); en PostgreSQL
    # el heap es desordenado y ese índice medía idx_scan=0 y 97 MB que nadie
    # consultaba. Ninguna FK la referenciaba y no se leía en el código.
    asset_id = Column(
        Integer, ForeignKey("assets.id", ondelete="CASCADE"), primary_key=True
    )
    date = Column(Date, primary_key=True)
    open = Column(Float)
    high = Column(Float)
    low = Column(Float)
    close = Column(Float)
    volume = Column(BigInteger)

    asset = relationship("Asset", back_populates="prices")

    __table_args__ = (
        # Índice global por fecha (migración 0063): MAX(date), calendario
        # del backfill y last_close hacían full scan sin él. La unicidad
        # (asset_id, date) la garantiza ahora la PK (antes: uq_asset_date).
        Index("ix_prices_date", "date"),
    )
