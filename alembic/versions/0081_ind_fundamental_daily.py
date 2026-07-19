"""Fundamentales anchos: ind_fundamental_daily + ind_fundamental_quarterly.

Los 12 fundamentales pasan de 12 tablas ind_fundamental_* a 2 tablas anchas por
cadencia (misma técnica que ind_daily, docs/notes/design_ind_wide_tables.md):
- ind_fundamental_daily (4): pe_ttm, pb, ps_ttm, pe_growth_yoy (dependen del precio).
- ind_fundamental_quarterly (8): márgenes, growths, roic (grilla trimestral).
Crea las tablas y copia los datos por merge en Python (fila completa, sin bloat).
NO dropea las 12 per-código todavía: quedan de ROLLBACK; se dropean en una
migración posterior tras validar.

DDL (create) renderiza offline; el pivot se saltea offline (guard as_sql).
Create idempotente (evita la carrera con ensure_wide_ind_tables del arranque).

Revision ID: 0081
Revises: 0080

(Encadena DESPUÉS de 0080_portfolio_tables — trabajo paralelo de Backtest+
Carteras. Si ese orden cambia, ajustar down_revision.)
"""
import sqlalchemy as sa
from alembic import op

revision = "0081"
down_revision = "0080"
branch_labels = None
depends_on = None

_DAILY = [
    "fundamental_pe_ttm", "fundamental_pb", "fundamental_ps_ttm",
    "fundamental_pe_growth_yoy",
]
_QUARTERLY = [
    "fundamental_net_margin", "fundamental_gross_margin",
    "fundamental_operating_margin", "fundamental_debt_to_equity",
    "fundamental_revenue_growth_yoy", "fundamental_eps_growth_yoy",
    "fundamental_net_income_growth_yoy", "fundamental_roic",
]
_TABLES = [
    ("ind_fundamental_daily", _DAILY),
    ("ind_fundamental_quarterly", _QUARTERLY),
]

_ASSET_BATCH = 100
_INSERT_BATCH = 5000


def _q(bind, name):
    return f"`{name}`" if bind.dialect.name in ("mysql", "mariadb") else f'"{name}"'


def _create_one(table: str, codes: list) -> None:
    cols = [
        sa.Column("asset_id", sa.Integer(),
                  sa.ForeignKey("assets.id", ondelete="CASCADE"), nullable=False),
        sa.Column("date", sa.Date(), nullable=False),
    ]
    for code in codes:
        cols.append(sa.Column(code, sa.Float(), nullable=True))
    op.create_table(table, *cols, sa.PrimaryKeyConstraint("asset_id", "date"))
    op.create_index(f"ix_{table}_date", table, ["date"])


def _pivot_one(bind, table: str, codes: list) -> None:
    ph = "?" if bind.dialect.paramstyle == "qmark" else "%s"
    present = [c for c in codes if sa.inspect(bind).has_table(f"ind_{c}")]
    if not present:
        return
    ids = set()
    for code in present:
        for (aid,) in bind.execute(sa.text(
                f"SELECT DISTINCT asset_id FROM {_q(bind, 'ind_' + code)}")):
            ids.add(aid)
    ids = sorted(ids)
    col_sql = ", ".join(_q(bind, c) for c in ["asset_id", "date"] + codes)
    ins = (f"INSERT INTO {_q(bind, table)} ({col_sql}) "
           f"VALUES ({', '.join([ph] * (len(codes) + 2))})")
    for i in range(0, len(ids), _ASSET_BATCH):
        batch = ids[i:i + _ASSET_BATCH]
        merged: dict = {}
        for code in present:
            idx = codes.index(code)
            sel = sa.text(
                f"SELECT asset_id, date, value FROM {_q(bind, 'ind_' + code)} "
                "WHERE asset_id IN :ids"
            ).bindparams(sa.bindparam("ids", expanding=True))
            for aid, d, v in bind.execute(sel, {"ids": batch}):
                merged.setdefault((aid, d), [None] * len(codes))[idx] = v
        rows = [(aid, d, *vals) for (aid, d), vals in merged.items()]
        for k in range(0, len(rows), _INSERT_BATCH):
            bind.exec_driver_sql(ins, rows[k:k + _INSERT_BATCH])


def upgrade() -> None:
    offline = op.get_context().as_sql
    bind = None if offline else op.get_bind()
    for table, codes in _TABLES:
        # Idempotente: si ensure_wide_ind_tables (arranque) ya la creó, no
        # re-crear (evita la carrera del deploy). Offline igual emite el DDL.
        if bind is None or not sa.inspect(bind).has_table(table):
            _create_one(table, codes)
    # NO se dropean las 12 per-código: quedan de rollback (drop en migración
    # posterior tras validar).
    if not offline:
        for table, codes in _TABLES:
            _pivot_one(bind, table, codes)


def downgrade() -> None:
    for table, _codes in _TABLES:
        op.drop_table(table)
