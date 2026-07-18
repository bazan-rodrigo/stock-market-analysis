"""Fase 5: DROP de las 24 tablas ind_{code} técnicas (ya viven en las anchas).

Cierre del refactor a tablas anchas (docs/notes/design_ind_wide_tables.md): las
columnas de estos 24 códigos están en ind_daily/ind_weekly/ind_monthly
(migraciones 0077/0078) y el código las lee/escribe por defecto
(use_wide_ind_tables()). Este DROP es el PUNTO DE NO RETORNO: libera el espacio
(la app ya no las usa). Los fundamentales (ind_fundamental_*) NO se tocan.

El DROP renderiza offline (DDL) → cubierto por tests/test_bootstrap_portability.
El downgrade recrea las tablas (esquema de la 0043 + índice por date de la 0062)
y las repuebla desde las anchas (parte de datos con guard offline).

Revision ID: 0079
Revises: 0078
"""
import sqlalchemy as sa
from alembic import op

revision = "0079"
down_revision = "0078"
branch_labels = None
depends_on = None

# (code, tipo_col, tabla_ancha). Autocontenido (snapshot).
_STR = "str"
_NUM = "num"
_CODES = [
    # daily -> ind_daily
    ("trend_daily", _STR, "ind_daily"), ("volatility_daily", _STR, "ind_daily"),
    ("atr_percentile_daily", _NUM, "ind_daily"), ("rsi_daily", _NUM, "ind_daily"),
    ("dist_sma20", _NUM, "ind_daily"), ("dist_sma50", _NUM, "ind_daily"),
    ("dist_sma200", _NUM, "ind_daily"),
    ("dist_optimal_sma_daily", _NUM, "ind_daily"),
    ("return_daily", _NUM, "ind_daily"), ("return_monthly", _NUM, "ind_daily"),
    ("return_quarterly", _NUM, "ind_daily"), ("return_yearly", _NUM, "ind_daily"),
    ("return_52w", _NUM, "ind_daily"),
    ("relative_strength_52w", _NUM, "ind_daily"),
    # weekly -> ind_weekly
    ("trend_weekly", _STR, "ind_weekly"), ("volatility_weekly", _STR, "ind_weekly"),
    ("atr_percentile_weekly", _NUM, "ind_weekly"),
    ("rsi_weekly", _NUM, "ind_weekly"),
    ("dist_optimal_sma_weekly", _NUM, "ind_weekly"),
    # monthly -> ind_monthly
    ("trend_monthly", _STR, "ind_monthly"),
    ("volatility_monthly", _STR, "ind_monthly"),
    ("atr_percentile_monthly", _NUM, "ind_monthly"),
    ("rsi_monthly", _NUM, "ind_monthly"),
    ("dist_optimal_sma_monthly", _NUM, "ind_monthly"),
]


def upgrade() -> None:
    for code, _tp, _wide in _CODES:
        op.drop_table(f"ind_{code}")


def downgrade() -> None:
    # Recrear el esquema per-código (idéntico a la 0043 + índice de la 0062).
    for code, tp, _wide in _CODES:
        name = f"ind_{code}"
        vcol = (sa.Column("value", sa.String(50), nullable=True) if tp == _STR
                else sa.Column("value", sa.Float(), nullable=True))
        op.create_table(
            name,
            sa.Column("asset_id", sa.Integer(),
                      sa.ForeignKey("assets.id", ondelete="CASCADE"),
                      nullable=False),
            sa.Column("date", sa.Date(), nullable=False),
            vcol,
            sa.PrimaryKeyConstraint("asset_id", "date"),
        )
        op.create_index(f"ix_{name}_date", name, ["date"])

    # Repoblar desde las anchas (datos: no offline).
    if op.get_context().as_sql:
        return
    bind = op.get_bind()

    def q(n):
        return f"`{n}`" if bind.dialect.name in ("mysql", "mariadb") else f'"{n}"'

    for code, _tp, wide in _CODES:
        bind.execute(sa.text(
            f"INSERT INTO {q('ind_' + code)} (asset_id, date, value) "
            f"SELECT asset_id, date, {q(code)} FROM {q(wide)} "
            f"WHERE {q(code)} IS NOT NULL"))
