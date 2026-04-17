"""Crea tabla catalog_aliases para mapeo de valores externos a entidades canónicas.

Revision ID: 0007
Revises: 0006
Create Date: 2026-04-16
"""
from alembic import op

revision = "0007"
down_revision = "0006"
branch_labels = None
depends_on = None


def upgrade():
    op.execute("""
        CREATE TABLE catalog_aliases (
            id           INT          NOT NULL AUTO_INCREMENT,
            entity_type  VARCHAR(50)  NOT NULL,
            source_value VARCHAR(200) NOT NULL,
            entity_id    INT          NOT NULL,
            PRIMARY KEY (id),
            UNIQUE KEY uq_catalog_alias (entity_type, source_value)
        ) DEFAULT CHARSET=utf8mb4
    """)


def downgrade():
    op.drop_table("catalog_aliases")
