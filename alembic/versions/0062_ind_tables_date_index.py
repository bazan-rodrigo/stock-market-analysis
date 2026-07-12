"""Indice por date en todas las tablas ind_*.

La PK es (asset_id, date): cualquier consulta que filtra SOLO por fecha
(scores de grupo por dia, carga de indicadores del pipeline de senales,
lookup as-of del filtro de estrategias) no puede usarla y hace full scan
de ~1M filas por query. En el backfill de senales eso son ~18 full scans
POR FECHA — la lentitud que se percibia con "Recalcular completo".

Idempotente: solo crea el indice donde falta (tablas ind_* nuevas que se
agreguen despues deben incluirlo en su propia migracion).

Revision ID: 0062
Revises: 0061
"""
import sqlalchemy as sa
from alembic import op

revision = "0062"
down_revision = "0061"
branch_labels = None
depends_on = None


def _ind_tables(bind) -> list[str]:
    # Solo tablas ind_* que tengan columna date: excluye ind_asset_meta
    # (cache de metadatos, matchea el prefijo pero no es tabla de valores)
    return [r[0] for r in bind.execute(sa.text(
        "SELECT table_name FROM information_schema.columns "
        "WHERE table_schema = DATABASE() AND table_name LIKE 'ind\\_%' "
        "  AND column_name = 'date'"
    )).fetchall()]


def _has_date_index(bind, table: str) -> bool:
    n = bind.execute(sa.text(
        "SELECT COUNT(*) FROM information_schema.statistics "
        "WHERE table_schema = DATABASE() AND table_name = :t "
        "  AND column_name = 'date' AND seq_in_index = 1"
    ), {"t": table}).scalar()
    return bool(n)


def upgrade() -> None:
    bind = op.get_bind()
    for table in _ind_tables(bind):
        if not _has_date_index(bind, table):
            op.create_index(f"ix_{table}_date", table, ["date"])


def downgrade() -> None:
    bind = op.get_bind()
    for table in _ind_tables(bind):
        exists = bind.execute(sa.text(
            "SELECT COUNT(*) FROM information_schema.statistics "
            "WHERE table_schema = DATABASE() AND table_name = :t "
            "  AND index_name = :i"
        ), {"t": table, "i": f"ix_{table}_date"}).scalar()
        if exists:
            op.drop_index(f"ix_{table}_date", table_name=table)
