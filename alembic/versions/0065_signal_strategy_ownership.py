"""Dueño y visibilidad en senales y estrategias.

- owner_id (FK users.id, SET NULL): quien la creo — controla la EDICION
  (solo admin o el dueno). No cambia al publicar/despublicar.
- is_public: solo VISIBILIDAD (publicas las ven todos; privadas solo el
  dueno y el admin). El pipeline de calculo ignora ambas columnas.

En strategy ya existia created_by (nunca poblado, siempre NULL): se
renombra a owner_id para unificar semantica con signal. Todo lo existente
queda publico (is_public=1) y sin dueno (editable solo por admin) — los
packs de strategy_packs/ importados hasta hoy entran en ese grupo.

El default de is_public queda en 0 (privada) para filas nuevas: el valor
real siempre lo setea la app (switch del ABM / columna `publica` del
import).

Revision ID: 0065
Revises: 0064
"""
import sqlalchemy as sa
from alembic import op

revision = "0065"
down_revision = "0064"
branch_labels = None
depends_on = None


def _strategy_created_by_fk(bind) -> str | None:
    """Nombre real del FK de strategy.created_by (autogenerado por MySQL
    en la 0033 — no se puede hardcodear)."""
    return bind.execute(sa.text(
        "SELECT CONSTRAINT_NAME FROM information_schema.KEY_COLUMN_USAGE "
        "WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = 'strategy' "
        "AND COLUMN_NAME = 'created_by' AND REFERENCED_TABLE_NAME = 'users'"
    )).scalar()


def upgrade() -> None:
    bind = op.get_bind()

    # signal: columnas nuevas (todo lo existente queda publico, sin dueno)
    op.add_column("signal", sa.Column(
        "owner_id", sa.Integer, sa.ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True))
    op.add_column("signal", sa.Column(
        "is_public", sa.Boolean, nullable=False, server_default=sa.text("1")))
    op.alter_column("signal", "is_public", existing_type=sa.Boolean(),
                    nullable=False, server_default=sa.text("0"))

    # strategy: created_by -> owner_id (siempre NULL hoy; el FK autogenerado
    # bloquea el rename, hay que dropearlo y recrearlo)
    fk_name = _strategy_created_by_fk(bind)
    if fk_name:
        op.drop_constraint(fk_name, "strategy", type_="foreignkey")
    op.alter_column("strategy", "created_by", new_column_name="owner_id",
                    existing_type=sa.Integer(), existing_nullable=True)
    op.create_foreign_key("fk_strategy_owner", "strategy", "users",
                          ["owner_id"], ["id"], ondelete="SET NULL")

    op.add_column("strategy", sa.Column(
        "is_public", sa.Boolean, nullable=False, server_default=sa.text("1")))
    op.alter_column("strategy", "is_public", existing_type=sa.Boolean(),
                    nullable=False, server_default=sa.text("0"))


def downgrade() -> None:
    op.drop_column("strategy", "is_public")
    op.drop_constraint("fk_strategy_owner", "strategy", type_="foreignkey")
    op.alter_column("strategy", "owner_id", new_column_name="created_by",
                    existing_type=sa.Integer(), existing_nullable=True)
    op.create_foreign_key(None, "strategy", "users",
                          ["created_by"], ["id"], ondelete="SET NULL")

    op.drop_column("signal", "is_public")
    # add_column creo el FK sin nombre explicito: buscarlo igual que arriba
    bind = op.get_bind()
    fk_name = bind.execute(sa.text(
        "SELECT CONSTRAINT_NAME FROM information_schema.KEY_COLUMN_USAGE "
        "WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = 'signal' "
        "AND COLUMN_NAME = 'owner_id' AND REFERENCED_TABLE_NAME = 'users'"
    )).scalar()
    if fk_name:
        op.drop_constraint(fk_name, "signal", type_="foreignkey")
    op.drop_column("signal", "owner_id")
