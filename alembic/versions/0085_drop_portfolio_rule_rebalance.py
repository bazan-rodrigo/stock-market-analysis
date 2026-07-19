"""Limpieza de composición de carteras: quita columnas sin uso.

- rule_json: placeholder del método 'regla dinámica', descartado (redundante con
  la cartera derivada de estrategia). Nunca se escribió ni se leyó.
- rebalance: columna write-only (se persistía al 'promover a seguimiento' pero
  ningún lector la consulta; la curva curada usa rebalance_every=1). Removida.

Ambas SIN FK → drop_column portable, renderizable offline contra MySQL y
PostgreSQL (tests/test_bootstrap_portability.py). No toca benchmark_asset_id
(tiene FK a assets → su baja requiere manejo aparte).

Revision ID: 0085
Revises: 0084
"""
import sqlalchemy as sa
from alembic import op

revision = "0085"
down_revision = "0084"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.drop_column("portfolio", "rule_json")
    op.drop_column("portfolio", "rebalance")


def downgrade() -> None:
    op.add_column("portfolio", sa.Column("rebalance", sa.Integer()))
    op.add_column("portfolio", sa.Column("rule_json", sa.Text()))
