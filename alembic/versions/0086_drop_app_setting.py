"""Elimina la tabla app_settings: el modo invitado (acceso público) se quitó.

La tabla existía solo para el switch "Acceso sin login" de la pantalla
Configuración de app (creada en la 0034). Ese modo hacía que el visitante
anónimo operara como administrador (GuestUser.is_admin = True con
public_access activo); se eliminó a pedido del usuario — siempre hay que
loguearse con un usuario real — junto con la pantalla, el servicio y el
modelo (jul-2026).

Sin FKs en ninguna dirección → drop_table portable, renderizable offline
contra MySQL y PostgreSQL (tests/test_bootstrap_portability.py).

Revision ID: 0086
Revises: 0085
"""
import sqlalchemy as sa
from alembic import op

revision = "0086"
down_revision = "0085"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.drop_table("app_settings")


def downgrade() -> None:
    # Espejo de la 0034, incluida la fila única con el default apagado.
    op.create_table(
        "app_settings",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("public_access", sa.Boolean(), nullable=False,
                  server_default="0"),
    )
    op.execute("INSERT INTO app_settings (id, public_access) VALUES (1, 0)")
