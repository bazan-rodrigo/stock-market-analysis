from sqlalchemy import Column, Integer, String, UniqueConstraint

from app.database import Base


class CatalogAlias(Base):
    __tablename__ = "catalog_aliases"

    id = Column(Integer, primary_key=True)
    entity_type = Column(String(50), nullable=False)
    source_value = Column(String(200), nullable=False)
    entity_id = Column(Integer, nullable=False)

    __table_args__ = (
        UniqueConstraint("entity_type", "source_value", name="uq_catalog_alias"),
    )
