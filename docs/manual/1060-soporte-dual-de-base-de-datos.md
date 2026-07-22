---
slug: soporte-dual-de-base-de-datos
title: Soportar dos motores de base de datos
chapter: Anexo tecnico
order: 1060
roles: admin
---

La aplicación corre indistintamente contra MySQL/MariaDB o contra PostgreSQL, con
el mismo código. El motor lo decide `DATABASE_URL` y nada más. El trabajo se hizo
sobre una app viva ya en producción con MySQL, así que la restricción no era "que
ande en los dos" sino **"que ande en PostgreSQL sin cambiar un byte de lo que
corre en MySQL"**.

El estudio previo midió el acoplamiento —unos 14 archivos de `app/` y `scripts/`,
y unas 20 de las 75 migraciones de entonces— y la factibilidad se apoyó en que
estaba **concentrado**. De ahí la decisión central: una sola frontera.

## Una única frontera: `db_compat`

Todo el SQL con sabor a motor se construye en `app/services/db_compat.py` — 261
líneas, 18 funciones, consumidas hoy por 18 módulos de `app/`.

| Función | Qué diferencia resuelve |
|---|---|
| `is_mysql` / `is_postgres` | Detección de dialecto; aceptan engine, connection o Session |
| `quote_ident` | Backticks en MySQL, comillas dobles en PG/sqlite |
| `placeholder` | `%s` del DBAPI vs `?` de sqlite |
| `upsert` | `ON DUPLICATE KEY UPDATE` ↔ `ON CONFLICT DO UPDATE` |
| `upsert_sql` | La misma variante como string crudo, para `executemany` |
| `is_retryable_lock_error` | Errno de InnoDB (1205, 1213) ↔ SQLSTATE de PG (40001, 40P01, 55P03) |
| `order_desc_nulls_last` | Posición de los NULL en un `ORDER BY DESC` |
| `ci_equals` | Igualdad sin distinguir mayúsculas |
| `supports_truncate` / `wipe_table` | `TRUNCATE` donde existe, `DELETE FROM` en sqlite |
| `list_tables_by_prefix` | Reemplaza los `SELECT` a `information_schema` con `DATABASE()` |
| `approx_table_rows` | `information_schema` ↔ `pg_class.reltuples` ↔ `COUNT(*)` |

La regla está en el docstring del módulo: **los servicios no llevan ramas por
dialecto propias**. La disciplina importa más que la elegancia. Sin un único punto
de entrada, cada servicio inventaría su rama y una regresión en MySQL pasaría
inadvertida; con la frontera única, un solo archivo de tests fija la paridad de
todo el SQL de motor.

Lo centralizado es la **detección** de dialecto y la **construcción** de SQL, no
la prohibición de tener dos estrategias. Cuando el algoritmo entero difiere, la
rama vive en el servicio y solo el predicado sale de `db_compat`: en
`purge_assets` (`app/services/asset_service.py`) MySQL borra con `DELETE ... LIMIT`
por lotes y PG sin `LIMIT` —no existe en su `DELETE`— y sin lotes, con commit por
tabla, porque bajo MVCC un `DELETE` no bloquea lectores. Meterlo dentro de
`db_compat` habría metido lógica de negocio en la capa de compatibilidad.

## Los dos invariantes

**La rama MySQL emite SQL byte-idéntico al histórico.** Son 29 tests en
`tests/test_db_compat.py` que compilan la construcción vieja y comparan el string
resultante contra el que produce `db_compat.upsert`: romperlos es cambiar lo que
corre en producción. El invariante prohíbe hasta las mejoras cosméticas — la rama
PG deduplica los lotes y la MySQL no, y hay un test que cuenta las tres filas del
`VALUES` para que nadie lo "empareje".

**PostgreSQL nunca cae al camino de sqlite.** Los despachos que ya existían
distinguían "MySQL vs el resto", y dejar que PG heredara ese resto era lo barato.
Habría roto tres cosas en silencio: `purge_assets` dejaría historia huérfana en
las tablas dinámicas (no tienen FK a `assets`), el escritor asíncrono del backfill
se desactivaría, y se usaría `DELETE FROM` en vez de `TRUNCATE`. Por eso el código
habilita por afirmación y no por descarte: en `signal_backfill_range` el escritor
asíncrono se activa con `is_mysql(s) or is_postgres(s)`.

> sqlite no es un tercer motor soportado: es un stub para que la suite corra sin
> drivers. Escribir una rama nueva pensando "PG y sqlite se parecen" es el error
> que el módulo prohíbe.

## Las sutilezas, que son lo caro

Lo que rompe con error de sintaxis —backticks, `VALUES()`, `DATABASE()`— es lo
fácil: se descubre al primer intento. Lo caro son las diferencias que **devuelven
un resultado distinto sin quejarse**.

**Cardinalidad del conflicto.** MySQL dispara `ON DUPLICATE KEY` con cualquier
clave única; PG exige nombrar las columnas. `_conflict_cols` usa la PK si los
valores la traen completa y si no, la primera `UniqueConstraint` cubierta. El caso
real: `prices.id` es autoincremental y no viene en los valores, así que el
`ON CONFLICT` tiene que apuntar al `UNIQUE(asset_id, date)`.

**Filas repetidas en un statement.** MySQL las tolera (gana la última); PG y
sqlite abortan con `CardinalityViolation`. Por eso la rama PG deduplica con
`_dedupe_last`, preservando el orden de primera aparición.

> Esa tolerancia de MySQL tapaba un bug de datos real: la fuente Ámbito
> (RIESGO_PAIS_AR) devolvía fechas duplicadas desde hacía tiempo y nadie lo sabía,
> hasta que PostgreSQL lo hizo explotar.

**Transacción envenenada.** En PostgreSQL un statement fallido aborta la
transacción entera. De ahí la regla de decidir por motor **antes** de emitir el
SQL en vez de intentar y perdonar: cuando el `try/except` captura la excepción,
la conexión ya está inutilizable hasta el rollback. La misma regla obligó a que
la consola SQL de administración haga rollback ante error **solo** en
PostgreSQL.

**Orden de los NULL.** MySQL los pone al final en `DESC`; PostgreSQL primero. Sin
el fix, en PG un activo con score NULL encabezaría el ranking: el output de todo
el pipeline invertido en su primera fila, sin ningún error visible. Y la cláusula
estándar `NULLS LAST` no sirve, porque **MariaDB no la soporta** — arreglar el
motor nuevo rompería el que ya andaba. El fix portable es una clave de orden
extra, `(col IS NULL) ASC`: funciona en los tres motores porque false/0 < true/1.
Está en los dos `ORDER BY` del ranking de `app/services/strategy_service.py`.

**Case-sensitivity.** La collation `utf8mb4_*_ci` daba igualdad insensible a
mayúsculas gratis; en PG el `=` es case-sensitive. `ci_equals` emite
`LOWER(col) = lower(valor)` y está en 11 call sites: login, keys de señal, nombre
de estrategia en el import, aliases de catálogo, ticker de activo y código ISO de
país. Sin eso, en PG el login con
`Admin` no encontraría al usuario `admin`, y `Technology` y `technology` serían
aliases distintos — duplicados silenciosos en vez de match.

> Dos límites asumidos de `ci_equals`: no replica la insensibilidad a **acentos**
> de MySQL (en PG `á` != `a`), y como emite `LOWER(col)` impide usar el índice.
> Solo para lookups puntuales sobre tablas chicas.

## El soporte dual no termina en el SQL

El mismo `INSERT`, correcto en los dos motores, puede tener un costo de
almacenamiento radicalmente distinto. Escribir una tabla ancha columna por columna
deja hasta N−1 tuplas muertas por fila bajo MVCC — con 14 columnas en `ind_daily`,
hasta 13. Se suponía que el bloat del delta era chico y lo recuperaba autovacuum;
medido en Postgres real resultó **51% de tuplas muertas en `ind_daily`: 1,08M
muertas contra 1,03M vivas, con el autovacuum corriendo y sin dar abasto**. La
suposición era cierta en rebuild y falsa en el backfill de activos nuevos, que
corre como delta pero escribe la serie histórica entera. La corrección fue
bufferizar siempre las escrituras anchas. De ahí salió además
`app/services/maintenance_service.py`, que compacta con `VACUUM FULL` (PG) u
`OPTIMIZE TABLE` (MySQL), sobre conexión en `AUTOCOMMIT` porque PG no admite
`VACUUM FULL` dentro de una transacción.

A veces la diferencia no está ni en el SQL ni en el algoritmo, sino en si una
condición devuelve NULL o levanta excepción: si una tabla dinámica desaparece
mientras se compacta, `pg_total_relation_size()` lanza `undefined_table` y abortaba
la corrida entera, mientras que en MySQL `information_schema` devolvía NULL y el
COALESCE lo volvía 0.

## Elección del motor y presupuesto de conexiones

`app/config.py` resuelve `DATABASE_URL` con prioridad entorno > `conf.properties` >
default construido con los `db_*` (que apunta a MySQL). `_normalize_db_url`
reescribe `postgres://` y `postgresql://` a `postgresql+psycopg://`: el proyecto
usa psycopg3 y SQLAlchemy sin el prefijo busca psycopg2, que no está instalado.
Evita un fallo de arranque imposible de diagnosticar desde el panel de un PaaS,
que entrega la cadena sin driver. En desarrollo el motor se elige con `DB_ENGINE`
(`mysql` | `postgres` | `both`); el modo `both` deja los dos lado a lado para
comparar resultados.

**En PostgreSQL cada conexión es un proceso del servidor**, con `max_connections`
en 100 por default, contra los 151 y threads baratos de MySQL. Eso convierte el
presupuesto de conexiones en la restricción real del paralelismo: el techo del pool
de indicadores lo pone PostgreSQL, no el hardware. El cálculo está en `config.py` y
fija `IND_POOL_MAX_PROCS` en 12: **12 procesos × 2 conexiones por hijo + 50 del
padre (pool 30 + overflow 20) = 74 < 100**. Subir `IND_POOL_PROCS` sin rehacer esa
cuenta agota `max_connections` y tira la app entera, no solo la corrida. Ver
[Concurrencia: hilos, procesos y exclusión mutua](/manual/concurrencia-y-multihilo).

## Migraciones: congelar en vez de reescribir

La cadena Alembic 0001–0075 quedó **congelada como solo-MySQL**: tiene backticks,
`AUTO_INCREMENT` crudo, `DATABASE()`, enteros en columnas Boolean y un `sa.Enum`
sin `name=` en la 0001. Reescribirla era trabajo de alto riesgo sobre una base viva
ya en head, sin beneficio para el usuario. La alternativa cuesta un script y una
regla: las bases nuevas nacen desde los modelos.

De las 85 migraciones actuales, las 10 posteriores al freeze son portables, y
`tests/test_bootstrap_portability.py` lo verifica renderizándolas en modo offline
(`sql=True`) contra `mysql://` y `postgresql://`, **sin base y sin driver**. Eso
atrapa los errores de compilación de DDL en la PC de desarrollo, que no tiene
ninguno de los dos motores instalados; descubrirlo en producción cuesta una
migración a medio aplicar. Un segundo guard recorre `Base.metadata` y verifica que
ningún `sa.Enum` quede sin `name=`: compila en MySQL como ENUM inline pero aborta
el DDL en PG, y como las bases nuevas nacen por `create_all`, nadie lo notaría
hasta crear una.

> `FROZEN_HEAD = "0075"` lleva la nota "No mover hacia adelante". Correrlo para que
> pase el test desactiva silenciosamente la verificación de las migraciones que ya
> eran portables.

La limitación conocida: una migración de **datos** que lea con `op.get_bind()` no
se puede renderizar offline. Se resolvió con un guard
`if op.get_context().as_sql: return` dentro de cada migración —lo llevan cuatro de
las diez post-freeze— y no con una lista de exclusión en el test: así no hay dos
archivos que recordar, y el DDL de esa misma migración sigue verificándose. El
costo es que esa parte no la cubre la suite y hay que probarla a mano contra ambos
motores. Ojo también con que las migraciones post-freeze **no** importan
`db_compat`: llevan helpers de dialecto duplicados inline a propósito, porque una
migración es un snapshot histórico y un refactor de la capa cambiaría lo que hizo
una migración ya aplicada.

Las bases nuevas las arma `scripts/init_db.py`: base vacía → `create_all` +
`alembic stamp head` (único camino válido en PG, y el recomendado también para
MySQL nuevo); base existente → `upgrade head`. Como las tablas `ind_{code}` no
están en `Base.metadata`, `ensure_ind_table()` las materializa desde las
definiciones de indicador. Que los dos caminos den el mismo esquema se validó con
un `alembic check` limpio sobre la base MariaDB del Codespace — la verificación que
hace legítimo el freeze: si divergieran, una base nueva y una migrada quedarían
distintas para siempre.

## Estado y deuda

Las fases 1 a 4 —capa `db_compat`, bootstrap portable, semántica y entorno
`DB_ENGINE`— están hechas y commiteadas. La fase 5, paridad de resultados entre
motores, tiene la herramienta lista (`scripts/compare_engines.py`, que compara
conteos por tabla, agregados por fecha con tolerancia y el orden del ranking de
cada estrategia) pero figura como **ejecución pendiente**; la fase 6, migrar datos
reales, quedó como "si se decide". Tampoco hay medición registrada de los riesgos
de performance que el propio plan señalaba para PG: heap contra la PK clusterizada
de InnoDB al leer series `ind_*`, y `delete_by_ranges` bajo MVCC.

> Esos estados contradicen otra nota del proyecto: `docs/notes/guide_deploy.md`
> documenta que Railway, el entorno de producción, corre PostgreSQL. El plan por
> fases no se actualizó y el docstring de `db_compat` sigue diciendo
> "MySQL/MariaDB (producción actual)". Verificar cuál refleja la realidad antes de
> apoyarse en cualquiera de las dos.

Queda una deuda. `signal_backfill_range.py` conserva
una rama por dialecto inline que duplica `db_compat.placeholder` — no es un
descuido, precede a la capa, pero deja a `placeholder()` sin consumidores externos.

El costo permanente: **mientras el soporte dual esté vigente, el código queda en el
mínimo común denominador**. Las ventajas PG-only —`COPY`, vistas materializadas,
índices parciales, particionado— se posponen o van detrás del mismo despacho por
dialecto. Soportar dos motores no es gratis aunque el código quede limpio.

Un beneficio no buscado, en cambio: `tests/test_dual_semantics_flows.py` prueba
flujos que **antes no podían ni ejecutarse** en la suite, porque su SQL era
MySQL-only. sqlite comparte con PG las dos propiedades que importan acá —`=`
case-sensitive y soporte de `ON CONFLICT`— así que portar a un segundo motor
amplió la cobertura de tests como efecto colateral.
