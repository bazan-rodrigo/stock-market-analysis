from sqlalchemy import Column, Date, Float, ForeignKey, Integer, String, UniqueConstraint
from sqlalchemy.orm import relationship

from app.database import Base


class SyntheticFormula(Base):
    __tablename__ = "synthetic_formula"
    __table_args__ = (UniqueConstraint("asset_id"),)

    id           = Column(Integer, primary_key=True)
    asset_id     = Column(Integer, ForeignKey("assets.id", ondelete="CASCADE"), nullable=False)
    formula_type = Column(String(20), nullable=False)   # ratio | weighted_avg | weighted_sum | index
    base_value   = Column(Float,  nullable=True)        # solo para 'index'
    base_date    = Column(Date,   nullable=True)        # solo para 'index'

    asset      = relationship("Asset", foreign_keys=[asset_id])
    components = relationship("SyntheticComponent", back_populates="formula",
                              cascade="all, delete-orphan", order_by="SyntheticComponent.id")


class SyntheticComponent(Base):
    __tablename__ = "synthetic_component"

    id         = Column(Integer, primary_key=True)
    formula_id = Column(Integer, ForeignKey("synthetic_formula.id", ondelete="CASCADE"), nullable=False)
    asset_id   = Column(Integer, ForeignKey("assets.id", ondelete="RESTRICT"),          nullable=False)
    role       = Column(String(20), nullable=False)     # numerator | denominator | component
    weight     = Column(Float, nullable=False, default=1.0)

    formula = relationship("SyntheticFormula", back_populates="components")
    asset   = relationship("Asset", foreign_keys=[asset_id])
