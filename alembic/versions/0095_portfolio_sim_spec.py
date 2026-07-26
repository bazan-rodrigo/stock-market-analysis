"""Spec de simulación en carteras de seguimiento derivadas de estrategia.

Agrega a `portfolio` dos campos (sólo los usan las teóricas 'strategy' promovidas
desde el Backtest de cartera):
- `sim_spec` (Text/JSON): {top_n, rebalance, cost_bps, spec} — misma forma que
  PortfolioRun.config. Hace la cartera AUTOCONTENIDA y re-corrible (botón
  "Recalcular curva").
- `source_run_id` (Integer plano, SIN FK de BD): apunta al PortfolioRun cuyo
  snapshot gated dibuja /carteras. Integer plano igual que `strategy_id` —el
  servicio tolera que el run ya no exista (get_portfolio_run cae a None)— y así la
  migración renderiza offline en ambos dialectos sin ALTER ... ADD CONSTRAINT.

Sólo DDL portable (add_column), renderizable offline contra MySQL y PostgreSQL.

Revision ID: 0095
Revises: 0094
"""
import sqlalchemy as sa
from alembic import op

revision = "0095"
down_revision = "0094"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("portfolio", sa.Column("sim_spec", sa.Text()))
    op.add_column("portfolio", sa.Column("source_run_id", sa.Integer()))


def downgrade() -> None:
    op.drop_column("portfolio", "source_run_id")
    op.drop_column("portfolio", "sim_spec")
