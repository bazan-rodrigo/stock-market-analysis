"""maintenance_service: descubrimiento de tablas propensas a bloat (lógica pura;
el VACUUM/OPTIMIZE en sí es DB-specific y se valida en el entorno real)."""
import app.models  # noqa: F401 — registra todos los modelos en Base.metadata
from app.database import Base, engine
from app.services import maintenance_service


def test_bloat_tables_incluye_churn_existentes():
    Base.metadata.create_all(engine)
    tables = maintenance_service.bloat_tables()
    # tablas fijas de churn que create_all materializa
    assert "prices" in tables
    assert "group_scores" in tables
    assert "current_indicator_values" in tables
    assert all(isinstance(t, str) for t in tables)
