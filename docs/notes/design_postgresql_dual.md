# Soporte dual MySQL/MariaDB ↔ PostgreSQL — estudio y plan

> Estudio de impacto/factibilidad/riesgo hecho el 16-jul-2026 (auditoría
> multi-agente sobre todo el repo, ~75 hallazgos confirmados). Requisito:
> **incorporar PostgreSQL sin perder MySQL** — la app corre contra cualquiera
> de los dos según `DATABASE_URL`, y lo que hoy funciona con MySQL no se toca.

## Veredicto

Factible. El acoplamiento MySQL está concentrado (~14 archivos de app/scripts,
~20 de 75 migraciones Alembic) y el proyecto ya tenía media infraestructura:
selección de motor por `DATABASE_URL` (`app/config.py`), ORM/Core portable en
casi todo el acceso a datos, DDL portable en las tablas dinámicas
`sig_{id}`/`strat_res_{id}`, y el patrón "despacho por dialecto" ya inventado
(`purge_assets`, `signal_backfill_range`).

## Decisiones (16-jul-2026)

- **Driver:** `psycopg[binary]` (v3), conviviendo con `mysqlclient` en
  `requirements.txt`. El motor lo decide solo la URL
  (`mysql+mysqldb://` vs `postgresql+psycopg://`).
- **Capa `db_compat`** (`app/services/db_compat.py`): todo SQL con sabor a
  motor pasa por ahí, con despacho por `dialect.name`. **La rama MySQL emite
  el SQL byte-idéntico al histórico** — `tests/test_db_compat.py` lo fija.
- **Alembic:** la cadena 0001–0075 queda congelada como solo-MySQL (contiene
  sintaxis que no corre en PG: backticks, `AUTO_INCREMENT` crudo, `DATABASE()`,
  enteros en Boolean, `sa.Enum` sin `name=` en la 0001). Toda base nueva
  (MySQL o PG) nace por `create_all + alembic stamp head` (extender
  `scripts/init_db.py`). Desde la 0076: **una sola cadena portable** para
  ambos motores (verificable con `alembic upgrade --sql` offline por dialecto).
- **ProcessPool desacoplado:** primero el soporte dual, ProcessPool después
  (revierte el acople decidido el 12-jul).
- **Setup del Codespace:** variable `DB_ENGINE` (`mysql`|`postgres`|`both`,
  default `mysql`). La rama PG instala desde el repo PGDG (bullseye trae
  PG13, EOL nov-2026).

## Inventario de impacto (qué rompe contra PG)

**Bloqueantes de runtime**

| Qué | Dónde |
|---|---|
| Upserts `ON DUPLICATE KEY UPDATE` (ORM dialecto mysql) | `technical_service` (×3), `fundamental_service` (×5), `price_service`, `synthetic_service` |
| Upserts crudos (backticks + `VALUES()`) vía `exec_driver_sql` | `technical_service._write_ind_series` (camino caliente de `ind_{code}`), `_upsert_ind_asset_meta`, `_upsert_ind_stats_meta` |
| Backticks en `SELECT id FROM \`signal\`` — **rompe el arranque** | `signal_store.reconcile_dynamic_tables` (corre en startup) |
| `SET SESSION foreign_key_checks` + `except: pass` — en PG el statement fallido **aborta la transacción entera** | `technical_service._set_bulk_load_checks` (usado también por fundamental) |
| `information_schema` + `DATABASE()`, `DELETE ... LIMIT`, `SET FOREIGN_KEY_CHECKS`, backticks | `asset_service.purge_assets`, `scripts/clean_data.py`, `admin_cleanup_callbacks`, `data_center_callbacks` (estimación de filas), `admin_sql` (query default) |

**Trampas silenciosas** (sin error de sintaxis)

- Los despachos `is_mysql` tratan a PG como el camino sqlite/tests:
  `purge_assets` dejaría **historia huérfana** en las tablas dinámicas (no
  tienen FK a assets); el **escritor asíncrono** del backfill se desactivaría;
  `DELETE FROM` completo en vez de `TRUNCATE` (que en PG existe y es
  transaccional).
- Retry de deadlock/lock-timeout por errno MySQL 1205/1213: en psycopg el
  código va en `pgcode`/`sqlstate` (`40P01`, `55P03`, `40001`) — los
  reintentos quedaban apagados en silencio.
- `ORDER BY score DESC` pone NULLs **primero** en PG (últimos en MySQL) —
  ranking de estrategias. Ojo: MariaDB NO soporta `NULLS LAST`; el fix debe
  ser portable. (Fase 3.)
- Collation case-insensitive de MySQL sostiene login, keys de señales y
  aliases de catálogo — en PG se vuelven case-sensitive. (Fase 3.)
- `sa.Float` sin precisión = FLOAT 4 bytes en MySQL, `double precision` en PG
  (afecta igualdades del delta tail-mode y empates de ranking). (Fase 3.)
- Aislamiento default: REPEATABLE READ (InnoDB) vs READ COMMITTED (PG) — la
  transacción lectora larga del backfill pierde su snapshot estable. (Fase 3.)
- Consola SQL admin: sin rollback tras error → en PG la transacción queda
  abortada. (Fase 3.)
- Pool 30+20 conexiones vs `max_connections=100` default de PG. (Fase 3.)

**Ya portable (no tocar):** `delete_by_ranges`, INSERT masivo del backfill
(rama por `paramstyle`), DDL de `sig_`/`strat_res_` (Core `Table.create`),
`init_db.py`, `alembic/env.py`, nombres de tablas dinámicas (lowercase,
máx. 38 chars < límite 63 de PG). No hay `FOR UPDATE`/`LOCK TABLES`/
`GET_LOCK`, ni GROUP BY permisivo, ni `lastrowid`, ni booleanos crudos.

## Capa db_compat (fase 1 — implementada)

API en `app/services/db_compat.py`:

- `upsert(bind, target, values, update)` — INSERT…upsert portable sobre la PK;
  el sentinel `INSERTED` marca "valor entrante" (`VALUES(col)` /
  `EXCLUDED.col`). MySQL compila byte-idéntico al viejo
  `on_duplicate_key_update`. sqlite también soporta (los tests EJECUTAN
  upserts reales ahora).
- `upsert_sql(bind, table, columns, update_cols, pk_cols, quote_table)` —
  generador del SQL crudo de los caminos calientes (`exec_driver_sql`),
  placeholder según `paramstyle` del driver.
- `quote_ident(bind, name)` — quoting incondicional por dialecto (backtick /
  comilla doble).
- `is_retryable_lock_error(exc)` — errno 1205/1213 (MySQLdb) ∪ SQLSTATE
  40001/40P01/55P03 (psycopg2 `pgcode` / psycopg3 `sqlstate`).
- `set_bulk_load_checks(s, enabled)` — chequea dialecto ANTES de emitir SQL
  (no-op fuera de MySQL; nunca envenena la transacción de PG).
- `wipe_table(session, name)` / `supports_truncate(bind)` — TRUNCATE en
  MySQL **y PG**, DELETE solo en sqlite.
- `list_tables_by_prefix(bind, *prefixes)` — inspector de SQLAlchemy en vez
  de `information_schema + DATABASE()`.
- `approx_table_rows(session, prefix)` — estimación de filas por catálogo
  (information_schema / `pg_class.reltuples` / COUNT en sqlite).
- `is_mysql(bind)` / `is_postgres(bind)`.

Reglas del módulo: la rama MySQL no se toca (paridad byte a byte testeada);
PG tiene rama propia — **nunca** cae al camino de sqlite/tests.

## Plan por fases

1. **db_compat + call sites + tests de paridad** — HECHA (16-jul, commit 5029d9e).
2. **Bootstrap** — HECHA (16-jul). Implementación:
   - `scripts/init_db.py`: base vacía → `create_all` + `alembic stamp head`
     (único camino válido en PG; recomendado también para MySQL nuevo);
     base existente → `upgrade head`; `--via-migrations` fuerza el replay
     de la cadena (solo MySQL, para comparar esquemas).
   - `sa.Enum` con `name=` en `user.role` (`user_role`) e
     `import_log.status` (`import_status`) — MySQL sigue rindiendo
     `ENUM(...)` idéntico; PG ahora puede emitir `CREATE TYPE`.
   - **Tablas `ind_{code}`**: no están en `Base.metadata` (las creaban las
     migraciones 0043/0060) → `indicator_store.ensure_ind_table()` las
     materializa desde `IndicatorDefinition` en `ensure_builtin_data`
     (esquema fiel a 0043 + índice date de 0062). En bases migradas es
     solo una inspección.
   - **Seeds**: el único seed de migración que faltaba en startup era
     `FundamentalSource` "Yahoo Finance" (0035) → movido a
     `ensure_builtin_data`. Las configs singleton (regime, drawdown,
     volatility, scheduler, app_settings) ya hacían get-or-create, y los
     seeds de señales de la 0033 fueron BORRADOS por la 0064 (una base
     nueva no debe sembrarlos).
   - `alembic/env.py` inyecta `Config.DATABASE_URL` solo si la URL no
     viene definida → permite renders offline con URL explícita.
   - Meta-test `tests/test_bootstrap_portability.py`: renderiza offline
     (`--sql`) las migraciones posteriores al freeze 0075 contra mysql y
     postgresql (verificado manualmente: la 0001 pasa en mysql y falla en
     PG con "ENUM type requires a name" — la red detecta). Además: guard
     de Enums sin nombre en modelos y tests de `ensure_ind_table`.
   - **Pendiente Codespace**: validar equivalencia cadena↔modelos con
     `alembic revision --autogenerate` (diff vacío) sobre MariaDB, y una
     corrida real de `init_db.py` en base vacía.
3. **Semántica** — HECHA (16-jul). Implementación:
   - `db_compat.order_desc_nulls_last(col)`: clave extra `(col IS NULL)
     ASC` — portable (MariaDB no soporta `NULLS LAST`), en MySQL no
     cambia el orden y en PG evita que los NULL encabecen el ranking.
     Aplicado en los dos ORDER BY de `strategy_service`.
   - `db_compat.ci_equals(col, valor)`: `LOWER(col) = lower(valor)` —
     replica en PG la case-insensitivity que la collation de MySQL daba
     gratis. Aplicado en: login (username), lookups/upserts por key de
     señal (ABM + import + scope de backfill), upsert de estrategia por
     nombre (import), y aliases de catálogo (`_resolve_alias`/
     `_upsert_alias`). La insensibilidad a ACENTOS de MySQL NO se
     replica en PG — asumido.
   - Consola SQL: rollback ante error SOLO en PG (transacción abortada —
     obligatorio); en MySQL el comportamiento histórico no se toca.
   - Pool configurable: `db_pool_size`/`db_max_overflow` en
     conf.properties (defaults 30/20, iguales a los hardcodeados).
   - **Decisión `sa.Float`: se mantiene sin precisión.** En PG las
     columnas serán `double precision` (8 bytes) vs FLOAT (4) de MySQL:
     no hay comparación de valores ENTRE motores en producción (cada
     base se compara consigo misma) y float8 coincide mejor con los
     doubles de Python. La paridad de fase 5 compara con tolerancia.
   - **Decisión aislamiento: sin cambio de código.** El productor del
     backfill lee `ind_*`/prices, que ninguna otra corrida modifica
     mientras corre (las corridas masivas son excluyentes a nivel app y
     el escritor de la propia corrida escribe OTRAS tablas). Con READ
     COMMITTED (default de PG) el resultado es el mismo; si la paridad
     de fase 5 muestra drift, fijar REPEATABLE READ en la sesión
     productora solo para PG.
4. **Entorno** — HECHA (16-jul). `DB_ENGINE` (mysql|postgres|both, default
   mysql) en `.devcontainer/setup.sh`, `scripts/codespace_setup.sh` y
   `devcontainer.json`; la rama PG instala PostgreSQL 16 desde PGDG, crea
   usuario/base con `psql`, corre `init_db.py` con `DATABASE_URL` y (modo
   postgres) la exporta en `~/.bashrc`; el modo `both` deja los dos motores
   lado a lado para la paridad de fase 5. `conf.properties.example`
   documenta `database_url` y el pool. CLAUDE.md actualizado (stack, flujo,
   convención db_compat). Drive-by: el check de admin de
   `codespace_setup.sh` consultaba la tabla `user` (no existe; es `users`).
5. **Paridad en Codespace** — herramienta lista, ejecución pendiente.
   La equivalencia cadena↔modelos quedó **VALIDADA** el 16-jul (`alembic
   check` limpio sobre la base MariaDB migrada del Codespace, tras alinear
   los índices de group_scores/indicator_definitions/market_event/prices/
   strategy_component en los modelos y filtrar las tablas dinámicas con
   `include_object` en env.py). Para la paridad de RESULTADOS:
   `scripts/compare_engines.py <url_mysql> <url_pg>` compara conteos por
   tabla, agregados por fecha con tolerancia (float4 de MySQL vs float8 de
   PG) y el ORDEN del ranking por estrategia en la última fecha común
   (empates por precisión = WARN, no error). Flujo: Codespace
   `DB_ENGINE=both` → importar el mismo dataset en ambos → "Recalcular
   completo" contra cada motor → correr el comparador. Medir además
   performance: lectura de series `ind_*` (riesgo de la PK clusterizada de
   InnoDB), rebuild, y `delete_by_ranges` bajo MVCC/autovacuum.
6. **Datos reales (si se decide):** copiar tablas fuente (users,
   definiciones, catálogo, prices, fundamentals, eventos) con pgloader o
   export/import; las derivadas (`ind_*`, `sig_*`, `strat_res_*`,
   group_scores) se regeneran con "Recalcular completo".

## Riesgos y mitigaciones

1. **Romper MySQL** → rama MySQL intacta + test de SQL byte-idéntico + suite
   antes de cada push + defaults siguen en MySQL en todos lados.
2. **Diferencias semánticas silenciosas** → fase 5 de paridad; no dar PG por
   bueno sin ella.
3. **Regresión de performance en PG** (heap vs PK clusterizada, autovacuum)
   → medir en fase 5 antes de decidir producción.
4. **Errores tragados** (`except: pass` + transacción abortada de PG) →
   auditados en fase 1; el resto en fase 3.
5. **Cobertura** → tests de compilación por dialecto + upserts ejecutados en
   sqlite; integración real por motor queda en el Codespace.

Mientras el soporte dual esté vigente, el código queda en el mínimo común
denominador: las ventajas PG-only (COPY, matviews, índices parciales,
particionado) se posponen o van detrás del mismo despacho.
