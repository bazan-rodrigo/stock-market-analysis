"""Una tabla por señal (sig_{id}) y por estrategia (strat_res_{id}) —
mismo patrón que los ind_{code} de indicadores. Motivo (medido en las
sesiones del 15-16 jul-2026): la unidad de recálculo no coincidía con la
unidad de almacenamiento, así que todo recálculo acotado pagaba
borrar-e-insertar dentro de tablas pobladas (3-5× más caro que en vacías);
con tabla propia, recalcular una unidad es TRUNCATE + insertar en vacío.

Copia la historia existente con INSERT…SELECT por unidad (inserción en
tabla vacía, lo barato) y dropea las monolíticas signal_value /
strategy_result — se sale de la migración con la historia intacta, sin
recálculo obligatorio.

PK (date, asset_id) — date primero: inserciones cronológicas append-only
y ventanas de fechas usan el prefijo (lección del staging: con date al
final cada ventana hacía full scan). Índice secundario (asset_id, date)
para lecturas por activo. Sin FK a assets: purge_assets limpia estas
tablas explícitamente (igual que ind_%) y el chequeo encarecería los
inserts masivos.

Revision ID: 0075
Revises: 0074
"""
import sqlalchemy as sa
from alembic import op

revision = "0075"
down_revision = "0074"
branch_labels = None
depends_on = None


def _create_sig_table(name: str) -> None:
    op.create_table(
        name,
        sa.Column("asset_id", sa.Integer, nullable=False),
        sa.Column("date",     sa.Date,    nullable=False),
        sa.Column("score",    sa.Float,   nullable=False),
        sa.PrimaryKeyConstraint("date", "asset_id"),
    )
    op.create_index(f"ix_{name}_asset_date", name, ["asset_id", "date"])


def _create_strat_table(name: str) -> None:
    op.create_table(
        name,
        sa.Column("asset_id", sa.Integer, nullable=False),
        sa.Column("date",     sa.Date,    nullable=False),
        sa.Column("score",    sa.Float),
        sa.Column("pct",      sa.Float),
        sa.PrimaryKeyConstraint("date", "asset_id"),
    )
    op.create_index(f"ix_{name}_asset_date", name, ["asset_id", "date"])


def upgrade() -> None:
    conn = op.get_bind()

    # backticks: `signal` es palabra reservada en MariaDB (la sentencia SIGNAL)
    sig_ids = [i for (i,) in conn.execute(sa.text("SELECT id FROM `signal`"))]
    for sid in sig_ids:
        name = f"sig_{sid}"
        _create_sig_table(name)
        conn.execute(sa.text(
            f"INSERT INTO {name} (asset_id, date, score) "
            f"SELECT asset_id, date, score FROM signal_value "
            f"WHERE signal_id = {int(sid)}"))

    strat_ids = [i for (i,) in conn.execute(sa.text("SELECT id FROM strategy"))]
    for sid in strat_ids:
        name = f"strat_res_{sid}"
        _create_strat_table(name)
        conn.execute(sa.text(
            f"INSERT INTO {name} (asset_id, date, score, pct) "
            f"SELECT asset_id, date, score, pct FROM strategy_result "
            f"WHERE strategy_id = {int(sid)}"))

    op.drop_table("signal_value")
    op.drop_table("strategy_result")


def downgrade() -> None:
    conn = op.get_bind()
    is_mysql = conn.dialect.name in ("mysql", "mariadb")

    op.create_table(
        "signal_value",
        sa.Column("id",        sa.Integer, primary_key=True),
        sa.Column("signal_id", sa.Integer,
                  sa.ForeignKey("signal.id", ondelete="CASCADE"),
                  nullable=False),
        sa.Column("asset_id",  sa.Integer,
                  sa.ForeignKey("assets.id", ondelete="CASCADE"),
                  nullable=False),
        sa.Column("date",  sa.Date,  nullable=False),
        sa.Column("score", sa.Float, nullable=False),
        sa.UniqueConstraint("signal_id", "asset_id", "date"),
    )
    op.create_index("ix_signal_value_signal_id", "signal_value", ["signal_id"])
    op.create_index("ix_signal_value_asset_id",  "signal_value", ["asset_id"])
    op.create_index("ix_signal_value_date",      "signal_value", ["date"])

    op.create_table(
        "strategy_result",
        sa.Column("id",          sa.Integer, primary_key=True),
        sa.Column("strategy_id", sa.Integer,
                  sa.ForeignKey("strategy.id", ondelete="CASCADE"),
                  nullable=False),
        sa.Column("asset_id",    sa.Integer,
                  sa.ForeignKey("assets.id", ondelete="CASCADE"),
                  nullable=False),
        sa.Column("date",  sa.Date, nullable=False),
        sa.Column("score", sa.Float),
        sa.Column("pct",   sa.Float),
        sa.UniqueConstraint("strategy_id", "asset_id", "date"),
    )
    op.create_index("ix_strategy_result_strategy_id", "strategy_result",
                    ["strategy_id"])
    op.create_index("ix_strategy_result_asset_id", "strategy_result",
                    ["asset_id"])
    op.create_index("ix_strategy_result_date", "strategy_result", ["date"])

    like = ("SHOW TABLES LIKE :p" if is_mysql else
            "SELECT name FROM sqlite_master WHERE type='table' AND name LIKE :p")
    for (name,) in list(conn.execute(sa.text(like), {"p": "sig\\_%"})):
        sid = name.split("_")[-1]
        if not sid.isdigit():
            continue
        conn.execute(sa.text(
            f"INSERT INTO signal_value (signal_id, asset_id, date, score) "
            f"SELECT {int(sid)}, asset_id, date, score FROM {name}"))
        op.drop_table(name)
    for (name,) in list(conn.execute(sa.text(like), {"p": "strat\\_res\\_%"})):
        sid = name.split("_")[-1]
        if not sid.isdigit():
            continue
        conn.execute(sa.text(
            f"INSERT INTO strategy_result (strategy_id, asset_id, date, score, pct) "
            f"SELECT {int(sid)}, asset_id, date, score, pct FROM {name}"))
        op.drop_table(name)
