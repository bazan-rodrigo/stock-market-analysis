from sqlalchemy import Column, Date, Float, Index, Integer, String, UniqueConstraint
from app.database import Base


class GroupScore(Base):
    """
    Serie temporal de indicadores agregados por grupo (sector, market, industry, etc.).
    Una fila por (group_type, group_id, date).
    """

    __tablename__ = "group_scores"
    # Índices con los nombres/composición que dejó la cadena de migraciones:
    # la 0033 los creó cuando la tabla se llamaba group_indicator_snapshot y
    # la 0050 renombró solo la tabla (MySQL conserva los nombres de índice).
    # Declarados idénticos para que una base nacida por create_all produzca
    # el mismo esquema (verificado con alembic autogenerate: diff vacío).
    __table_args__ = (
        UniqueConstraint("group_type", "group_id", "date"),
        Index("ix_group_indicator_snapshot_group", "group_type", "group_id"),
        Index("ix_group_indicator_snapshot_date", "date"),
    )

    id         = Column(Integer, primary_key=True)
    group_type = Column(String(30), nullable=False)
    group_id   = Column(Integer,    nullable=False)
    date       = Column(Date,       nullable=False)

    # Scores de régimen promediados sobre los activos del grupo (-100..100)
    regime_score_d = Column(Float)
    regime_score_w = Column(Float)
    regime_score_m = Column(Float)

    # Cantidad de activos en el grupo con datos para esa fecha
    n_assets = Column(Integer)
