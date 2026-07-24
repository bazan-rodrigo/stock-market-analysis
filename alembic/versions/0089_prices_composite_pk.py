"""prices: PK compuesta (asset_id, date), dropea la columna `id` sustituta.

`prices.id` era una PK autoincremental HEREDADA de InnoDB (donde la PK es el
índice clusterizado y una PK autoincremental hace que los inserts vayan al
final). En PostgreSQL el heap es desordenado y esa PK es un índice más: medido
`idx_scan=0` y **97 MB** de índice (`prices_pkey`) que nadie consulta. Ninguna
FK la referencia y no se lee en el código (grep). La identidad real de un precio
es (asset_id, date) — ya cubierta por el UNIQUE `uq_asset_date`.

Rama por dialecto (soporte dual, portable desde la 0076):
- **PostgreSQL** (producción): PROMUEVE el índice único existente a PK
  (`USING INDEX uq_asset_date`, sin reconstruirlo) y dropea el índice de `id`
  → 97 MB liberados al instante. `DROP COLUMN id` es metadata-only (el heap no
  se reescribe; el espacio de la columna se recicla con el tiempo).
- **MySQL/MariaDB**: la PK ES el clustered index en InnoDB → cambiar la PK
  RECONSTRUYE la tabla y cambia el orden físico de inserción. **RAMA NO
  VALIDADA contra MariaDB viva** (mismo estatus que el refactor de tablas
  anchas): el SQL queda escrito para conservar el dual, no ejercitado.

Espeja app/models/price.py (bases nuevas nacen ya con PK compuesta, sin `id`).
El upsert de precios sigue igual: db_compat._conflict_cols usa la PK cuando los
valores la traen completa — antes caía al fallback uq_asset_date, ahora usa la
PK (asset_id, date) directo, mismo target de conflicto.

SQL crudo por dialecto → op.execute (el meta-test de portabilidad renderiza el
texto de cada rama sin ejecutarlo).

Revision ID: 0089
Revises: 0088
"""
from alembic import op

revision = "0089"
down_revision = "0088"
branch_labels = None
depends_on = None


def upgrade() -> None:
    dialect = op.get_context().dialect.name
    if dialect == "postgresql":
        op.execute("ALTER TABLE prices DROP CONSTRAINT prices_pkey")
        op.execute("ALTER TABLE prices ADD CONSTRAINT prices_pkey "
                   "PRIMARY KEY USING INDEX uq_asset_date")
        op.execute("ALTER TABLE prices DROP COLUMN id")
    elif dialect in ("mysql", "mariadb"):
        # RAMA NO VALIDADA. InnoDB reconstruye la tabla (re-clusteriza por la
        # nueva PK). Hay que quitar AUTO_INCREMENT antes de soltar la PK.
        op.execute("ALTER TABLE prices MODIFY id INT NOT NULL")
        op.execute("ALTER TABLE prices DROP PRIMARY KEY, "
                   "ADD PRIMARY KEY (asset_id, date)")
        op.execute("ALTER TABLE prices DROP COLUMN id")
        op.execute("ALTER TABLE prices DROP INDEX uq_asset_date")
    # sqlite (tests): las bases de test nacen por create_all desde el modelo ya
    # actualizado (PK compuesta, sin id) → nada que migrar acá.


def downgrade() -> None:
    dialect = op.get_context().dialect.name
    if dialect == "postgresql":
        # ADD COLUMN ... SERIAL repuebla las filas existentes (el DEFAULT
        # nextval es volátil → se evalúa por fila al agregar la columna).
        op.execute("ALTER TABLE prices ADD COLUMN id SERIAL")
        op.execute("ALTER TABLE prices DROP CONSTRAINT prices_pkey")
        op.execute("ALTER TABLE prices ADD CONSTRAINT prices_pkey PRIMARY KEY (id)")
        op.execute("ALTER TABLE prices ADD CONSTRAINT uq_asset_date "
                   "UNIQUE (asset_id, date)")
    elif dialect in ("mysql", "mariadb"):
        op.execute("ALTER TABLE prices DROP PRIMARY KEY")
        op.execute("ALTER TABLE prices ADD COLUMN id INT NOT NULL AUTO_INCREMENT "
                   "PRIMARY KEY FIRST")
        op.execute("ALTER TABLE prices ADD UNIQUE uq_asset_date (asset_id, date)")
