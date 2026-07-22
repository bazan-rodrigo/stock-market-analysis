# PostgreSQL-only: qué se gana y qué se pierde al retirar el soporte dual

> Estudio del 22-jul-2026. Pregunta del usuario: *cuánto ganaríamos si quitamos
> el soporte dual y nos quedamos solo con PostgreSQL — beneficio, pérdida, y qué
> funcionalidades se beneficiarían de features que PG tiene y otros motores no.*
> Solo estudio y plan: **no se programó nada**.
>
> Contexto previo: `design_postgresql_dual.md` (el estudio inverso, 16-jul, que
> incorporó PG sin perder MySQL) y `project_postgresql_migracion.md`.
>
> **Método:** primera versión escrita leyendo la capa `db_compat` y el diseño
> dual; después **verificada por 8 agentes contra el código real**. La
> verificación encontró una cita truncada que invertía el argumento central,
> 3 afirmaciones falsas y ~20 imprecisiones, y **cambió el veredicto**. Lo que
> sigue es la versión corregida; los errores de la primera versión están
> anotados donde importan, porque explican por qué la conclusión intuitiva
> ("cortar el dual desbloquea la escala") no se sostiene.
>
> **ACTUALIZACIÓN 22-jul (respuesta del usuario a la pregunta abierta #1):
> la instalación MariaDB ya NO se usa. La única base es PostgreSQL en Railway.**
> Eso resuelve el estudio a favor del corte, pero **no por los motivos que la v1
> daba**: el corte es higiene de bajo riesgo sobre un motor muerto, no la
> palanca que desbloquea la escala. Ver "Veredicto final". El plan ejecutable
> está en **`plan_corte_pg_only.md`**.

---

## Veredicto final (22-jul, con MariaDB confirmada fuera de uso)

**Cortar: sí. Pero el corte es limpieza, no la palanca de escala — y el orden
importa.** Etapa 0 (precondiciones en Railway) → **A** (bugs vivos) → **B** (el
corte) → **C** (esquema PG-only) → **D** (cosecha medida). Detalle ejecutable en
`plan_corte_pg_only.md`.

Tres consecuencias del hecho nuevo:

1. **Se CANCELA la fase 5 del plan dual** (el gate de paridad con
   `scripts/compare_engines.py`). Sin segundo motor no hay nada que comparar, y
   el comparador además estaba roto para las tablas anchas (`_value_col:76-81`
   solo reconoce columnas `value`/`score`). **Ese es el ahorro más grande del
   hecho nuevo, mayor que las ~1.130 líneas de código**: se cae el gate que
   bloqueaba todo el plan y que llevaba parado desde el 16-jul.
2. **La opción 3 (dual asimétrico) queda descartada.** Su único contra-argumento
   era "deja al motor de producción sin optimizar"; ahora se invierte: no hay
   motor de producción que proteger del otro lado. Mantener una rama para un
   motor apagado es puro costo de lectura.
3. **El orden "cortar antes de cosechar" queda confirmado, pero por una razón
   distinta a la intuitiva.** El argumento "cosechá primero para no escribir
   despacho que después tirás" **no aplica**: el seam de escritura genérico lo
   exige **sqlite**, no MySQL (`tests/conftest.py:31-46` fuerza el stub y aborta
   si el dialecto no es sqlite). Lo único MySQL del seam son 4 líneas
   (`db_compat.py:129,132-135`). Lo que sí justifica cortar antes de la cosecha
   es que **B es un refactor demostrablemente inerte sobre el motor vivo** (las
   10 ramas fuera de `db_compat` son ramas no-tomadas bajo PG), mientras que D
   cambia lo que Railway ejecuta de verdad; y que B mata la regla de paridad
   byte a byte, que es el impuesto que se paga en **cada** edición de camino
   caliente, o sea en toda la etapa D.

**Lo que NO cambia con el hecho nuevo:** el análisis de ganancias y pérdidas de
las secciones 3 y 4 sigue en pie tal cual. En particular, **el corte no acelera
nada por sí solo** — la performance está en la etapa D (COPY, CLUSTER,
fillfactor, LATERAL), que exige medición propia porque el "3-10x de COPY" no
está medido acá y las dos últimas victorias de perf vinieron de *escribir
menos*, no de escribir más rápido.

**Un riesgo se agrava con el corte y hay que atacarlo ANTES (etapa A):** la red
de retry está inerte bajo PG (pérdida #4 de la sección 4), y **MariaDB era el
único motor cuyo `innodb_lock_wait_timeout` hacía visible ese escenario**. El
corte remueve el testigo del bug: un escritor bloqueado se cuelga en silencio,
con el heartbeat de `run_lock_service` latiendo, así que la corrida *parece*
estar corriendo.

---

## Veredicto original del estudio (antes de saber que MariaDB estaba apagada)

*Se conserva porque el razonamiento sigue siendo válido si algún día vuelve a
haber un segundo motor, y porque explica por qué el corte NO es lo que
desbloquea la escala.*

**Cortar el dual gana mucho menos de lo que parece, porque casi todo el
beneficio PG está disponible SIN cortar.** La recomendación era la **opción 3
(dual asimétrico)**: declarar MySQL rama legacy congelada, cosechar ya las
ventajas PG detrás del despacho que `db_compat` **ya tiene**, y dejar escritos
los gatillos que dispararían el corte definitivo más adelante.

Los cuatro hechos que sostenían esto (los tres primeros siguen siendo ciertos;
el cuarto lo canceló la respuesta del usuario):

1. **El dual no bloquea las optimizaciones PG.** El diseño dual dice
   textualmente que las ventajas PG-only *"se posponen **o van detrás del mismo
   despacho**"* (`design_postgresql_dual.md:210`). La primera versión de este
   estudio citó esa frase **cortada en "se posponen"**, convirtiendo una
   disyunción en un dilema. Con la cláusula restituida, el pilar del argumento
   ("hay que cortar para poder escalar") se cae: de los 5 ítems de mayor
   impacto, **4 se capturan sin tocar la rama MySQL**.
2. **La producción ya es PostgreSQL.** `docs/notes/guide_deploy.md:16` rotula
   Railway **(prod)** sobre PG, desde el 17-jul (`847c6eb`). El "Linux + Apache2
   + mod_wsgi + MariaDB" que este estudio daba por producción viva solo
   sobrevive en documentación desactualizada (`CLAUDE.md:81`, `PROMPT.md:32`,
   `project_overview.md:11`); en el repo **no hay ninguna config de Apache
   versionada**. O sea: la app viva ya corre sobre PG y ya cosecha lo que PG da.
3. **El costo de mantener el dual es empíricamente ≈0.** Desde que aterrizó
   (`5029d9e`) hubo **122 commits**; `db_compat.py` fue tocado por **3**, y de
   esos uno *agregó* una feature PG y otro fue relleno de tests. Un solo autor
   en el repo: no hay costo de coordinación ni riesgo de que "otro" rompa la
   paridad byte a byte.
4. **El corte tiene un gate que lleva 6 días parado y compite por un recurso
   escaso.** La fase 5 del plan dual (paridad + performance) está en
   "herramienta lista, ejecución pendiente" desde el 16-jul, y
   `project_pendientes.md` nombra el Codespace 17 veces, casi todas
   verificaciones que compiten por él. Un plan serial fase 0 → 1 → 2 → 3 → 4
   corre el riesgo de dejar **la ola de escala en pausa esperando una decisión
   que espera una medición que espera un Codespace ocupado**. La opción 3 no
   tiene ese modo de falla: cada optimización PG se puede hacer mañana.

**Lo que sí exige cortar** (o al menos, tocar el esquema compartido) es un
subconjunto chico y no urgente: particionado declarativo, `citext`/índices
únicos funcionales, JSONB, dropear `prices.id`. Ese subconjunto es el criterio
natural del corte, no su motivación.

**Contra-argumento honesto a la opción 3:** si la instalación MariaDB todavía
existe y tiene datos que importan, el asimétrico deja al motor de producción
como el NO optimizado — el único escenario donde esta opción falla.
→ **Resuelto el 22-jul: MariaDB no se usa.** El contra-argumento se invierte y
la opción 3 queda descartada (ver "Veredicto final").

---

## 1. Las tres opciones sobre la mesa

*(Tabla escrita antes de saber que MariaDB estaba apagada. Con ese dato, las
filas "requiere migrar datos" y "requiere el gate de paridad" pasan a **no** en
la columna 2, y la opción 3 pierde su ventaja: gana la **2**.)*

| | **1. Dual simétrico (statu quo)** | **2. PG-only (la elegida)** | **3. Dual asimétrico** |
|---|---|---|---|
| Rama MySQL | se mantiene y se optimiza | se borra | se congela: funciona, no se optimiza más |
| Optimizaciones PG | mínimo común denominador | libres | libres, detrás del despacho existente |
| Requiere migrar datos | no | sí (si MariaDB vive) | no |
| Requiere el gate de paridad | no | **sí** | no |
| Puerta de un solo sentido | no | **sí** | no |
| Ahorro de código | 0 | ~1.130 líneas (~65% tests) | 0 (y suma ~60-80 de seams nuevos) |
| Desbloquea esquema compartido | no | **sí** | no |

El estudio original planteaba una binaria 1 vs 2. La opción 3 no es un invento:
**el repo ya la practica**. `db_compat.table_write_stats`
(`app/services/db_compat.py:264-281`) es PG-only, devuelve `None` en los otros
motores y el Centro de Datos muestra "no disponible en este motor" — 18 líneas.
Y `asset_service.purge_assets` (`:93` vs `:124`) implementa **dos algoritmos
distintos**, no un mínimo común denominador.

**Por qué la regla "byte-idéntico al histórico" no lo impide:** esa regla es
una propiedad de *lo que emite la rama MySQL*, no del archivo. Agregar una rama
PG nueva (COPY, prefijos DDL) no cambia el string que `upsert_sql` produce para
MySQL, y los tests de paridad (`tests/test_db_compat.py:140-190`) siguen verdes
sin editarlos.

---

## 2. Qué cuesta hoy el soporte dual (inventario medido)

### 2.1 Código y tests que existen solo por el dual

| Pieza | Medición real | Qué pasa con PG-only |
|---|---|---|
| `app/services/db_compat.py` (281 líneas) | **48 líneas estrictamente MySQL = 17%** (import `_mysql_insert`, `is_mysql`, rama mysql de `upsert` y `upsert_sql`, errnos 1205/1213, `set_bulk_load_checks`, rama mysql de `approx_table_rows`) | Queda en **~200-230**, no en ~150: el seam PG↔sqlite, `ci_equals`, `wipe_table`, `_dedupe_last` y `_conflict_cols` se quedan. También se simplifican `supports_truncate` y `order_desc_nulls_last` |
| `tests/test_db_compat.py` (434 líneas, 29 tests) | Se borran **11 de 29 (38%), ~146 líneas** | Sobreviven 18 tests / ~290 líneas: forma PG del upsert, SQLSTATEs de psycopg2/3, `ci_equals`, y los 5 que **ejecutan upserts reales contra sqlite** |
| `scripts/compare_engines.py` (212) + `tests/test_compare_engines.py` (115) | se retiran | — |
| `tests/test_lock_retry_and_purge.py` | **no se borra: se reescribe** — hoy testea solo errnos de InnoDB simulando `.orig.args[0]` de MySQLdb. Sin reescribir, quedaría testeando código muerto |
| `tests/test_dual_semantics_flows.py` (133), `test_config_db_url.py:27-28`, retoques en `test_indicator_batching.py:295,322,847` y `test_fundamental_batching.py:253` | parcial / se van | — |
| `tests/test_bootstrap_portability.py` (106) | render contra 1 dialecto en vez de 2 | se simplifica |
| Ramas sueltas fuera de `db_compat` | ver 2.2 | ~14 sitios |
| `requirements.txt` | `mysqlclient>=2.2.0` | se va (y con él el bloque de build-deps del setup, ver 2.2) |
| Cadena Alembic 0001–0075 | **no se toca** — historia congelada; toda base nueva nace por `scripts/init_db.py` (create_all + stamp head) | — |

**Total ≈1.130 líneas.** La estimación original de "~1.000" era correcta, incluso
conservadora. Pero el desglose importa: **~65% son tests y herramientas de
verificación**. Borrarlos reduce cobertura, no carga de mantenimiento. El ahorro
neto de **código de producción es ~130 líneas sobre las ~44.900 de `app/`**.

### 2.2 El inventario de ramas fuera de `db_compat` (corregido y completado)

- `asset_service.purge_assets` — `:93` (mysql) vs `:124` (pg), dos algoritmos.
- `maintenance_service` — **4 funciones / 6 sitios**, no 3: `:42+46`
  (`_table_size_bytes`), `:80` (VACUUM/OPTIMIZE), `:152+158` (`_all_table_sizes`),
  `:172+174+177` (`database_size_report`). La rama sqlite de `:59` se queda.
- Consola SQL — **dos archivos**: `app/pages/admin_sql.py:25` (query default) y
  `app/callbacks/admin_sql_callbacks.py:171` (rollback tras statement fallido).
- **`signal_backfill_range.py:636`** — faltaba en la primera versión y es el más
  importante: `use_async = is_mysql(s) or is_postgres(s)` **activa el escritor
  asíncrono y el pool de lectores**. No es un detalle de SQL: cambia la
  arquitectura de la corrida. Camino caliente.
- `scripts/measure_indicator_storage.py` — 4 sitios.
- **Configuración, donde el default sigue siendo MySQL** (faltaba entero):
  `app/config.py:57-61` arma `mysql+mysqldb://…?charset=utf8mb4` cuando no hay
  `database_url`; `:50` `DB_PORT=3306`; `conf.properties:4` y `.example:4,8`;
  y **`.devcontainer/devcontainer.json:7,9`** fija `DB_ENGINE=mysql` +
  `DB_PORT=3306` en `remoteEnv`. Sin tocar esto, una instalación PG-only sin
  `DATABASE_URL` explícita **levanta intentando MySQL y falla importando un
  driver que ya no estaría instalado** — no con un error claro de config.
  Nota: cambiar solo los `.sh` del setup no alcanza, el valor efectivo lo
  inyecta `devcontainer.json`. Y `.devcontainer/setup.sh:88-92` instala
  **incondicionalmente** `default-libmysqlclient-dev build-essential pkg-config`
  ("Siempre: requirements.txt incluye mysqlclient") — ese bloque cae con la dep
  y hoy es parte de lo que hace lento el postCreate.
- `scripts/init_db.py:64-69` — el flag `--via-migrations`, declarado "solo
  MySQL", muere con el dual.

### 2.3 El costo recurrente (lo que no se ve en líneas)

- **Regla de paridad byte a byte:** cada cambio que roza SQL con sabor a motor
  obliga a razonar dos ramas. Medido: se activó 3 veces en 122 commits.
- **Matriz de verificación:** "probado" debería significar probado dos veces.
  En la práctica **ya no se cumple** — ver pérdida #5 en la sección 5.
- **Mínimo común denominador:** solo muerde donde hay esquema compartido.
  `order_desc_nulls_last` existe porque MariaDB no soporta `NULLS LAST`;
  `ci_equals` renuncia al índice para replicar una collation de MySQL.

**Higiene independiente de la decisión:** `set_bulk_load_checks`
(`db_compat.py:171-189`, 19 líneas) **no es un no-op fuera de MySQL: es código
muerto en los tres motores**. Grep completo: cero call sites de producción —
solo la definición, 3 tests y las docs (`docs/manual/1050-concurrencia-y-multihilo.md:227`
ya lo registra: *"quedó como código muerto"*). Quedó huérfano al quitar el
toggle del rebuild por un bug de afinidad de conexión. **Esas 19 líneas se
borran hoy, en cualquier escenario** — no son ahorro atribuible al corte.

---

## 3. Qué se GANA — features PG mapeadas a call sites reales

Esta es la pregunta central del usuario. La columna clave es la última: casi
todo se cosecha **sin cortar**.

### Nivel 1 — pegan directo en el objetivo de 10k activos

| # | Ganancia | ¿Requiere cortar el dual? |
|---|---|---|
| 1 | COPY en escritura | **No** — seam nuevo `db_compat.bulk_write` con fallback a `upsert_sql` |
| 1bis | COPY en lectura | **No** |
| 2 | CLUSTER en vez de VACUUM FULL | **No** — una línea |
| 3 | UNLOGGED en derivadas | **No** — helper de prefijos DDL |
| 4 | `pg_stat_statements` / EXPLAIN | **No** — es método, cero código |
| 5 | Query paralelo | **No** — lo da el planner (con caveat) |
| 6 | **Particionado por fecha** | **SÍ** — toca esquema compartido |

**1. `COPY` (psycopg3 `cursor.copy()`) en los caminos calientes de escritura.**
La primera versión citó mal los tres call sites. Los reales:

- (a) `technical_service.upsert_ind_cadence` (`:786-821`) — `executemany` de
  upserts crudos (`upsert_sql`, chunks de 5.000) sobre las tablas **anchas**
  `ind_daily/weekly/monthly` + `ind_fundamental_*`, alimentado por el buffer de
  fila completa del rebuild (`_wide_buffer_flush`, `:851-874`). *(El
  `executemany` de `_write_ind_series` `:769-783` que citaba la v1 **está muerto
  en producción**: solo corre para códigos fuera de `_WIDE`, y
  `use_wide_ind_tables()` es `True` por default —`indicator_store.py:84-92`—
  con las per-código dropeadas por la 0079.)*
- (b) `signal_backfill_range._bulk_insert` (`:529-535`) — **INSERT plano, sin
  ON CONFLICT** (la v1 decía que usaba `upsert_sql`): el `_initial_cleanup`
  (`:475-522`) o el DELETE del batch (`:539-563`) garantizan rango vacío. Corte
  a 150.000 filas (`:186`).
- (c) `price_service._upsert_prices` (`:80-86`) — `db_compat.upsert()`, o sea
  INSERT multi-fila **compilado por SQLAlchemy**, en lotes de 500 (`_PRICE_BATCH`
  `:49`, con el comentario *"evita superar max_allowed_packet de MariaDB"* — un
  límite que COPY hace desaparecer).

**Dónde COPY es DIRECTO** (sin temporal, sin ON CONFLICT): el rebuild de
indicadores (`_force_reset_ind_tables` trunca antes del pool,
`technical_service.py:1587-1626`), **todo** el backfill de señales (los tres
modos borran antes de insertar; ~2M filas por chunk de 250 fechas a 500 activos
× 16 señales) y el import de precios (`price_service.py:155-162`, `:338-343`
borran el rango en la misma transacción — ojo: `prices` tiene PK sustituta `id`,
el COPY debe declarar la lista de columnas sin `id`).
**Dónde hace falta temporal + `INSERT … ON CONFLICT`:** solo el **delta** de
indicadores (upsert parcial de columnas sobre filas existentes,
`technical_service.py:765-767`), que es el camino barato.

> ⚠️ **El "3-10x" de la v1 era un número de folleto.** No hay una sola medición
> del repo detrás, y `project_scaling_target.md:143-145,225-232` documenta que
> los benchmarks sintéticos **mintieron tres veces en un día**, uno por 10x —
> de ahí salió el método de 4 pasos. Peor: hay evidencia de que **escribir ya no
> es el cuello**. Las dos últimas victorias de perf (`5c271d4`, `79c31e7`) no
> fueron escribir más rápido sino **escribir menos** (21.432 → 153 updates;
> 5.331 → 0-4), y la validación del 21-jul dejó el pipeline en ~1,0 upd/activo
> con inserts puros en el rebuild. **El techo real de COPY acá probablemente sea
> mucho menor que el de la literatura. Medir antes de invertir.**

**1bis. `COPY (SELECT …) TO STDOUT (FORMAT BINARY)` del lado de la LECTURA.**
La v1 solo miró COPY para escribir. Las lecturas van por `fetchall`/`read_sql`,
que en psycopg3 arma un objeto Python por celda. Call sites con volumen lineal
a 10k activos: `_load_all_prices` (`technical_service.py:1313-1322`),
`_load_prices_for_assets` (`:1343-1365` — **se paga N veces, una por proceso
hijo del pool**), `_load_fund_prices` (`fundamental_service.py:990-1013`),
`_load_sweep` (`signal_backfill_range.py:222-238`, por código y por chunk) y la
carga del backtest (`backtest_service.py:122-126`). MySQL no tiene equivalente
usable desde el driver: PG-only puro, y pega donde está el cuello.

**2. `CLUSTER` en vez de `VACUUM FULL` — cierra el riesgo abierto que hoy
justifica no cortar.** `maintenance_service.py:80-83` emite hoy
`VACUUM (FULL, ANALYZE)`. `CLUSTER ind_daily USING ind_daily_pkey` toma **el
mismo lock ACCESS EXCLUSIVE, cuesta lo mismo y compacta igual**, pero deja el
heap ordenado por `(asset_id, date)` — el orden exacto de todas las lecturas por
activo. Es un cambio de una línea en un servicio **que ya tiene botón en la UI**.
Aplicable a `ind_daily/weekly/monthly`, `prices` (USING `uq_asset_date`) y
`sig_*`/`strat_res_*`. Limitación honesta: es one-shot, el delta diario vuelve a
desordenar la cola.

**3. Tablas `UNLOGGED` para derivadas regenerables.** No generan WAL. Pero el
trade-off de la v1 estaba mal caracterizado ("es el mismo contrato que ya
tienen"): **el dato es regenerable, la reposición NO es automática.**
- `signal_service.py:975-995`: el delta arma `computed` como (fechas presentes
  en `sig_{id}`) ∪ `signal_eval_log`. Con `sig_*` vacía y `signal_eval_log`
  intacta, **todas las fechas quedan marcadas como hechas y el delta no repone
  nada**. `cleanup_service.py:47-49` ya documenta el riesgo textualmente. Y
  `signal_eval_log` **no** cae bajo los prefijos `sig_`/`strat_res_`.
- `technical_service.py:1634-1645` + `:1914-1955`: el delta tail-mode confía en
  min/max/count y checksum cacheados en `ind_asset_meta`.
- **Riesgo operativo:** una tabla UNLOGGED no se replica a standbys y llega
  **VACÍA a cualquier restore por pg_basebackup/PITR** — en Railway, un restore
  dejaría todas las derivadas vacías y exigiría "Recalcular completo" como parte
  del procedimiento de recuperación.

  → Marcar UNLOGGED también los metadatos que gobiernan los deltas
  (`ind_asset_meta`, `signal_eval_log`, `current_indicator_values`) o agregar un
  chequeo de tabla vacía al arranque; y documentar el runbook de restore ANTES
  de aplicarlo. **Alternativa de menor riesgo y casi el mismo beneficio:**
  `synchronous_commit=off` **por sesión** durante el rebuild (se pierden
  milisegundos de commits ante crash del SO, no la tabla entera, y no requiere
  DDL) — pero hoy no hay dónde setearlo (ver sección 6).

**4. Observabilidad: `pg_stat_statements`, `EXPLAIN (ANALYZE, BUFFERS)`.** El
paso 3 del método de escala ("medir en la base") hoy se hace con herramientas
pobres. ⚠️ **Caveat que la v1 no vio:** `pg_stat_statements` requiere
`shared_preload_libraries` + restart del servidor, que en PG gestionado
(Railway) suele **no ser configurable por el usuario**. Sí están disponibles sin
tocar el servidor: `EXPLAIN (ANALYZE, BUFFERS)`, `pg_stat_user_tables` (ya
usado por `write_stats_service`) y `pg_statio_user_tables`. **Verificar
disponibilidad antes de que ningún plan dependa de ello.**

**5. Query paralelo** para las lecturas cross-seccionales (ranking, backtest).
⚠️ **Caveat:** choca con el ProcessPool. `_resolve_pool_procs`
(`technical_service.py:1387-1397`) dimensiona procesos *"para no reventar
max_connections"* y cada hijo abre su pool; con parallel workers los backends
pasan a N×(1+`max_parallel_workers_per_gather`) compitiendo por el mismo disco
— **la patología ya medida acá** (`_READ_WORKERS` bajó de 8 a 3 porque *"los
lectores le sacaban CPU/disco al propio servidor"*; el pool volvió de cores+6 a
cores+2 por contención). Receta correcta: **asimétrica** —
`max_parallel_workers_per_gather=0` en las sesiones de los hijos (hook natural:
`process_child.child_initializer:31-37`), paralelismo alto solo en las lecturas
de un solo hilo.

**6. Particionado declarativo por fecha — el único que exige el corte.**
> ❌ La v1 decía: *"MySQL tiene particiones con restricciones fuertes (la clave
> de partición debe integrar toda clave única); en PG es directo."* **Falso:
> PostgreSQL exige exactamente lo mismo.** Y las dos tablas candidatas tienen PK
> sustituta: `app/models/group_scores.py:23` y `group_signal_value.py:11`
> (`id = Column(Integer, primary_key=True)`). Particionar por `date` obliga a
> **eliminar ambas PKs** (que nada consulta), recrear las tablas y mover los
> datos: un cambio de esquema compartido que impacta también a MySQL, va por
> migración post-freeze con render dual, y necesita un servicio de mantenimiento
> de particiones que no existe. **Es un proyecto, no un ítem de cosecha** — y
> por eso es el criterio natural del corte definitivo.

> ❌ Además, el dolor que la v1 usaba para justificarlo (*400s+ reteniendo locks;
> el loop `DELETE … LIMIT` en O(n²), 17min sin terminar*) **se midió sobre
> `signal_value`, tabla que YA NO EXISTE**: la 0075 la partió en
> `sig_{id}`/`strat_res_{id}` y la dropeó (`0075_sig_strat_tables_per_unit.py:55-78`).
> Y "las por-unidad ya se truncan enteras" es incompleto: el TRUNCATE ocurre
> **solo con `whole_history`** (`signal_backfill_range.py:485-489, 512-517`); el
> rebuild **acotado** (el caso frecuente) les hace `delete_by_ranges` en ventanas
> de 100 fechas, y el delta les borra por fecha en cada flush. A la inversa,
> `group_scores`/`group_signal_value` **sí** se truncan enteras en `full_wipe`.
> **Falta re-medir el costo sobre la topología actual antes de justificar nada.**

### Nivel 2 — arreglan deuda existente

7. **Índices únicos funcionales (`LOWER(col)`) o `citext`.** Precisando el
   alcance real de los 11 call sites de `ci_equals`:
   - **Bug REAL, uno solo:** `users.username` (`app/models/user.py:14`,
     `unique=True`). El login hace `.filter(ci_equals(...)).first()` **sin
     ORDER BY** (`app/__init__.py:151-152`) y el alta **no valida caso**
     (`reference_service.py:343-350`, `:366`: solo `.strip()`). En PG 'Admin' y
     'admin' **coexisten** y el `.first()` devuelve una fila arbitraria según el
     plan → **autenticación no determinista**, o login contra la cuenta
     equivocada con otro rol.
   - **No afectadas** (unicidad CI sostenida por la app, con TOCTOU):
     `signal_definition.key` (`signal_service.py:587-590`), `catalog_alias`
     (`reference_service.py:396-403`). `assets.ticker` está blindado por
     normalización `.upper()` al escribir.
   - **Caso aparte:** `strategy.name` **no tiene UNIQUE** en ningún motor
     (`app/models/strategy.py:23`); la ambigüedad es preexistente, no regresión.
   - **Bonus que la v1 no vio:** `ci_equals` emite `LOWER(col)`
     **incondicionalmente** en los 11 sitios. En MySQL eso es puro costo (la
     collation `_ci` ya daba la igualdad) e inutiliza el índice — **una
     regresión de perf que el dual introdujo sobre el motor de producción y que
     nadie midió**. Bajo la opción 3 se arregla a favor de los dos: MySQL vuelve
     a `col == value` (que además es el SQL histórico pre-dual) y PG usa
     `LOWER()` con índice funcional.
8. **`prices.id` es una PK sustituta MUERTA.** `Price.id`
   (`app/models/price.py:19`) no aparece en ninguna query del código (verificado
   por grep: el único hit es un docstring de `db_compat`). Existe porque bajo
   InnoDB la PK autoincremental daba clustering por orden de inserción; en el
   heap de PG **no aporta nada**: ~50M entradas btree (~1,1 GB a 10k activos)
   mantenidas en cada insert y jamás leídas. PG-only: PK a `(asset_id, date)`,
   dropear `id`. Colateral: `db_compat._conflict_cols` (`:57-71`) dejaría de
   necesitar el fallback a `UniqueConstraint`, documentado explícitamente *por*
   `prices.id`.
9. **El costo de FK en inserts masivos.** Todas las `ind_*` llevan FK
   `asset_id → assets` con CASCADE (`indicator_store.py:190-191`, `:219-221`);
   `sig_*`/`strat_res_*` deliberadamente **no** (`signal_store.py:20-22`: *"el
   chequeo de FK encarecería cada insert masivo"*). En PG ese chequeo es un
   trigger RI por fila vía SPI, más caro que el lookup de InnoDB, y se paga en
   decenas de millones de filas del rebuild. Y como `set_bulk_load_checks` está
   muerto, **hoy nadie desactiva nada, ni en MySQL**. PG-only: dropear la FK
   (coherente con `signal_store`; `purge_assets:124-144` ya limpia esas tablas
   explícitamente) o `SET session_replication_role='replica'` en el rebuild.
10. **Reporte de escrituras del Centro de Datos** pasa de degradado a pleno
    (`table_write_stats` ya es PG-only).
11. **`NULLS LAST` nativo** (`order_desc_nulls_last` existe solo por MariaDB;
    sqlite ≥3.30 también lo soporta, así que hasta la rama de tests se limpia).
12. **DDL transaccional — cobra dos deudas concretas.** (a)
    `cleanup_service.clean_data` (`:125-139`) corre bajo `bind.begin()` con el
    docstring *"si algo falla, no queda una limpieza a medias"* — **bajo MySQL
    eso es FALSO** (el TRUNCATE de cada tabla dinámica hace commit implícito);
    bajo PG es verdadero. Una garantía documentada que hoy no se cumple. (b) Al
    revés: `signal_store.reconcile_dynamic_tables` (`:143-172`) existe
    justificado en que *"el DDL de MySQL no es transaccional"* (`:10-13`); en PG
    la ventana de inconsistencia desaparece y deja de ser una necesidad
    estructural (sigue sirviendo contra ediciones por `/admin/sql` y kill -9).
13. **`fillfactor` 80-85 en las tablas anchas.** El caso fuerte no es
    `current_indicator_values` (100k filas) sino **la cola de `ind_daily` en el
    delta**: `upsert_ind_cadence` hace ON CONFLICT DO UPDATE sobre las últimas
    fechas de cada activo en cada corrida (`technical_service.py:765`: *"bloat
    chico de la cola → autovacuum"*). Ni la PK `(asset_id,date)` ni
    `ix_{table}_date` incluyen las columnas actualizadas → **el UPDATE ya es
    candidato a HOT**, solo falta espacio libre en la página.
14. **Advisory locks — no es un "si algún día".** Existe hoy
    `app/services/run_lock_service.py` (280 líneas: heartbeat en thread daemon,
    token de propiedad, stale-reclaim a 120s, latch, fail-open) cuyo docstring
    (`:1-19`) declara que la mecánica es así por ser *"atomicidad PORTABLE
    MySQL/PostgreSQL/sqlite sin SQL de motor"*. Con `pg_advisory_lock` sobre una
    conexión dedicada el lock se libera **solo cuando esa conexión muere** —
    exactamente el evento que el heartbeat intenta detectar. Desaparecen el
    thread de latido, el token y el reclaim. Caveats: exige conexión sostenida
    (no la scoped session) y se rompe bajo pooler en modo transacción.
    **Bonus:** `run_lock_service.py:65-73` incluye `"1146"` (errno MySQL) en
    `_MISSING_TABLE_MARKERS`, matcheado **por substring sobre el mensaje** — con
    PG es ruido y puede matchear por casualidad (un id, un OID) y latchear el
    lock como no disponible para todo el proceso.
15. **El límite de 64 KB de TEXT en MySQL.** Las columnas `Text` con JSON
    adentro compilan a TEXT (**tope duro 65.535 bytes**); en PG `text` es
    ilimitado. Afecta a `strategy.filter_conditions` (`:25`),
    `signal_definition.params` (`:37`), `backtest_run.config` (`backtest.py:24`),
    `portfolio.config/summary` (`portfolio.py:114-115`) y los tracebacks de
    `*_update_log.error_detail`. Un árbol de filtro grande o un summary de
    walk-forward con muchos folds puede pasarlo: **en MariaDB no estricta eso
    trunca SILENCIOSAMENTE y deja JSON inválido**. → Si alguna vez se migran
    datos desde MariaDB, revisar si ya vienen truncados.

### Nivel 3 — menores u oportunistas

16. **`LATERAL` (no `DISTINCT ON`).** La v1 vendía `DISTINCT ON` como "más
    simple y rápido": es más simple, **no más rápido** (recorre las mismas filas
    que el GROUP BY MAX). Lo que cambia el orden de magnitud es **LATERAL**
    (`FROM assets a, LATERAL (SELECT … ORDER BY p.date DESC LIMIT 1)`): N
    descensos de índice en vez de un scan de 50M filas. Y **MariaDB no soporta
    derived tables laterales** (MySQL 8.0.14 sí) → genuinamente PG-only frente
    al motor actual. Call sites: `price_service.get_latest_prices_all`
    (`:743-765`), `indicator_store.query_values_asof` (`:260-275`),
    `portfolio_service.py:404-412`.
17. **JSONB** en las columnas de config/árboles: validación de forma en la base
    e índices GIN. ⚠️ Sacarle el argumento de consulta que usaba la v1: la
    derivación del scope de group_scores
    (`signal_backfill_range._load_derivation_inputs:95-123`) carga **todas** las
    estrategias y señales con dos `.all()` sin filtro y parsea en Python — son
    decenas de filas, no un problema de performance, y el resultado necesita
    `restricted_attribute_ids`, lógica de árbol no expresable en un operador
    JSONB. El beneficio real es solo validación, a cambio de tocar el contrato
    de import/export xlsx.
18. **Extensiones** (TimescaleDB, pg_partman, pg_repack): ver el caveat del
    ítem 4 — en PG gestionado probablemente no estén disponibles.

### 3bis. Evaluadas y DESCARTADAS (para que no vuelvan)

- **Materialized views para group_scores/rankings.** No aplica: la arquitectura
  **ya es materialización a mano** con la ventaja decisiva del refresh **por
  delta** (por fecha, por señal, por estrategia). Una MATVIEW solo soporta
  refresh **completo** (`CONCURRENTLY` evita el lock pero igual recomputa todo)
  → sería una regresión de orden de magnitud. Además el score no es derivable en
  SQL: sale de un árbol AND/OR y una suma ponderada evaluados en Python
  (`strategy_service.py:102-125`).
- **`generate_series`** (la v1 lo listaba): **cero call sites**. No existe
  ningún spine de fechas de calendario — las fechas **siempre** salen de las
  ruedas reales de `prices` (`signal_service.py:929-931`) o de la unión de
  fechas efectivas de los activos (`portfolio_backtest_service.py:107-120`).
  Usarlo produciría fechas sin cotización, justo lo que el proyecto evita a
  propósito (gate de precio propio, semántica as-of).
- **Window functions / `percent_rank` en SQL.** MariaDB 10.2+ y MySQL 8 ya las
  tienen → **no es ganancia del corte**. Y no aplica: `percent_ranks`
  (`strategy_service.py:73-99`) se calcula en Python porque el valor que rankea
  no existe en la base.
- **`ON CONFLICT DO NOTHING`.** Hay un call site real (el INSERT de
  `signal_eval_log`, hoy un check-then-act contra un set en memoria,
  `signal_service.py:988-995`, que es una carrera si dos corridas se solapan),
  pero MySQL tiene `INSERT IGNORE`: vale poco como argumento PG-only.

---

## 4. Qué se PIERDE / qué cuesta

1. **Contra-evidencia MEDIDA: en la tabla dominante, PostgreSQL fue 7,3x PEOR y
   costó código extra.** La v1 no lo mencionaba ni una vez.
   `project_ind_wide_tables.md:49-52` y `design_ind_wide_tables.md:157-160`: el
   rebuild escribía columna por columna → cada fila ancha se actualizaba N veces
   → el MVCC de PG dejaba N-1 tuplas muertas → **`ind_daily` 3,4 MB → 25 MB**.
   InnoDB no tiene esa patología (update in-place en el índice clusterizado,
   versiones en el undo log). La mitigación fue construir un subsistema nuevo:
   `_wide_buffer_*` (`technical_service.py:825-880`, ~60 líneas). **El camino
   delta sigue sin bufferizar**, dependiendo de autovacuum (`:765`). Es el único
   encuentro medido entre PG y el camino caliente de indicadores, **y lo ganó
   MySQL**.
2. **Footprint: punto ciego frente a un techo duro documentado.**
   `design_ind_wide_tables.md:15-19,115-117` registra el tope de **500 MB en
   Railway** — todo el refactor ancho existió para bajar 22,8 → 4,1 MB. PG
   empuja al revés en cuatro frentes sobre las tablas más grandes: `sa.Float`
   sin precisión → `double precision` 8 bytes vs FLOAT 4 (decisión explícita del
   diseño dual, `:155-159`; en `ind_daily`, ~14 columnas float ≈ **+56 bytes por
   fila**); header de tupla de 24 bytes + alineación; InnoDB tiene
   `ROW_FORMAT=COMPRESSED` y PG no tiene equivalente nativo; y el bloat ya
   medido. → Si se quiere float4 real en PG hay que declarar
   `Float(precision=24)` en los modelos y las 5 tablas anchas.
3. **PostgreSQL NO tiene loose index scan — y el código lo asume por escrito.**
   `signal_service.py:939-942`: *"DISTINCT date … sobre el prefijo de la PK
   (date, asset_id) es un loose index scan barato"* — eso es semántica de
   MySQL/MariaDB. **PG no implementa index skip scan** (ni en PG17): recorre el
   índice entero o hace seq scan + HashAggregate. Peor, `signal_service.py:929-931`
   hace `SELECT DISTINCT date FROM prices` completo en cada corrida de historia,
   y el propio comentario (`:936-938`) dice que ya costaba *"18s por
   estrategia"*. Mismo patrón en `_count_price_assets` (`:963-968`),
   `_fund_asset_ids` (`fundamental_service.py:1039-1042`) y
   `technical_service.py:1329`. **Es una regresión de PG, no una oportunidad.**
   Mitigación PG-only: CTE recursivo de skip-scan emulado (~5.000 descensos de
   índice en vez de 50M filas).
4. **La red de retry queda INERTE bajo PG.** La v1 vendía el MVCC de PG como
   ganancia; es al revés. `_PG_RETRYABLE_SQLSTATES` (`db_compat.py:149-153`)
   espera 40001, 40P01 y 55P03. Con READ COMMITTED (el default, nunca se cambia)
   **40001 no se emite nunca**, y **55P03 solo aparece si hay `lock_timeout`
   seteado**. `app/database.py:6-13` crea el engine **sin `connect_args`**, no
   hay listener de `connect`, y no hay ningún `SET` de sesión en el repo. Bajo
   MySQL, `innodb_lock_wait_timeout` (50s) producía errno 1205 y el retry de
   `signal_backfill_range._flush` / `fundamental_service._fund_worker`
   funcionaba. **Bajo PG el mismo escenario bloquea indefinidamente: el flush no
   falla, no reintenta, y la corrida queda colgada sin error.** Precondición,
   no ganancia.
5. **MySQL es estrictamente MEJOR en el upsert masivo.** `ON DUPLICATE KEY
   UPDATE` tolera claves repetidas dentro del statement (gana la última); PG y
   sqlite **abortan el statement entero** con CardinalityViolation y en PG
   envenenan la transacción. **Ya pasó en producción** (`946fc6d`: la fuente
   Ámbito devuelve fechas duplicadas y volteaba el lote). Dos agravantes: (a)
   `_dedupe_last` (`db_compat.py:74-88`) es un pase O(n) en Python sobre cada
   lote y **no se va con el corte** (sqlite sigue siendo el motor de la suite),
   ahora sin el motor tolerante como plan B; (b) **`upsert_sql` —la variante
   cruda de los caminos calientes— NO deduplica** (`:121-138`): sigue expuesta a
   que un lote con `(asset_id,date)` repetido tumbe la corrida.
6. **Lectura por PK clusterizada** (riesgo original, acotado y re-dimensionado).
   Aplica a la lectura **por activo** (`technical_service.py:1843-1852` prefetch
   por chunk, `:1944-1952` fallback). **No** aplica a los sweeps por fecha del
   backfill (`signal_backfill_range.py:222-238`,
   `indicator_store.py:260-274`), que van por `ix_date` — secundario en ambos
   motores. Y el camino rápido tail-mode **saltea ese prefetch** para los 24
   códigos con historia (`technical_service.py:1737-1739`). Las tablas anchas
   cambian las mitigaciones: **el covering index dejó de ser barato** (no hay una
   columna `value` única — habría que `INCLUDE`-ar las 14 columnas de
   `ind_daily`, reintroduciendo el footprint de índices que el refactor vino a
   eliminar); `CLUSTER` es one-shot con lock exclusivo (pero ver ganancia #2).
7. **Nivel de aislamiento pasa de "diferencia entre motores" a "la
   semántica".** `app/database.py:6-16` crea el engine sin `isolation_level`.
   Bajo MySQL una sesión larga ve un snapshot REPEATABLE READ congelado; bajo PG
   (READ COMMITTED) cada sentencia ve datos nuevos. Importa en los lectores por
   chunks del backfill, el pool de workers y `purge_assets` (`:134-144` commitea
   por tabla mientras otras conexiones leen): un cálculo **transversal** que hoy
   sale de un snapshot estable puede volverse no determinista. Decidirlo
   explícitamente.
8. **Ordenamiento por collation** (la v1 solo cubrió la igualdad). En MySQL la
   base se crea `utf8mb4_unicode_ci` (`.devcontainer/setup.sh:50`) y ordena
   ignorando mayúsculas/acentos; en PG depende del `LC_COLLATE` de creación —
   con `C`/`POSIX` (habitual en imágenes Docker, **no controlado por el repo**)
   ordena por bytes: 'Zz' antes que 'aa'. Visible en ~20 dropdowns y tablas
   (`asset_service.py:156`, `asset_callbacks.py:71-72`,
   `signal_params_ui.py:164`, `strategy_filter_ui.py:64-67`,
   `currency_conversion_service.py:43,57`, `data_explorer_service.py:79`).
9. **`db_compat` no muere.** sqlite sigue siendo el motor de la suite (**~886
   tests** al 21-jul — el "~740" de `CLAUDE.md` está desactualizado; conteo
   actual: 813 `def test_` en `tests/*.py`). El seam PG↔sqlite queda, y esas dos
   ramas ya comparten el grueso (`on_conflict_do_update` es la misma API).
10. **Puerta de un solo sentido.** Hoy re-agregar MySQL cuesta poco. Después de
    COPY, particiones, índices `LOWER()`, UNLOGGED, JSONB y `prices` sin `id`,
    volver sería un proyecto. También se pierde la optionalidad de hosting.
11. **El oráculo ya está degradado.** La v1 listaba "se pierde el segundo motor
    como oráculo" como pérdida intacta. En la práctica **hace semanas que no se
    ejercita**: `project_ind_wide_tables.md:55-58` dice que todo el refactor
    ancho (24 tablas técnicas + 12 fundamentales, migraciones 0077-0079/0081/0082,
    el default `use_wide_ind_tables`) se probó **solo en Postgres/Railway** y
    *"en MariaDB … NO se corrió ahí — verificación pendiente"*. El plan B ya está
    degradado; revivirlo cuesta una corrida completa, no es gratis.
12. **No existe procedimiento de backup en el repo.** Grep de
    `backup`/`mysqldump`/`pg_dump` sobre `app/`, `scripts/`, `docs/`: nada
    operativo. Cualquier migración de datos lo necesita, y es justo cuando
    cambia de herramienta.
13. **Lo ya invertido no se recupera** (fases 1-4 del dual). Costo hundido: no
    debe pesar en la decisión, pero explica por qué "borrar la capa" ahorra poco.

---

## 5. Precondiciones — trabajo previo, no cosecha

Independientes de la opción elegida; varias son bugs latentes hoy:

1. **Hook de GUCs de sesión.** `app/database.py:6-13` llama a `create_engine`
   **sin `connect_args`** y no hay ningún event listener de `connect` (grep de
   `lock_timeout`/`statement_timeout`/`work_mem`: cero hits). Hoy es **imposible
   setear un parámetro de sesión de PG sin tocar `app/database.py`**. Bloquea
   tres palancas: (a) `lock_timeout` — sin él la red de retry queda inerte
   (pérdida #4); (b) `work_mem` — `_load_sweep` hace `ORDER BY date` sobre
   millones de filas por chunk **y por código**; con el default de 4 MB eso es
   un external merge sort a disco garantizado, y es el paso que el propio módulo
   identifica como dominante (`signal_backfill_range.py:266-273`: **158s de
   180s** en `strategy_only`); (c) `max_parallel_workers_per_gather`.
2. **Actualizar `scripts/compare_engines.py` antes de usarlo como gate.**
   `_value_col` (`:76-81`) solo reconoce columnas llamadas `"value"` o
   `"score"`. Las tablas anchas **no tienen ninguna de las dos** (sus columnas
   son los códigos), igual que `prices`, `current_indicator_values`
   (`value_num`/`value_str`) y `group_scores` (`regime_score_d/w/m`): **de los
   indicadores solo se compara el COUNT, nunca los valores**. Además **no mide
   performance**, que es la mitad de lo que el gate pide.
3. **Borrar `set_bulk_load_checks`** (código muerto, 19 líneas) — hoy, en
   cualquier escenario.
4. **`alembic/env.py:26-27`** remite a `tests/test_migration_portability.py`,
   archivo que **no existe** (es `test_bootstrap_portability.py`).
5. **Límite de identificadores 63 (PG) vs 64 (MySQL)** — riesgo bajo hoy, alto
   con el pendiente "indicadores por plantilla". `IndicatorDefinition.code` es
   `String(50)` → `ind_{code}` hasta 54. El índice `ix_ind_{code}_date` llega a
   62 (entra), pero el FOREIGN KEY se declara **sin nombre**
   (`indicator_store.py:188-197`): MySQL lo bautiza `{tabla}_ibfk_1` (61,
   seguro), PG `{tabla}_{columna}_fkey` = hasta **68, que PG trunca en silencio
   a 63**. Dos códigos que compartan los primeros ~45 caracteres colisionarían.
   Hoy el code más largo mide 33. Mitigación barata: `naming_convention` en el
   MetaData (`indicator_store.py:18`, `signal_store.py:42` lo tienen vacío) +
   validar el largo al dar de alta.

---

## 6. Plan — Opción 3: dual asimétrico ~~(recomendada)~~ SUPERSEDED

> ⚠️ **Descartado el 22-jul** al confirmarse que MariaDB no se usa. Se conserva
> por dos motivos: su **etapa B (cosecha)** sigue siendo el contenido de la
> etapa D del plan vigente, y sus gatillos documentan qué habría disparado el
> corte si el motor siguiera vivo.

**Regla:** MySQL queda declarada **rama legacy**: se mantiene funcionando, no se
optimiza más. Toda inversión de performance va a la rama PG detrás del despacho
existente. Escribirlo en el docstring de `db_compat.py` el día 1, junto con los
gatillos de corte.

### 6.1 Gatillos del corte definitivo (sin esto degenera en "dual para siempre con deuda creciente")

El corte se dispara con **cualquiera** de estos cuatro:

1. **Técnico:** la primera optimización que exija tocar el *esquema compartido*
   (particionado, JSONB, citext, `prices` sin `id`, dropear FKs) o que el camino
   genérico no pueda expresar sin cambiar el **resultado** (no la performance).
2. **Operativo:** la instalación MariaDB queda apagada o sin corridas reales
   durante 90 días.
3. **De mantenimiento:** el primer bug que requiera *trabajo* sobre la rama
   MySQL. La regla es "la legacy no se toca nunca más"; el primer arreglo
   necesario **es la señal de corte, no una excepción**.
4. **De medición:** fase 5 ejecutada con paridad OK y PG ≥ 0.7x. Ahí el corte
   pasa a ser puro ahorro y deja de tener riesgo.

### 6.2 Orden de trabajo (cada ítem con bench antes/después, método de 4 pasos)

**Etapa A — precondiciones e higiene** (sección 5; barato, desbloquea el resto):
hook de GUCs de sesión + `lock_timeout` (cierra la red de retry inerte, que es
un bug hoy), `work_mem` en el sweep del backfill, borrar
`set_bulk_load_checks`, arreglar la referencia colgada de `env.py`,
`naming_convention` en los MetaData.

**Etapa B — cosecha PG sin tocar esquema** (el grueso del beneficio):
1. **CLUSTER en vez de VACUUM FULL** (una línea, servicio con botón en la UI).
2. **COPY en escritura**: seam `db_compat.bulk_write(bind, …)` con fallback a
   `upsert_sql`. Orden por volumen: backfill de señales (INSERT plano, rango
   garantizado vacío) → rebuild de indicadores → import de precios.
3. **COPY en lectura** (`COPY … TO STDOUT BINARY`) en `_load_sweep` y las cargas
   de precios del pool.
4. **`fillfactor` 80-85** en las tres tablas anchas (HOT updates en la cola).
5. **UNLOGGED** — solo después de resolver los metadatos que gobiernan los
   deltas y de documentar el runbook de restore. Evaluar antes
   `synchronous_commit=off` por sesión, que da casi lo mismo con menos riesgo.
6. **LATERAL** en los "último por activo".
7. **Índice único funcional `LOWER(username)`** + arreglar `ci_equals` para que
   **no** emita `LOWER()` en MySQL (regresión de perf que el dual introdujo).
8. **`max_parallel_workers_per_gather=0`** en los hijos del pool; paralelismo
   alto solo en las lecturas de un hilo.
9. **Mitigar el DISTINCT sin skip scan** (CTE recursivo) si la medición lo
   confirma como cuello.

**Etapa C — solo si se dispara un gatillo:** particionado, JSONB, `prices` sin
`id`, dropear FKs de `ind_*`, `citext`.

## 7. Plan — Opción 2 (PG-only): **ES EL PLAN VIGENTE**

> ✅ **Elegido el 22-jul.** El esbozo de abajo quedó desactualizado en un punto
> importante —la fase 1 (gate de paridad) **se cancela**, no se ejecuta— y el
> plan detallado, verificado archivo por archivo y ordenado para que la suite
> quede verde en cada commit, vive en **`plan_corte_pg_only.md`**.
>
> Resumen del plan vigente: **etapa 0** (precondiciones en Railway: aplicar la
> 0086, buscar duplicados case-insensitive en `users`) → **A** (bugs vivos:
> `lock_timeout`, login determinista, código muerto — 0,5 sesión) → **B** (el
> corte: 7-8 commits — 1,5-2 sesiones) → **C** (esquema PG-only: `prices` sin
> `id`, índice funcional `LOWER(username)`, FKs de `ind_*` — 1-1,5 sesiones) →
> **D** (cosecha medida, fuera de alcance del plan de corte).

Esbozo original (previo a la respuesta del usuario):

- **Fase 0 — decisión:** confirmar si la instalación MariaDB todavía existe y
  tiene datos que importan. (No es "qué hacemos con la producción MariaDB": la
  producción ya es Railway/PG.)
- **Fase 1 — GATE:** ejecutar la fase 5 del plan dual, **previa actualización
  del comparador** (precondición #2). Criterio: paridad dentro de tolerancia
  float y PG ≥ ~0.7x MySQL en los caminos calientes, o mitigación medida.
- **Fase 2 — datos:** solo si MariaDB vive. Antes: **escribir el procedimiento
  de backup** en `guide_deploy.md` (hoy no existe) y **revisar truncamientos de
  TEXT >64 KB** en las columnas JSON.
- **Fase 3 — corte de código:** el inventario de la sección 2 (incluidos los
  sitios de configuración y `devcontainer.json`, sin los cuales una instalación
  PG-only sin `DATABASE_URL` levanta intentando MySQL). Documentación: además de
  `CLAUDE.md`, **`docs/manual/1060-soporte-dual-de-base-de-datos.md` (237
  líneas)** — no tiene `page:` así que se puede borrar sin romper
  `test_manual_coverage`, **pero 8 capítulos lo enlazan** (1000, 1010, 1020,
  1040, 1050, 1080, 1090, 1095) y `tests/test_manual_coverage.py:118-129` valida
  esos enlaces: **borrarlo sin editar los 8 rompe pytest**. Otros 10 capítulos
  quedarían falsos (1050, 1090, 1095, 1099, `650-centro-de-datos.md:154`), más
  `PROMPT.md:32`, `guide_deploy.md:19,51-59,157-158,205` y `project_overview.md:11`.
  *(El hook `pre-push` solo vigila `MEMORY.md`, `project_*.md` y `feedback_*.md`
  — no los `design_*.md` ni el manual: esta sincronización es manual.)*
- **Fase 4 — cosecha:** la etapa B de la opción 3, más la etapa C.
- **Fase 5 — tests contra PG real** en el Codespace, además de la corrida
  sqlite local.

## 8. Preguntas — RESUELTAS

1. ~~*¿La instalación MariaDB (Apache2 + mod_wsgi) todavía existe y tiene datos
   que importan?*~~ → **NO. Respondido por el usuario el 22-jul: "no se está
   usando, ahora uso Postgres en Railway".** Con eso: desaparece la fase de
   migración de datos, se cancela el gate de paridad, y el corte pasa de
   decisión riesgosa a limpieza de bajo riesgo.
2. ~~*¿Alguna restricción de hosting/costo que haga valiosa la optionalidad
   MySQL?*~~ → Implícitamente no: Railway/PG es el destino elegido.
3. ~~*¿Preferís igual el corte por simplicidad?*~~ → Sí, con la salvedad de que
   **el corte no acelera nada por sí solo**: la performance está en la etapa D.

**Lo único que queda por decidir** (dentro del plan de corte, no antes):
si en la etapa C se dropean las FK `asset_id→assets` de las tablas anchas
—hay que medir el ahorro del trigger RI antes, y la rama PG de `purge_assets`
no está cubierta por la suite—, y si se versiona un procedimiento de backup
(`pg_dump`) en `guide_deploy.md`, que hoy no existe en el repo.

## 9. Correcciones a documentación que este estudio destapó

Independientes de la decisión:

- `CLAUDE.md:81`, `PROMPT.md:32`, `project_overview.md:11` declaran producción
  MySQL/Apache; `guide_deploy.md:16` y `docs/manual/1090` dicen Railway/PG.
- `CLAUDE.md` dice "~740 tests"; el conteo real es 813 `def test_` (886 según
  `project_testing.md` tras la sesión del 21-jul).
- `alembic/env.py:26-27` referencia un archivo de test inexistente.
- `cleanup_service.clean_data:125-139` documenta una garantía transaccional que
  **bajo MySQL es falsa**.
- `docs/manual/1050:227` ya registra `set_bulk_load_checks` como código muerto,
  pero el código sigue ahí.
