---
slug: concurrencia-y-multihilo
title: Concurrencia: hilos, procesos y exclusion mutua
chapter: Anexo tecnico
order: 1050
roles: admin
---

Casi todo el trabajo pesado del sistema es el mismo bucle: recorrer activos, leer
su historia, calcular y escribir. Paralelizarlo parece obvio, pero acá casi
ninguna decisión de concurrencia se tomó por teoría — se tomó midiendo, y varias
veces la medición dijo lo contrario de lo esperado. Hay tres niveles de
paralelismo conviviendo, y encima de todos una capa de exclusión mutua que
garantiza una sola corrida pesada por vez.

## Nivel 1: un ThreadPoolExecutor por activo

El patrón dominante. Seis servicios reparten activos entre hilos, cada uno con
su propia constante:

| Servicio | Constante | Valor |
|---|---|---|
| `price_service.py` | `_UPDATE_WORKERS` | 6 |
| `fundamental_service.py` | `_UPDATE_WORKERS` | 4 |
| `verification_service.py` | `_VERIFY_WORKERS` | 4 |
| `synthetic_service.py` | `_SYN_WORKERS` | 4 |
| `signal_backfill_range.py` | `_READ_WORKERS` | 3 |
| `technical_service.py` | `_POOL_WORKERS` | `max(3, cores + 2)` |

Solo el último se deriva del hardware; la asimetría entre 6 y 4 no está
documentada en el código. Lo que hace funcionar el patrón es `app/database.py`:
la sesión es un `scoped_session`, thread-local sobre un engine único. Cada worker
llama a `get_session()` y hace `Session.remove()` al terminar — sin ese remove la
conexión no vuelve al pool. `synthetic_service` y `price_service` materializan los
pares `(id, ticker)` en el hilo principal antes de lanzar el pool.

> Los objetos ORM no cruzan threads. Tocar un atributo lazy-load desde otro
> worker comparte la misma conexión DBAPI entre hilos, y MySQLdb no es
> thread-safe para eso: corrompe el cursor con "Commands out of sync".

## Nivel 2: el ProcessPool de indicadores

`app/services/process_pool.py` existe y está integrado — expone
`spawn_executable_ok()` y `make_executor()`. Varias notas viejas del proyecto lo
dan por pendiente; están desactualizadas.

Usa contexto **spawn**, nunca fork. El padre (mod_wsgi en producción, el server
de Dash en desarrollo) está lleno de threads: APScheduler, pools de callbacks,
SQLAlchemy. Un fork heredaría locks tomados por otros threads —deadlock clásico—
y los sockets vivos del pool de conexiones, y compartir un socket MySQL/PG entre
padre e hijo corrompe el protocolo. El executor es además **efímero**, uno por
corrida: un pool persistente sobreviviría a los reciclados de mod_wsgi como
procesos huérfanos escribiendo en la base.

`spawn_executable_ok()` devuelve verdadero solo si `sys.executable` parece un
intérprete de Python. Bajo Apache+mod_wsgi embebido apunta a `httpd`, y spawn
lanzaría httpd como intérprete: el pool nacería roto. Ahí `_use_process_pool`
loguea un warning y **degrada a threads** en vez de fallar en silencio. También
degrada con sqlite (spawn no comparte el monkeypatch de la suite, y sqlite con
escritores concurrentes da SQLITE_BUSY) y por debajo del umbral de activos.
MySQL y PostgreSQL comparten el mismo camino de procesos.

### Por qué `process_child.py` vive en la raíz del repo

Parece un archivo suelto mal ubicado; moverlo rompería el pool de conexiones del
hijo en silencio. El bootstrap de spawn **des-picklea la referencia al
initializer antes de ejecutarlo**, y ese unpickle importa su módulo. Desde
`app.*` arrastraría `app/__init__.py` → `app.config`, evaluando `Config` (que lee
`os.environ`) antes de que `child_initializer` setee `DB_POOL_SIZE` — y el hijo
nacería con el pool del padre, 30+20, en vez del pool chico.

> Ese pool chico tiene piso 2, no 1: con `pool=1` la tarea del hijo se
> autodeadlockea contra sí misma, porque necesita dos conexiones a la vez — una
> que la sesión retiene mientras se refleja `ind_{code}` con autoload, y otra
> para leer los precios del lote.

El presupuesto está calculado: N procesos × `IND_CHILD_DB_POOL` más el pool del
padre tienen que entrar en 151 (MySQL) o 100 (PostgreSQL). Con los defaults,
12×2 + 50 = 74 < 100. El cuidado es asimétrico a propósito: en PostgreSQL cada
conexión es un **proceso** del servidor; en MySQL son threads baratos. El detalle
está en [Soportar dos motores de base de datos](/manual/soporte-dual-de-base-de-datos).

### El orquestador compartido

`run_asset_batches` abstrae threads y procesos detrás de la misma interfaz, y lo
consumen la verificación, el backfill fundamental y la fase de vigentes. Llama a
`consume(out, batch)` serializado en el thread del padre vía `as_completed`, así
que los agregados no necesitan lock. `_partition_assets` reparte por rangos
**contiguos** de `asset_id`, no por peso puro:

> Un greedy-LPT balancearía mejor, pero intercalaría vecinos de PK entre lotes.
> Como las tablas tienen PK `(asset_id, date)` y N workers escriben la misma
> tabla a la vez, eso convertiría cada frontera de activo en superficie de
> gap-lock.

El progreso vivo en modo procesos viaja por una `Manager().Queue()`, un proxy
picklable — una `mp.Queue` cruda solo se comparte por herencia, que spawn no da.
Los ticks se batchean cada 50 activos: a 10.000 activos × 24 códigos serían
~240.000 mensajes sin batchear, contra ~4.800 con el batch.

## Nivel 3: productor/escritor con cola acotada

Exclusivo de `signal_backfill_range.py`. Un thread escritor con su propia sesión
consume de una `queue.Queue(maxsize=1)` mientras el productor computa el chunk
siguiente. La cola de uno da backpressure: a lo sumo un lote esperando además del
que se computa. La barrera borrar-antes-de-insertar es **estructural**, no un
lock — limpieza inicial y flushes viven en el mismo thread, en orden FIFO. Y
tras un error el escritor sigue drenando sin escribir, porque con `maxsize=1` un
escritor detenido colgaría al productor para siempre.

## El GIL, medido y no argumentado

`scripts/profile_pool_concurrency.py` corrió los 6 códigos de indicador más
pesados, secuencial contra concurrente (6 threads, cómputo puro, sin tocar la
base): **0.9x de speedup**. Los threads no paralelizan nada; empeoran un poco.
Ese script se escribió porque el intento anterior solo medía secuencial y había
descartado la hipótesis erróneamente. Pero el GIL no es la única causa de que más
paralelismo empeore las cosas.

> Subir `_POOL_WORKERS` de cores+2 a cores+6 empeoró el delta de **3m08s a
> 3m42s**, con el hueco de scheduling creciendo de ~30s a ~61s. La causa no era
> falta de workers sino contención de disco: cada worker disparaba un full-scan
> de `tail_stats`, y más workers eran más full-scans compitiendo por el I/O.

El fix fue menos paralelismo, no más: `_precompute_all_tail_stats` resuelve el
`tail_stats` de todos los códigos **secuencialmente**, en una sola sesión, antes
de lanzar el pool. Resultado: **2m11s** contra 3m08s de línea base. Lo mismo con
los lectores del backfill por rango: paralelizarlos tenía sentido porque la
lectura serial dominaba (158s de 180s en `strategy_only`), pero con 8 la corrida
con señales pasó de **5m10s a 6m50s** —escritor +30%, productor 177s
esperándolo— porque le sacaban CPU y disco al propio MariaDB mientras insertaba.
Se fijó en 3. Donde app y base comparten máquina, sumar lectores es suma cero.
(Otra hipótesis murió midiendo: `innodb_flush_log_at_trx_commit=2` no movió el
delta, 59s contra 62.9s.) La contracara explica por qué los hilos siguen siendo
el patrón dominante:

> El GIL no es una condena acá. El I/O de base **lo libera** —con MySQLdb y con
> psycopg por igual— y pandas/numpy lo liberan en la parte vectorizada. La
> conclusión honesta del código es "threads ganan velocidad real, aunque no al
> nivel de multiprocessing puro", no "threads no sirven".

## Reintentar es parte del contrato

`db_compat.is_retryable_lock_error` centraliza qué error amerita reintentar:
errnos 1205 (lock wait timeout) y 1213 (deadlock found) de MySQL, y los SQLSTATE
40001, 40P01 y 55P03 de PostgreSQL. Lee `.orig` bajo el wrapper de SQLAlchemy y
cubre los tres drivers: MySQLdb señala por errno, psycopg2 por `pgcode` y
psycopg3 por `sqlstate`. Cuatro call sites lo usan, todos con
`_MAX_LOCK_RETRIES = 3` y backoff con jitter: `fundamental_service._fund_worker`,
`fundamental_service._backfill_fund_batch`, `signal_backfill_range._flush` y el
retry por (lote, código) de `_backfill_batch_worker`. Los cuatro reintentan la
transacción completa, idempotente en los cuatro casos.

> Escribir a claves primarias disjuntas no te protege del deadlock. Los threads
> de `_fund_worker` escriben cada uno a un `asset_id` distinto y aun así InnoDB
> deadlockea entre INSERTs concurrentes a la misma tabla, por gap locks y FK
> checks. No hace falta que se pisen filas.

El de `technical_service` hace **siempre rollback antes de decidir**: la
transacción quedó envenenada —en PG cualquier statement posterior daría
`InFailedSqlTransaction`— y el resto de los códigos del lote comparten esa misma
sesión thread-local. Más sobre borrado masivo en
[Deltas, recalculos y borrado masivo](/manual/deltas-y-borrado-masivo).

## Exclusión mutua: `run_lock_service.py`

Las corridas pesadas se excluyen con un lock persistido en base, con heartbeat.
Cierra tres agujeros que un flag en memoria no puede cerrar por diseño:

1. **Doble corrida tras un reciclado del proceso WSGI**: los flags renacen en
   `False` mientras hijos huérfanos siguen escribiendo — dos corridas
   concurrentes contra las mismas tablas, deadlocks garantizados.
2. **La carrera check-then-act** entre dos requests concurrentes.
3. **Distinguir "abortada" de "corriendo"**, para poder destrabar el botón.

La atomicidad se logra **sin SQL de motor**, portable entre MySQL, PostgreSQL y
sqlite: un DELETE condicional del lock muerto más un INSERT atómico por la PK.
Ante dos tomadores concurrentes exactamente uno gana y el otro recibe
`IntegrityError`. No hicieron falta `SELECT ... FOR UPDATE`, advisory locks ni
`GET_LOCK()`. El token de propiedad es único por adquisición
(`secrets.token_hex(8)`), no el pid: en un despliegue de un solo proceso WSGI el
Centro de Datos y el scheduler comparten pid, y un stale-reclaim del mismo pid
dejaría que una corrida vieja pise el lock de la que reclamó. El heartbeat late
cada **30 segundos** y el lock muere a los **120** — cuatro latidos perdidos,
tolerante a pausas de GIL o GC sin dejar el botón trabado eternamente.

Dos detalles del camino de error del propio mecanismo: `release()` hace
`Session.remove()` **antes** del DELETE, porque la sesión pudo quedar envenenada
por la corrida que falló y un `PendingRollbackError` abortaría el DELETE dejando
el lock trabado 120s; y `th.start()` va dentro del try/finally, así que si falla
por agotamiento de threads el finally igual libera. Hay **una sola op**,
`HEAVY_WRITE`: Centro de Datos, botones de precios y corrida nocturna son
mutuamente excluyentes entre todos. (El docstring del modelo `RunLock` sugiere una
op por operación; el diseño evolucionó a un lock único y ese comentario no
acompañó.)

> El lock es **fail-open**. Si la tabla `run_lock` no existe o la base está
> caída, `guarded_acquire` devuelve el sentinel `NO_LOCK` y la corrida procede
> sin exclusión mutua. Es deliberado —mantiene la feature puramente aditiva— pero
> significa que en un deploy sin la migración 0076 la protección no está.

Si la tabla falta, el módulo **latchea** `_unavailable` para todo el proceso en
vez de reintentar en cada acquire: una corrida entera martillaría la base con
queries a una tabla inexistente, que PostgreSQL además loguea como ERROR una por
una. Latchea solo ante "tabla ausente"; los errores de conexión sí se reintentan.
El GIL asoma incluso en el scheduler: el job diario sobreescribe
`misfire_grace_time` a 3600, porque el default de 1 segundo saltea el job en
silencio si el timer despierta tarde — normal con pools GIL-bound. Del lado del
usuario, todo esto produce el mensaje "Ya hay una corrida en curso"
([Solución de problemas](/manual/solucion-de-problemas)).

## Deuda técnica conocida

**El ProcessPool nunca se ejercitó a escala real.** El umbral de activación es
1500 activos y el universo del proyecto es ~561, así que toda corrida real cae al
camino de threads. El código está escrito, testeado con un executor inline y
commiteado, pero el spawn real nunca corrió contra una base viva. Para forzarlo
hay que bajar `ind_pool_min_assets`. Consecuencia directa: **no hay ninguna
medición del ProcessPool contra la línea base de 2m11s**, así que cualquier
número sobre cuánto mejora sería inventado. Ver
[Estado, límites y deuda técnica](/manual/estado-y-limites-conocidos).

Queda además una brecha medida sin explicar: incluso con el factor GIL
confirmado, `volatility_daily` sola tardaba 53-63s de pared con solo ~2s de
cómputo puro. Un 30x que el GIL no alcanza a explicar, y nunca se aisló si el
resto es el commit a la base, el lock del contador de progreso u otra cosa.
`db_compat.set_bulk_load_checks` quedó como código muerto: desactivar
`foreign_key_checks` en el rebuild se revirtió por un bug de afinidad de conexión
—los commits por volumen devolvían la conexión al pool compartido con los checks
apagados— y la función sigue existiendo, con tests, pero sin ningún call site.

El dominio tiene **67 tests** en seis archivos, sobre una suite total de **822**.
El camino de procesos se valida con un `_InlineExecutor` falso que corre la tarea
del hijo en el proceso del test pero hace round-trip de pickle sobre el resultado
— la única forma de atrapar un DataFrame colado en el dict de retorno sin
depender de un spawn real. Ver
[Cómo se prueba y cómo se mide](/manual/pruebas-y-medicion).
