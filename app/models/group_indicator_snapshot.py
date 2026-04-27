from sqlalchemy import Column, Date, Float, Integer, String, UniqueConstraint
from app.database import Base


class GroupIndicatorSnapshot(Base):
    """
    Serie temporal de indicadores agregados por grupo (sector, market, industry, etc.).
    Una fila por (group_type, group_id, date).
    """

    __tablename__ = "group_indicator_snapshot"
    __table_args__ = (UniqueConstraint("group_type", "group_id", "date"),)

    id         = Column(Integer, primary_key=True)
    group_type = Column(String(30), nullable=False, index=True)
    group_id   = Column(Integer,    nullable=False, index=True)
    date       = Column(Date,       nullable=False, index=True)

    # Scores de régimen promediados sobre los activos del grupo (-100..100)
    regime_score_d = Column(Float)
    regime_score_w = Column(Float)
    regime_score_m = Column(Float)

    # Cantidad de activos en el grupo con datos para esa fecha
    n_assets = Column(Integer)
