from sqlalchemy import Column, Date, Float, ForeignKey, Integer, UniqueConstraint
from sqlalchemy.orm import relationship

from app.database import Base


class FundamentalQuarterly(Base):
    __tablename__ = "fundamental_quarterly"
    __table_args__ = (UniqueConstraint("asset_id", "period_date", name="uq_fund_asset_period"),)

    id               = Column(Integer, primary_key=True)
    asset_id         = Column(Integer, ForeignKey("assets.id", ondelete="CASCADE"), nullable=False)
    period_date      = Column(Date, nullable=False)

    # Income Statement
    revenue          = Column(Float)
    gross_profit     = Column(Float)
    operating_income = Column(Float)
    net_income       = Column(Float)
    ebitda           = Column(Float)

    # Balance Sheet
    total_debt       = Column(Float)
    equity           = Column(Float)
    shares           = Column(Float)

    # Cash Flow
    fcf              = Column(Float)
    operating_cf     = Column(Float)

    # EPS
    eps_actual       = Column(Float)
    eps_estimated    = Column(Float)

    asset = relationship("Asset", back_populates="fundamental_quarterly")
