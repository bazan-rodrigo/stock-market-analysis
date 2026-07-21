---
name: postgresql-migracion-futura
description: "Migración a PostgreSQL con soporte dual: FASES 1-4 IMPLEMENTADAS y pusheadas (db_compat 5029d9e, bootstrap 27b2d95, semántica 0086bfb, entorno DB_ENGINE 0df8a9d — 16-jul-2026); faltan 5 (paridad, Codespace) y 6 (datos)"
metadata: 
  node_type: memory
  type: project
  originSessionId: afebd59f-7b20-434c-a0ab-7c3cbd794a91
---

Estudio de impacto/factibilidad/riesgo hecho el 16-jul-2026 (auditoría
multi-agente de 8 dimensiones, ~75 hallazgos confirmados). Veredicto:
factible; acoplamiento MySQL concentrado en ~14 archivos de app/scripts y
~20 de las 75 migraciones Alembic. Requisito del usuario: soporte DUAL —
la app debe seguir corriendo contra MySQL igual que hoy; el motor se elige
solo por DATABASE_URL (mecanismo ya existente en app/config.py).

**Decisiones del plan (acordadas en la conversación del estudio):**
- Capa `db_compat` con despacho por `dialect.name`; la rama MySQL emite el
  SQL byte-idéntico al actual (test de compilación que lo verifica).
- Cadena Alembic 0001–0075 congelada como solo-MySQL. Bases nuevas (MySQL
  y PG) nacen por `create_all + alembic stamp head` (extender
  scripts/init_db.py); requiere: (a) diff autogenerate vacío cadena vs
  modelos, (b) mudar seeds de catálogo de migraciones a
  ensure_builtin_data. Desde 0076: UNA sola cadena portable para ambos
  motores (nada de backticks/DATABASE()/0-1 en Boolean/sa.Enum sin name=;
  meta-test con `alembic upgrade --sql` offline contra ambos dialectos).
- Driver propuesto: `psycopg[binary]` (v3) conviviendo con mysqlclient en
  requirements.txt. Setup del Codespace con variable DB_ENGINE
  (mysql|postgres|both, default mysql); PG 16/17 vía repo PGDG (bullseye
  trae PG13, EOL nov-2026).
- Fases: 0 decisiones → 1 db_compat + call sites → 2 bootstrap/baseline →
  3 semántica (NULLs ranking, case-insensitive login/aliases, Float,
  aislamiento, rollback consola SQL) → 4 entorno/setup.sh → 5 paridad en
  Codespace con ambos motores (mismo dataset, comparar scores/rankings,
  medir perf) → 6 datos reales (copiar tablas fuente, regenerar derivadas).

**Hallazgos clave a no olvidar al implementar:**
- Bloqueantes PG: upserts ON DUPLICATE (4 servicios ORM + 3 crudos en
  technical_service, incl. _write_ind_series L726); backticks en
  reconcile_dynamic_tables (signal_store.py:153 — rompe el ARRANQUE);
  _set_bulk_load_checks (SET SESSION foreign_key_checks + except:pass —
  en PG envenena la transacción); information_schema+DATABASE() y
  DELETE...LIMIT en purge_assets/clean_data/limpiezas admin.
- Trampas silenciosas: PG caería en las ramas "else" pensadas para sqlite
  (purge_assets dejaría huérfanas las tablas dinámicas; escritor asíncrono
  del backfill deshabilitado; DELETE FROM en vez de TRUNCATE); retry de
  deadlocks por errno 1205/1213 nunca matchea en psycopg (usar pgcode
  40P01/55P03/40001); ORDER BY score DESC pone NULLs primero en PG (y
  MariaDB NO soporta NULLS LAST — fix portable); collation _ci sostiene
  login/aliases/keys de señales; sa.Float = 4 bytes MySQL vs 8 PG;
  REPEATABLE READ vs READ COMMITTED afecta la transacción lectora larga
  del backfill.
- Ya portable (no tocar): delete_by_ranges, INSERT masivo del backfill
  (rama paramstyle), DDL de sig_/strat_res_, init_db.py, env.py, nombres
  de tablas dinámicas (lowercase, <63 chars).

**FASE 1 IMPLEMENTADA (16-jul-2026, misma sesión del estudio):** creado
app/services/db_compat.py (upsert ORM + upsert_sql crudo + quote_ident +
is_retryable_lock_error + set_bulk_load_checks + wipe_table +
list_tables_by_prefix + approx_table_rows) y migrados los ~12 archivos de
call sites; psycopg[binary] agregado a requirements.txt; el estudio quedó
en docs/notes/design_postgresql_dual.md. tests/test_db_compat.py fija la
paridad byte-idéntica del SQL MySQL (23 tests). Suite completa: 528 passed.
Detalle clave descubierto al implementar: prices tiene PK id autoincrement
+ UNIQUE(asset_id,date) → el ON CONFLICT de PG debe derivarse a la UNIQUE
cuando la PK no viene en los values (db_compat._conflict_cols). Pendiente
de verificar en Codespace contra MariaDB real (y PG cuando se instale).

**FASE 2 IMPLEMENTADA (16-jul, commit 27b2d95):** init_db.py con base
vacía → create_all + stamp head (base existente → upgrade head;
--via-migrations fuerza la cadena); Enums con name= (user_role,
import_status); ensure_ind_table() materializa las ind_{code} en el
arranque (¡no están en Base.metadata! — gap descubierto en fase 2); seed
FundamentalSource movido a ensure_builtin_data (las demás configs ya
hacían get-or-create; los seeds de señales de 0033 los borró la 0064 —
NO sembrarlos); env.py inyecta URL solo si falta;
tests/test_bootstrap_portability.py renderiza offline las migraciones
post-freeze-0075 contra ambos dialectos (harness verificado: 0001 pasa
mysql / falla PG por Enum sin nombre). Suite: 530 passed, 2 skipped.
Nota entorno: alembic NO estaba en el venv local (se instaló 16-jul) —
la nota "todas menos mysqlclient y yfinance" era imprecisa.

**FASE 3 IMPLEMENTADA (16-jul, commit 0086bfb):** order_desc_nulls_last
(ranking, 2 sitios en strategy_service) + ci_equals (login, keys de
señal, nombre de estrategia en import, aliases de catálogo — acentos NO
replicados en PG, asumido) + rollback de consola SQL solo-PG + pool
configurable (db_pool_size/db_max_overflow). Decisiones documentadas:
sa.Float se mantiene; aislamiento sin cambio (revisar en paridad).

**FASE 4 IMPLEMENTADA (16-jul, commit 0df8a9d):** DB_ENGINE
(mysql|postgres|both) en .devcontainer/setup.sh, scripts/
codespace_setup.sh y devcontainer.json; rama PG instala PostgreSQL 16
vía PGDG, crea base con psql, init_db con DATABASE_URL (~/.bashrc en
modo postgres); modo both = ambos motores para paridad. CLAUDE.md
actualizado (stack/flujo dual + convención db_compat). Fix drive-by:
check de admin de codespace_setup.sh consultaba tabla `user` (es
`users`) — nunca podía pasar.

**Verificación autogenerate (16-jul, commit 3970763):** el usuario corrió
`alembic revision --autogenerate` en el Codespace — diff NO vacío: (a)
autogenerate proponía DROPear todas las tablas dinámicas (no están en
Base.metadata) → filtro include_object en env.py; (b) drift real de
índices que create_all no producía → modelos alineados: group_scores
(ix_group_indicator_snapshot_* heredados del rename 0050),
indicator_definitions (UNIQUE 'code' + ix no-unique), market_event (0028),
prices ix_prices_date (0063), strategy_component (0041). Recordar: la
revisión autogenerada en el Codespace debe BORRARSE (contiene los DROPs).
Re-verificado con `alembic check` (16-jul): "No new upgrade operations
detected" → EQUIVALENCIA cadena↔modelos VALIDADA sobre MariaDB real; el
bootstrap create_all+stamp queda confirmado para cualquier motor.

**Herramienta de paridad (16-jul, commit c2652db):**
`scripts/compare_engines.py <url_A> <url_B>` — conteos por tabla,
agregados por fecha con tolerancia (float4 MySQL vs float8 PG), ORDEN
del ranking por estrategia en la última fecha común (empates por
precisión = WARN); exit 0/1. Suite: 542 passed, 2 skipped.

**Pendiente (FASE 5, ejecución del usuario):** ambiente con
DB_ENGINE=both — recomendado un Codespace DESCARTABLE aparte (el usuario
NO quiere PG en su ambiente habitual; both es opt-in solo para paridad);
mismo dataset en ambos motores; "Recalcular completo" contra cada uno;
correr compare_engines.py; smoke de login/import/consola SQL; medir perf
(lectura ind_*, rebuild, delete_by_ranges bajo autovacuum); init_db.py
sobre base vacía en ambos motores. Después FASE 6 (datos reales: copiar
tablas fuente, regenerar derivadas con Recalcular completo).

**Decisión 16-jul:** ProcessPool DESACOPLADO de esta migración (dual
primero) — revierte el acople del 12-jul con
[[processpool-particion-por-activos]]. Ver también [[feedback_mariadb]] y
[[project_decisions]].
