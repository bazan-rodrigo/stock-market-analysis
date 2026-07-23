"""float4 en las tablas dinámicas de señales (sig_*) y estrategias (strat_res_*).

Mismo motivo que 0087: Column(Float) sin precisión = `double precision` (8 B)
en PostgreSQL. score (sig_* y strat_res_*) vive en -100..100 y pct
(strat_res_*) en 0..100 — float4 (~7 dígitos) los cubre de sobra. Las cuatro
tablas sig_* son, juntas, ~48% de la base; recortar el score no las achica
mucho por fila (el peso es índices), pero suma sin resignar nada.

NEUTRAL AL MOTOR: MySQL FLOAT → FLOAT(24) es no-op; PostgreSQL reescribe cada
tabla (lock exclusivo por tabla — correr con el pipeline detenido).

Las tablas son DINÁMICAS (una por señal/estrategia, ver app/models/signal_store):
se descubren por prefijo en runtime, así que esta migración NO se renderiza
offline (guard as_sql, igual que el pivot de 0081). Espeja signal_store._build
(las tablas nuevas ya nacen en float4). Reconcile en el arranque no re-tipa
tablas existentes: por eso el ALTER acá.

Revision ID: 0088
Revises: 0087
"""
import re

import sqlalchemy as sa
from alembic import op

revision = "0088"
down_revision = "0087"
branch_labels = None
depends_on = None

_SIG_RE   = re.compile(r"^sig_\d+$")
_STRAT_RE = re.compile(r"^strat_res_\d+$")


def _retype(new_precision, old_precision) -> None:
    # Dinámica: en modo offline (--sql) no hay catálogo que enumerar → no-op
    # (el render offline de test_bootstrap_portability solo verifica que las
    # migraciones de nombre fijo compilen en ambos dialectos).
    if op.get_context().as_sql:
        return
    bind = op.get_bind()
    new_type = sa.Float(precision=new_precision) if new_precision else sa.Float()
    old_type = sa.Float(precision=old_precision) if old_precision else sa.Float()
    for name in sa.inspect(bind).get_table_names():
        if _SIG_RE.match(name):
            op.alter_column(name, "score", type_=new_type,
                            existing_type=old_type, existing_nullable=False)
        elif _STRAT_RE.match(name):
            op.alter_column(name, "score", type_=new_type,
                            existing_type=old_type, existing_nullable=True)
            op.alter_column(name, "pct", type_=new_type,
                            existing_type=old_type, existing_nullable=True)


def upgrade() -> None:
    _retype(24, None)


def downgrade() -> None:
    _retype(None, 24)
