# Plan de corte a PostgreSQL-only — checklist ejecutable

> Plan del 22-jul-2026, derivado de `design_postgres_only.md` (el estudio) tras
> confirmar el usuario que **la instalación MariaDB ya no se usa: la única base
> es PostgreSQL en Railway**. Verificado archivo por archivo contra el código
> por una corrida multi-agente (inventario por área + dry-run de la suite +
> revisión adversarial de qué NO cortar).
>
> **ESTADO: etapa A HECHA (22-jul, commits d75d7d2 + el de esta revisión).**
> Etapa 0 pendiente (es consola en Railway, no código). Etapas B, C y D sin
> empezar; cada una es una sesión de trabajo con confirmación previa.
>
> La etapa A se revisó después con una corrida adversarial (4 revisores por
> dimensión + un escéptico por hallazgo, 30 hallazgos). Sobrevivieron 3 sobre
> el código nuevo —la unidad implícita en milisegundos de `lock_timeout`, el
> `options` de la URL pisado en silencio, y el error crudo de psycopg con el
> hash bcrypt en el modal— más uno **preexistente y grave** que la etapa A
> volvía alcanzable: ver "Hallazgo del flush ancho" abajo. Los cuatro quedaron
> arreglados; el resto se refutó.

## Orden y costo

| Etapa | Qué | Sesiones |
|---|---|---|
| **0** | Precondiciones en Railway, **sin tocar código** | ≈20 min de consola |
| **A** | Bugs vivos + código muerto | **0,5** |
| **B** | **El corte** (código, tests, config/entorno, tooling, docs) | **1,5–2** |
| **C** | Esquema PG-only (migraciones 0087/0088 + FKs) | **1–1,5** |
| **D** | Cosecha medida (COPY, CLUSTER, fillfactor, LATERAL, UNLOGGED) | 3–5, **fuera de este plan** |

**Por qué A antes que B.** El fix de `lock_timeout` no gana nada por esperar
(`app/database.py:6-13` no pasa `connect_args`, y el hook tiene que ser
condicional por dialecto igual, porque la suite es sqlite). Mientras no exista,
bajo PG con READ COMMITTED el `55P03` **no se emite nunca** y el retry de
`signal_backfill_range.py:600` y `fundamental_service.py:503,1360` está
**inerte**: el escritor bloqueado no falla, no reintenta, y la corrida se cuelga
con el heartbeat de `run_lock_service` latiendo — o sea **parece que está
corriendo**. MariaDB, con su `innodb_lock_wait_timeout` de 50s, era lo único que
hacía visible ese escenario: **el corte remueve el testigo del bug**.

**Por qué B antes que D.** El argumento "cosechá primero para no escribir
despacho que después tirás" **no aplica**: el seam de escritura genérico lo
exige **sqlite**, no MySQL (`tests/conftest.py:31-46` fuerza el stub y
`pytest_sessionstart` aborta si el dialecto no es sqlite). Lo único MySQL del
seam son 4 líneas (`db_compat.py:129,132-135`). B es un refactor
**demostrablemente inerte sobre el motor vivo** (las 10 ramas fuera de
`db_compat` son ramas no-tomadas bajo PG); D cambia lo que Railway ejecuta de
verdad y necesita medición. Además B mata la regla de paridad byte a byte
(`db_compat.py:7-9`), que es el impuesto que se paga en cada edición de camino
caliente — o sea, en toda la etapa D.

**Por qué C antes que D.** Las migraciones 0087/0088 son PG-only y la suite las
rechaza mientras `tests/test_bootstrap_portability.py:52` renderice contra
`mysql://`; ese parametrize se saca en B.

**Se CANCELA la fase 5 del plan dual** (gate de paridad con
`scripts/compare_engines.py`): sin segundo motor no hay nada que comparar, y el
comparador además estaba roto para tablas anchas (`_value_col:76-81` solo
reconoce columnas `value`/`score`).

---

## Regla que gobierna todo el checklist

**El test que fija una conducta MySQL se borra o se reescribe ANTES o EN EL
MISMO commit que el código que fija.** Con esa regla **ningún commit pasa por
rojo**. Los pares atómicos obligatorios están marcados con ⚠.

---

## ETAPA 0 — precondiciones (sin commit)

| # | Dónde | Qué | Si se saltea |
|---|---|---|---|
| 0.1 | Railway, shell del servicio web | `python scripts/init_db.py` → confirmar `alembic current` = **0086** (`0086_drop_app_setting.py`; el `Procfile` no aplica migraciones solo) | La 0087/0088 se apilan detrás: un fallo de la 0086 aborta el cambio de esquema nuevo en una ventana no planificada |
| 0.2 | `/admin/sql` (solo SELECT) | `SELECT lower(username), count(*), array_agg(id ORDER BY id) FROM users GROUP BY 1 HAVING count(*)>1;` | Si hay filas, el `CREATE UNIQUE INDEX` de la 0088 **aborta en producción** — y no sabés si el login ya viene resolviendo contra la cuenta equivocada |

---

## ETAPA A — bugs vivos + higiene (2 commits, suite verde)

| # | archivo:línea | Qué se hace | Si se saltea |
|---|---|---|---|
| A.1 | `app/database.py:6-13` | Listener `connect` (o `connect_args`) **condicional al dialecto**: `SET lock_timeout = '30s'` (+ opcional `statement_timeout`) solo si `postgresql`. ~10 líneas | La red de retry sigue inerte: escritura bloqueada = cuelgue silencioso en Railway, sin excepción en el log |
| A.2 | `app/__init__.py:151-152` | `.order_by(User.id).first()` en el lookup del login | Login no determinista mientras exista un par `Admin`/`admin` (el `unique=True` de `app/models/user.py:14` es case-sensitive en PG) |
| A.3 | `app/services/reference_service.py:343-350` y `:366` | `create_user`/`update_user` validan unicidad con `db_compat.ci_equals` y tiran `ValueError` en castellano | Sin esto, cuando llegue la 0088 el usuario ve el texto crudo de psycopg en el modal (`reference_callbacks.py:957-958`) |
| A.4 | `scripts/init_db.py:93` | Buscar el admin inicial con `ci_equals`, no `User.username == Config.ADMIN_USERNAME` | Tras la 0088, `init_db` sobre una base con `Admin` intenta crear un duplicado y **aborta el bootstrap** |
| A.5 ⚠ | `app/services/db_compat.py:171-189` + `tests/test_db_compat.py:271-285` **mismo commit** | Borrar `set_bulk_load_checks` y su único test (cero call sites de producción; ya declarada muerta en `docs/manual/1050:227`). Retitular el encabezado `tests/test_db_compat.py:256`; **NO borrar** la clase `_Sess` (`:258-269`), la usa `test_wipe_table_truncate_vs_delete` | Borrar la función sin el test = `AttributeError`, suite roja |
| A.6 | `app/services/run_lock_service.py:67` | Borrar la entrada `"1146"` de `_MISSING_TABLE_MARKERS` | Falso positivo latente: el match es por substring sobre `str(exc).lower()` (`:71-73`) y `_note_error` latchea `_unavailable=True` para **todo el proceso** |
| A.7 | `alembic/env.py:26-27` | El comentario apunta a `tests/test_migration_portability.py`, **que no existe**; el real es `tests/test_bootstrap_portability.py` | Única pista de dónde se verifica una migración nueva, colgada |

### Hallazgo del flush ancho (salió de la revisión de la etapa A)

En tablas anchas el worker de indicadores no escribe por código: acumula en un
buffer y lo vuelca una sola vez al final del lote. Si ese volcado agotaba los
reintentos, el buffer se descartaba —ninguna fila del lote llegaba a la base, de
ningún código— **pero los resultados por código igual subían al padre**, que
consolidaba `ind_asset_meta` con checksums y estadísticas calculados en memoria.
El delta siguiente veía los metadatos coincidentes, tomaba el camino rápido
tail-mode y **el hueco no se rellenaba nunca**: pérdida de datos silenciosa y
permanente, contra la invariante que el propio comentario de la consolidación
documenta.

Es preexistente, pero la etapa A lo convirtió en el modo de falla normal: antes,
sin `lock_timeout`, el flush bloqueado colgaba para siempre y la consolidación
nunca se alcanzaba; ahora falla, reintenta y sigue. Arreglado descartando
`per_code`/`inserted` del lote cuando el volcado no se completa, con dos tests
(camino de error y camino feliz).

---

## ETAPA B — el corte (7-8 commits, todos verdes)

### B1 · Retry: fixtures primero, código después (2 commits, el orden importa)

- **B1.1** — `tests/test_lock_retry_and_purge.py:7-23`,
  `tests/test_fundamental_ratios.py:29-50`,
  `tests/test_indicator_batching.py:846-850` (+ call sites `:885,:935,:983`),
  `tests/test_fundamental_batching.py:252-256` (+ `:279,:311`): los fixtures
  pasan de `orig.args=(errno,)` a `orig.sqlstate` — `1213→"40P01"`,
  `1205→"55P03"`, `1146/1062→"23505"`. **Ningún test se borra.**
  *Si se saltea:* B1.2 pone **9 tests en rojo**. Y si en vez de reescribirlos
  los borrás, te quedás **sin ninguna cobertura** del retry/backoff/de-dup de
  progreso de los workers — que es lo que estos tests realmente prueban; el
  errno era solo el fixture.
- **B1.2** ⚠ — `app/services/db_compat.py:145-148,164-166` +
  `tests/test_db_compat.py:225-228` **mismo commit**: borrar
  `_MYSQL_RETRYABLE_ERRNOS` y el bloque `args`; renombrar
  `_PG_RETRYABLE_SQLSTATES` → `_RETRYABLE_SQLSTATES`. El test se **da vuelta**:
  `test_retry_ignora_errnos_de_mysql` asserta que `args=(1205,)` **ya no**
  reintenta.

### B2 · Tests de paridad byte a byte (1 commit, solo borra tests → verde por construcción)

- `tests/test_db_compat.py:49-118` — borrar los 5 `test_upsert_mysql_*` (70
  líneas). El equivalente vivo es
  `test_upsert_dedup_lote_clave_repetida_ultima_gana_en_sqlite` (`:374-390`),
  **que se queda**.
- `:142-172` — borrar los 3 `test_upsert_sql_mysql_*_byte_identico`; retitular
  el encabezado `:140-141`.
- `:195-216` — sacar la línea MYSQL de `test_quote_ident_por_dialecto`,
  `test_placeholder_por_driver` y `test_supports_truncate`;
  `test_is_mysql_is_postgres` → `test_is_postgres`. Borrar la constante `MYSQL`
  (`:32`), el import `mysql_insert` (`:20`) y `mysql` de `:19`. Docstring `:1-14`.
- `:287-322` — sacar `mysql.dialect()` de los dos loops.

### B3 · `is_mysql` y sus call sites ⚠ UN SOLO COMMIT, indivisible

| archivo:línea | Qué |
|---|---|
| `app/services/signal_backfill_range.py:636` | `use_async = db_compat.is_postgres(s)`. **No** poner `True` ni `not is_sqlite`: sqlite tiene que seguir sincrónico. Comentarios `:626`, `:646-650` |
| `app/services/asset_service.py:93-123` | Borrar la rama MySQL entera de `purge_assets`; `:124` pasa de `elif` a `if`; el `else` sqlite (`:147-150`) **se queda**. Docstring `:69-79`. Revisar si `_DELETE_BATCH` queda huérfano |
| `app/services/maintenance_service.py:46-51, 80-83, 158-163, 177-181` | Borrar las 4 ramas MySQL. **Conservar obligatoriamente** `return 0` (`:52`), `return []` (`:164`) y `else: total = 0` (`:182-183`) — `tests/test_maintenance_size_report.py` los exige |
| `app/services/db_compat.py:91-118` + import `:16` | `upsert()`: borrar el early-return MySQL. **Agregar un `raise ValueError` para dialecto desconocido** — hoy `:109` haría caer un bind desconocido al camino sqlite en silencio, justo lo que la regla del módulo prohíbe |
| `app/services/db_compat.py:121-138` | `upsert_sql()`: borrar la rama MySQL; `:129` → `tbl = quote_ident(b, table)`. **Borrar el parámetro `quote_table`** de la firma y los dos `quote_table=True` de `technical_service.py:775,810` |
| `app/services/db_compat.py:240-261` | `approx_table_rows()`: borrar la rama MySQL (`:246-251`). El `if is_postgres` **queda** (distingue PG de sqlite) |
| `app/services/db_compat.py:216-219` | `supports_truncate()` → `return is_postgres(bind)`. **No inline-arla**: tiene call site externo en `signal_backfill_range.py:456` |
| `app/services/db_compat.py:31-32` | Borrar `is_mysql` — **último de la lista** |
| `app/pages/admin_sql.py:9-13,22-27` | Borrar `_MYSQL_DEFAULT_QUERY` y `_default_query()`; usar la constante PG directo en `:44` |
| `app/callbacks/admin_sql_callbacks.py:163-176` | Rollback incondicional; borrar los imports locales `:169-170` (inofensivo en sqlite: rollback sin transacción abortada es no-op) |

*Si se saltea alguno:* borrar `is_mysql` con un call site vivo da `AttributeError`
**en runtime, no en import** — pytest no lo agarra si esa ruta no se ejercita
(`purge_assets`, `_bulk_insert` del backfill: los caminos más caros).

### B4 · Config y entorno (1 commit)

| archivo:línea | Qué | Si se saltea |
|---|---|---|
| `app/config.py:57-61` | Default → `postgresql+psycopg://{USER}:{PASS}@{HOST}:{PORT}/{NAME}`, **sin** `?charset=utf8mb4`. **No tocar** `_normalize_db_url` (`:15-29`): la URL de Railway la necesita | Cualquier entorno sin `DATABASE_URL` levanta con `ModuleNotFoundError: MySQLdb`. **Único ítem que puede dejar la app sin arrancar** |
| `app/config.py:49-53` | `db_port` 3306→**5432**, `db_user` root→**postgres**, `db_password` ""→**postgres** (coincide con `.devcontainer/setup.sh:76`) | Aun con el esquema corregido, apunta a 3306/root sin password |
| `requirements.txt:13` | Borrar `mysqlclient>=2.2.0` | Se sigue compilando un driver que nadie importa |
| `.devcontainer/devcontainer.json:5-14` | Borrar `"DB_ENGINE": "mysql"`; puerto 5432, user/pass postgres; agregar `DATABASE_URL` explícita | **La trampa**: el valor efectivo del entorno lo inyecta este archivo, no los `.sh`. Un Codespace recreado sigue apuntando a MySQL |
| `.devcontainer/setup.sh:7-14,18-51,81-92,101-125` | Borrar `install_mysql()`, el default `DB_ENGINE`, el `case`, **y el bloque `:88-92`** (apt de `default-libmysqlclient-dev`, que existe solo por `mysqlclient`). Conservar `PG_URL` (`:16`) e `install_postgres` (`:53-79`) | El postCreate sigue instalando MariaDB por default y compilando libs para nada |
| `scripts/codespace_setup.sh:16,20-70,109-128,154-159,177-181,196,202-205` | Borrar `setup_mysql()`, `check_mysql_schema()`, `DB_ENGINE`, los dos `case` | El **validador** del entorno falla con exit 1 en un Codespace PG-only: el falso negativo más caro |
| `conf.properties.example:4-10` | 5432/postgres/postgres; reescribir el comentario del motor | Plantilla que induce el modo de falla que `config.py` acaba de cerrar |
| `tests/test_config_db_url.py:27-29` | Borrar `test_mysql_no_se_toca` | — |

*(`conf.properties` local está en `.gitignore`: actualizalo a mano, no entra en
el commit.)*

### B5 · Tooling (1 commit) ⚠ atómico

- `scripts/compare_engines.py` **+** `tests/test_compare_engines.py` — borrar
  **juntos** (212 + 115 líneas). Si borrás solo el script, el
  `from scripts import compare_engines` revienta en **colección**: la suite
  entera no corre.
- `scripts/init_db.py:57,64-69,115` — borrar `--via-migrations` (declarado "solo
  MySQL" en su propio docstring; contra PG dispara el replay de la cadena
  congelada y falla a mitad). Conservar `_database_is_empty` y las dos ramas de
  `create_schema`.
- `scripts/measure_indicator_storage.py:46-47,80-81,84-102,109-118,141-146` — 5
  sitios, dejar solo el camino PG.
- `tests/test_bootstrap_portability.py:52` — parametrize → `["postgresql://"]`;
  docstring `:1-16`. **`FROZEN_HEAD = "0075"` (`:36`) NO se mueve y
  `alembic/versions/0001..0075` NO se tocan.**
  *Se descarta* conservar el render `mysql://` como oráculo de portabilidad: la
  etapa C trae DDL PG-only (`ADD CONSTRAINT … PRIMARY KEY USING INDEX`, índice
  funcional) que MariaDB no compila, así que dejarlo reimpone el mínimo común
  denominador justo en la capa que el corte viene a liberar. El test no pierde
  su razón de ser: sigue atrapando `CompileError`, `sa.Enum` sin nombre y tipos
  no soportados, offline y sin driver.

### B6 · Manual ⚠ atómico (1 commit)

- `docs/manual/1060-soporte-dual-de-base-de-datos.md` — **reescribir
  conservando el slug**, `order: 1060`, `chapter` y `roles: admin`. Título tipo
  *"Por qué la base es PostgreSQL (y qué quedó del soporte dual)"*.
  **No borrarlo**: 8 capítulos lo enlazan (`1000:197`, `1010:91`, `1020:43`,
  `1040:168`, `1050:81`, `1080:71`, `1090:158`, `1095:111`) y
  `tests/test_manual_coverage.py:118-129` valida esos enlaces → borrarlo sin
  editar los 8 **rompe pytest**. Conservando el slug, los 8 se editan por prosa,
  no por obligación.
  - *Se va:* la tabla de 12 funciones por motor (`:24-37`), los dos invariantes
    (`:53-72`), `set_bulk_load_checks` (`:32,94-99,221-226`), `DB_ENGINE`
    (`:149-151`), fases 5/6 (`:204-219`), el cierre "mínimo común denominador"
    (`:228-231`).
  - *Se queda reescrito:* presupuesto de conexiones (`:142-160`), bloat MVCC
    (`:121-134`), transacción envenenada (`:94-99`), CardinalityViolation/Ámbito
    (`:86-92`), `ci_equals` **sigue existiendo** porque sqlite es el motor de la
    suite (`:109-119`), freeze 0075 (`:162-202`).
- Mismo commit, solo prosa (ninguno rompe tests): `1000:78,196-197` ·
  `1010:88-91,95,186` (recontar deps **después** de sacar `mysqlclient`) ·
  **`1020:63-64`** — el párrafo más delicado: *"el DDL de MySQL no es
  transaccional"* es la premisa de la que cuelgan tres decisiones (nombrar por
  ID, dejar el lado benigno, `reconcile_dynamic_tables`), y bajo PG es **falsa**;
  reencuadrar sin borrar las decisiones · `1040:139,165-170` (dos ramas, no
  tres; solo `VACUUM FULL`) · **`1050`** (el punto crítico es `:145-148`: bajo PG
  con READ COMMITTED **y ya con `lock_timeout` de A.1** la red de retry sí se
  dispara; si A.1 no se hizo, documentarla como inerte) · `1080:69-71` (+ sumar
  el riesgo de `users.username`) · `1090:9-10,95,154-160,164,179-180` ·
  `1095:92,109-111,292` (quedan **cuatro** variantes del oráculo, no cinco; el
  hueco de portabilidad se invierte: ahora sqlite tolera lo que PG no) ·
  `1099:76-82,179` · `650-centro-de-datos.md:154-155`.

### B7 · CLAUDE.md, PROMPT.md y memoria (1 commit)

`CLAUDE.md:21,23-27,35,38-46,81-84,127,131,161-163` · `PROMPT.md:30-32`
(**nota de encabezado**, no reescribir el cuerpo: es el brief histórico y
explica por qué el código nació con forma MySQL) ·
`docs/notes/guide_deploy.md:19,45,51-59,157-161,205` ·
`docs/notes/project_overview.md:9-12,24` · `design_postgresql_dual.md` (bloque
SUPERSEDED al tope, **no borrar**) · `design_postgres_only.md` ·
`project_postgres_only_estudio.md` · `project_postgresql_migracion.md`
(migración cerrada, fases 5/6 canceladas) · `MEMORY.md` · **borrar
`feedback_mariadb.md`** (única pieza redactada como orden imperativa a Claude
Code) · `project_testing.md:21` · **NO tocar `project_pendientes.md`** (es un log
histórico: blindarlo de cualquier grep-and-replace de "MariaDB").

⚠️ El hook **pre-push** vigila `MEMORY.md`, `project_*.md` y `feedback_*.md`
contra la memoria de Claude Code: sincronizar la memoria en el mismo movimiento
o el push se traba.

### B8 · Higiene de comentarios (commit aparte, opcional)

`technical_service.py:577,651,1410,1491,1596,1795,2090,2699`,
`cleanup_service.py:70,125-139`, `signal_store.py:10-13,144`,
`indicator_store.py:26`, `verification_service.py:71`,
`write_stats_service.py:17`, `synthetic_service.py:457`,
`app/__init__.py:149-152`, `wsgi.py:1`. Cero riesgo, pero `:1491` y `:2090`
dejan de ser argumentos válidos bajo MVCC.

---

## ETAPA C — esquema PG-only (2-3 commits; requieren Codespace/Railway)

| # | archivo:línea | Qué | Si se saltea |
|---|---|---|---|
| C.1 | `app/models/price.py:19,33` + migración **0087** | Dropear `Price.id`, promover `(asset_id,date)` a PK: `DROP CONSTRAINT prices_pkey` → `ADD CONSTRAINT prices_pkey PRIMARY KEY USING INDEX uq_asset_date` → `DROP COLUMN id`. **No mueve datos**: reusa el índice y el `DROP COLUMN` de PG es metadata-only. Verificado que `Price.id` no se lee en ningún lado | Se mantiene en cada insert un btree de ~50M entradas (al objetivo) que nadie consulta |
| C.2 | `tests/test_db_compat.py:128-137` — **mismo commit que C.1** | Renombrar `test_upsert_pg_prices_usa_unique_no_la_pk_autoincremental` y reescribir el comentario `:129-131`: tras la 0087 el assert pasa **por la rama de PK** | Test verde documentando un esquema inexistente |
| C.3 | `app/services/db_compat.py:57-71` | **Solo el docstring.** `fundamental_quarterly` y `group_scores` tienen la **misma forma** que `prices` (UNIQUE + `id` sustituto): hoy no pasan por `upsert()`, pero el día que lo hagan, sin el fallback emiten `ON CONFLICT (id)` con `id` ausente. **El fallback se queda**; cambia la justificación (dejar de citar `prices.id`) | Si alguien lo "simplifica" creyendo que emulaba `ON DUPLICATE KEY`, rompe cualquier upsert futuro sobre esas tablas |
| C.4 | `app/models/user.py:14` + migración **0088** + `docs/manual/800-usuarios.md:71-73` y `110-primeros-pasos.md:16-17` | `Index('uq_users_username_lower', func.lower(username), unique=True)`. Preferir índice funcional sobre `citext` (no exige `CREATE EXTENSION`). Dejar el `unique=True` de la columna. **Depende de 0.2** | Bug de autenticación vivo; y el manual sigue prometiendo en `110:16` algo que la base no garantiza |
| C.5 | `app/models/indicator_store.py:219-221` + migración | Dropear las FK `asset_id→assets` de las 5 tablas anchas. Seguro: la rama PG de `purge_assets` (`asset_service.py:124-146`) borra las dinámicas **explícitamente**, no depende del CASCADE. **Antes, un bench**: el ahorro del trigger RI no está medido. `alembic check` **no lo detecta** (`env.py:38` excluye las dinámicas): migración a mano | Se paga un trigger RI por fila en decenas de millones de inserts, mientras `sig_*`/`strat_res_*` ya decidió no pagarlo. **Riesgo:** la rama PG de `purge_assets` **no está cubierta por la suite** → escribir primero un test que ejercite su lista de tablas |

**Fuera de alcance, explícito:** `float4` en las anchas, particionado de
`group_scores`/`group_signal_value`, y `float4` en `prices` (irreversible: los
precios no son regenerables sin redescarga). Todo eso es etapa D, con medición
previa.

---

## Qué NO se toca

1. **El seam PG↔sqlite entero.** No es residuo del dual: es lo único que hace
   ejecutable este proyecto sin base. Verificado: esta PC **no tiene ningún
   driver** (`import app.database` sin `DATABASE_URL` →
   `ModuleNotFoundError: MySQLdb`; `psycopg` tampoco está). Sobreviven sin
   cambios: `_bind`, `_table_of`, `quote_ident` (`:39-42` — el
   `identifier_preparer` escapa comillas internas, un f-string no),
   **`placeholder`** (`:45-49` — `%s` vs `?`, gobierna todos los
   `exec_driver_sql` calientes), `wipe_table`/`supports_truncate` (sqlite no
   tiene TRUNCATE; 11 call sites), `list_tables_by_prefix` (nunca fue dual: es
   lo que *reemplazó* al SQL MySQL), `table_write_stats`, `is_postgres`.
2. **`is_postgres` no se vuelve trivial ni se cambia por `not is_sqlite`.** Es
   la función que hace cumplir "PG nunca cae al camino de sqlite" — la única
   asimetría que queda, y ahora la más importante.
3. **`_dedupe_last` (`:74-88`) intacta.** Su docstring dice "semántica de MySQL
   ON DUPLICATE KEY" y por eso **se lee como legacy sin serlo**: PG y sqlite
   abortan con CardinalityViolation. Fue un bug real de producción (`946fc6d`,
   fuente Ámbito). **Reescribir el docstring antes de que alguien la borre**; el
   corte además le saca el motor tolerante como plan B, o sea vale más.
4. **`_conflict_cols` con su fallback** — ver C.3.
5. **`order_desc_nulls_last` (`:192-200`) igual.** `NULLS LAST` nativo
   compilaría, pero cambiaría el SQL de los dos call sites del ranking
   transversal (`strategy_service.py:465,516`) y dependería de la versión de
   sqlite de cada máquina. Ganancia: una línea.
6. **`ci_equals` (`:203-213`) y sus 11 call sites.** Tras la 0088,
   `LOWER(username)` es justo lo que usa el índice funcional: deja de ser el
   "costo sin índice" que era.
7. **`tests/test_dual_semantics_flows.py`** (3 tests): es la **única cobertura
   ejecutable** de ON CONFLICT + NULLS LAST + case-insensitive contra el stub.
   Vale más post-corte. El rename es opcional y no se mezcla con el corte.
8. **Los 5 tests de `test_db_compat.py` que ejecutan de verdad contra sqlite**
   (`:362,:374,:393,:401,:416`).
9. **`alembic/versions/0001..0075`** y `FROZEN_HEAD`: ninguna base los
   reejecuta, pero borrarlos rompe el linaje de `down_revision` y
   `command.upgrade(cfg, "0075:head")`. Tampoco `0078:52`, `0079:80`, `0081:48`,
   `0082:40` (sus `downgrade()` son la única red de rollback del refactor
   ancho). Ojo: `0078:68` y `0081:64` **no son ramas MySQL** — son
   `paramstyle == "qmark"`, o sea **sqlite**.
10. **La convención `delete_by_ranges` (`db_utils.py:4-11`).** Está justificada
    por escrito con razones de InnoDB, así que post-corte se lee como folklore
    borrable. En PG las razones son otras (transacción larga → bloat +
    autovacuum bloqueado; `DELETE … LIMIT` ni existe) pero el resultado es igual
    de malo. **Falta re-medir sobre la topología actual antes de tocarla.**
11. **`ensure_ind_table` (`indicator_store.py:190-191`)** con su FK: está
    dormido (los 36 códigos con historia están todos en `_WIDE`) pero es el
    camino per-código de la suite.
12. **`Procfile`**: verificado, cero referencias al motor. El corte no toca el
    despliegue.

---

## Riesgos

| # | Riesgo | Mitigación |
|---|---|---|
| **1** | **`signal_backfill_range.py:636` mal editado.** Es la única línea del repo donde un chequeo de dialecto elige una **arquitectura de concurrencia** (thread escritor + pool de 3 lectores), no un string de SQL. La suite es **estructuralmente ciega** ahí: los ~892 casos corren siempre la rama sincrónica de sqlite. Si queda `True` o `not is_sqlite`, **la suite pasa verde y el backfill se rompe en Railway** | `use_async = db_compat.is_postgres(s)`, literal. Verificación obligatoria en Codespace: un backfill de rango real con el panel de progreso, **antes** de que el corte llegue a Railway |
| **2** | **Cuelgue silencioso por retry inerte** (bug preexistente que el corte agrava). `_flush_once` no vuelve → el escritor no marca `_werrors` → el productor se traba en `_wq.put` con cola `maxsize=1`. Y el heartbeat de `run_lock_service` sigue latiendo: el lock nunca se ve obsoleto y el botón del Centro de Datos queda trabado | **A.1 antes que B**, y B1.1 reescribe los tests en vez de borrarlos, así la maquinaria de reintento conserva cobertura justo cuando pasa a ser el único plan |
| **3** | **Irreversible: se pierden el motor de fallback y la única línea de base de performance.** `project_ind_wide_tables.md:49-52` registra el único encuentro medido PG vs MySQL en el camino caliente de indicadores — **y lo ganó MySQL**. Post-corte, toda medición es autorreferencial | Aceptado por decisión del usuario. Mitigación parcial: **no borrar** `design_postgresql_dual.md` ni `project_ind_wide_tables.md`, que son el registro de esa medición. Y **no existe procedimiento de backup versionado** (`pg_dump` no aparece en el repo): vale la pena sumarlo a `guide_deploy.md` |
| **4** | **`app/config.py:57-61` + `requirements.txt:13` desfasados** = app que no arranca con `ModuleNotFoundError` (error de import, no de configuración) en cualquier entorno sin `DATABASE_URL` | Los dos en el **mismo commit** (B4), junto con `devcontainer.json` — que es el que inyecta el valor efectivo del Codespace |
| **5** | **Railway sufre lo que la suite no ve.** La suite nunca ejecuta: la rama PG de `purge_assets`, el escritor asíncrono, `_use_process_pool` con procesos (`technical_service.py:1413`), ni ningún `TRUNCATE`. Además `conftest.py:46` fuerza `USE_WIDE_IND_TABLES=0`, o sea corre el camino **per-código**, que en producción está muerto | Ninguna etapa se cierra con "pytest verde": ver Verificación. Y la 0088 puede abortar en producción si 0.2 no se corrió antes |

**Puntos de atomicidad que, si se rompen, dejan la suite roja:** B1.2 (código
sin fixtures), B3 (`is_mysql` sin sus 10 call sites → `AttributeError` en import
→ **toda** la suite), B5 (`compare_engines.py` sin su test → falla la
**colección**), B6 (borrar el 1060 sin editar los 8 enlaces).

---

## Verificación

Local: solo `venv\Scripts\python.exe -m pytest` (813 funciones / ~892 casos),
verde al final de **cada** commit.

| Etapa | Codespace | Railway |
|---|---|---|
| **0** | — | `python scripts/init_db.py` → `alembic current` = 0086; query de duplicados de `users` por `/admin/sql` |
| **A** | Levantar la app: `SHOW lock_timeout;` devuelve `30s`. Login con el usuario en otro caso (`ADMIN` vs `admin`). Crear un usuario que difiera solo en mayúsculas → mensaje en castellano, **modal abierto** | Reiniciar y repetir `SHOW lock_timeout;`. Mirar el log de una corrida nocturna: sin reintentos nuevos ni cuelgues |
| **B** | **Rebuild del devcontainer desde cero** (única forma de probar `devcontainer.json` + `setup.sh`), después `bash scripts/codespace_setup.sh` → exit 0. Verificar que el postCreate **no** instala `default-libmysqlclient-dev`. Luego: boot de la app, `/manual` renderiza el 1060 reescrito y los 8 enlaces resuelven, `/admin/sql` abre con la query PG por default, `/admin/data-center` muestra tamaños y el reporte de escrituras, **borrar un activo de prueba** (rama PG de `purge_assets`) y **un backfill de rango real** (riesgo #1) | `git pull` + reinicio. Smoke: login, `/screener`, `/admin/data-center` |
| **C** | 0087: aplicar y confirmar `\d prices` → PK `(asset_id,date)` sin columna `id`; después **un delta de precios** y **un rebuild de un sintético**. 0088: aplicar y correr **`alembic check`** (alembic no refleja bien los índices por expresión; el repo ya tuvo que alinear índices por esto, `3970763`). C.5: bench antes/después según el método de 4 pasos, y borrar un activo con tablas anchas pobladas | Ventana corta y anunciada: `alembic upgrade head` desde la shell del servicio (el `Procfile` no lo hace solo). Post-0087 medir con `scripts/measure_indicator_storage.py --raw` contra el presupuesto de 500 MB. **Nunca perfilar en Railway** |

**Al cerrar todo:** recontar los tests con la suite ya podada y recién ahí
actualizar `CLAUDE.md` y `project_testing.md` (hoy dicen ~740 y 886; el real es
813 funciones). Sincronizar la memoria antes del push o el hook `pre-push` lo
frena.
