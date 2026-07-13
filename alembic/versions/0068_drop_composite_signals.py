"""Elimina la fórmula compuesta (composite) de señales.

La combinación de señales se hace ahora en la estrategia, con componentes
ponderados; el tipo de fórmula "composite" se removió. Esta migración borra
las señales composite que pudieran quedar. Sus signal_value/group_signal_value
se van por FK ON DELETE CASCADE; signal_eval_log (alcance señal) no tiene FK,
se limpia a mano. Si alguna composite estuviera referenciada por un componente
de estrategia (FK RESTRICT), la migración falla a propósito: hay que sacarla de
esa estrategia primero.

Revision ID: 0068
Revises: 0067
"""
import sqlalchemy as sa
from alembic import op

revision = "0068"
down_revision = "0067"
branch_labels = None
depends_on = None


def upgrade() -> None:
    conn = op.get_bind()
    conn.execute(sa.text(
        "DELETE FROM signal_eval_log WHERE scope_kind = 'signal' AND ref_id IN "
        "(SELECT id FROM `signal` WHERE formula_type = 'composite')"))
    conn.execute(sa.text(
        "DELETE FROM `signal` WHERE formula_type = 'composite'"))


def downgrade() -> None:
    # No se puede recrear una feature removida; nada que revertir.
    pass
