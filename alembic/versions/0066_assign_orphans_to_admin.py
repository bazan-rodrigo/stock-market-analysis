"""Asignar al admin las senales/estrategias sin dueno.

Las filas anteriores a la 0065 quedaron con owner_id NULL ("sin dueno",
editables solo por rol admin). A pedido del usuario pasan a ser del
usuario `admin` (ADMIN_USERNAME de config; fallback: primer usuario con
role='admin'), para que figuren con dueno visible en los ABMs.

Si no existe ningun usuario admin en la tabla, la migracion no hace nada
(owner_id NULL sigue siendo un estado valido: edita solo el admin).

Revision ID: 0066
Revises: 0065
"""
import sqlalchemy as sa
from alembic import op

revision = "0066"
down_revision = "0065"
branch_labels = None
depends_on = None


def _admin_id(bind):
    aid = bind.execute(sa.text(
        "SELECT id FROM users WHERE username = 'admin' LIMIT 1")).scalar()
    if aid is None:
        aid = bind.execute(sa.text(
            "SELECT id FROM users WHERE role = 'admin' ORDER BY id LIMIT 1"
        )).scalar()
    return aid


def upgrade() -> None:
    bind = op.get_bind()
    aid = _admin_id(bind)
    if aid is None:
        return
    bind.execute(sa.text(
        "UPDATE `signal` SET owner_id = :aid WHERE owner_id IS NULL"),
        {"aid": aid})
    bind.execute(sa.text(
        "UPDATE strategy SET owner_id = :aid WHERE owner_id IS NULL"),
        {"aid": aid})


def downgrade() -> None:
    # No hay forma de distinguir cuales eran huerfanas: no se revierte.
    pass
