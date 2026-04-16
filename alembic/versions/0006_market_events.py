"""Crea tabla market_event para eventos de mercado.

Revision ID: 0006
Revises: 0005
Create Date: 2026-04-16
"""
from alembic import op
import sqlalchemy as sa

revision = "0006"
down_revision = "0005"
branch_labels = None
depends_on = None


def upgrade():
    # FK constraints se omiten para compatibilidad con MariaDB/MyISAM.
    # Las relaciones se gestionan a nivel ORM (SQLAlchemy).
    op.execute("""
        CREATE TABLE market_event (
            id         INT          NOT NULL AUTO_INCREMENT,
            name       VARCHAR(200) NOT NULL,
            start_date DATE         NOT NULL,
            end_date   DATE         NOT NULL,
            scope      VARCHAR(10)  NOT NULL DEFAULT 'global',
            country_id INT          NULL,
            asset_id   INT          NULL,
            color      VARCHAR(20)  NULL DEFAULT '#ff9800',
            PRIMARY KEY (id)
        ) DEFAULT CHARSET=utf8mb4
    """)


def downgrade():
    op.drop_table("market_event")
