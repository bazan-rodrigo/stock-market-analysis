---
name: processpool-particion-por-activos
description: "Diseño elegido para escalar el backfill de indicadores: ProcessPoolExecutor particionando por ACTIVOS (no por indicador); se encara junto con la migración a PostgreSQL, sin fecha"
metadata: 
  node_type: memory
  type: project
  originSessionId: 5559d8c9-e98c-4f69-a01f-04bf194ffc36
---

**Decisión (12-jul-2026):** la migración del pool de indicadores de
`ThreadPoolExecutor` a `ProcessPoolExecutor` se encara **junto con la
migración a PostgreSQL** ([[postgresql-migracion-futura]]), más adelante,
sin fecha. El diseño ya quedó elegido: **particionar por activos, no por
indicador**.

**Why (dos problemas, una solución):**
1. **GIL confirmado** como cuello de botella del pool actual
   (`profile_pool_concurrency.py`: speedup 0.9x con 6 threads — los
   threads no paralelizan el cómputo pandas/numpy).
2. **El caché en memoria no escala a 10k activos**
   ([[objetivo-10000-activos]]): `_load_all_prices` +
   `df_w_cache`/`df_m_cache` cargan TODA la tabla `prices` en DataFrames
   (~300 MB con 550 activos hoy; estimado ~5-6 GB de pico con 10k) — no
   entra en un Codespace de 8 GB.

**How to apply (el diseño elegido):** hoy el pool es un worker por
indicador (36 workers compartiendo el caché completo). Invertir el eje:
cada proceso recibe un LOTE de activos (~500), carga solo los precios de
su lote, calcula los 36 indicadores para esos activos, escribe y libera.
- Ningún proceso supera el footprint que hoy ya funciona (~300 MB).
- Desaparece el caché compartido que bloqueaba la migración a procesos
  (no hay nada que serializar entre procesos).
- Sin GIL entre procesos: el cómputo paraleliza de verdad.

Detalles abiertos a resolver cuando se encare:
- Benchmarks compartidos entre lotes (`relative_strength_52w` necesita el
  df del benchmark, que puede caer en otro lote).
- El scheduling LPT (`last_backfill_seconds`/`last_rebuild_seconds`) hoy
  es por indicador; con partición por activos cambia la unidad de trabajo.
- Contador de progreso/`progress_cb` entre procesos (hoy usa un lock de
  threads).
- Sesión de BD propia por proceso + reintentos ante deadlocks (patrón ya
  existente en `_fund_worker`).
- Replicar el criterio en `backfill_all_fundamental_values` (mismo GIL).

Nota: el backfill de señales (`signal_service`) NO tiene este problema —
cada fecha es autocontenida (lee de la BD lo que necesita, sin caché
compartido entre fechas); si algún día hiciera falta, se paraleliza por
fechas con procesos sin rediseño.

**Correcciones al diseño (17-jul-2026, mapeo verificado contra el código):**
- El pool de backfill tiene **24 códigos** (`_BACKFILL_FNS`), no 36 — el 36
  es la unión con los 12 current-only de la fase de vigentes. El contrato
  del hijo es "lote de activos × 24 códigos".
- **Lote fijo de ~500 degenera hoy**: con 561 activos serían 1-2 procesos
  (regresión vs 24 threads). El tamaño de lote debe derivarse de
  n_assets/n_procesos, con fallback a threads para universos chicos.
- **Migrar solo el backfill NO resuelve el objetivo de memoria**: la fase
  de vigentes (`_run_current_and_backfill`) sigue cargando toda la tabla
  prices en el padre (`_load_all_prices` + `close_cache` full-history).
- El TRUNCATE del force vive DENTRO del worker por código
  (`backfill_indicator` ~1390): con partición por activos hay que izarlo
  al padre. Ídem en fundamental (`~953-956`, `~1088-1092`).
- El universo a dimensionar incluye los sintéticos de conversión de moneda
  (~2x los activos reales con 1 divisor por moneda): 10k reales ≈ 20k en
  el pool.
- Start method: **spawn/forkserver casi obligatorio** (mod_wsgi
  multi-thread + engine global import-time en `app/database.py`;
  `max_tasks_per_child` requiere spawn y Python ≥3.11 — verificar prod).
- Tests: el monkeypatch no cruza a un hijo spawn y sqlite-archivo da
  SQLITE_BUSY → hace falta modo inline para sqlite/tests (patrón
  `use_async` de `signal_backfill_range`) y conservar los seams de
  `test_indicator_pipeline_order.py`.

Plan de implementación por etapas (aprobado 17-jul): 1) unidad por-lote en
threads, 2) ProcessPool spawn con initializer + sizing adaptativo
configurable, 3) progreso vía Queue+thread bomba (molde de etapas de
señales), 3.5) lock de corrida persistido en BD con heartbeat + misfire
explícito de APScheduler (el usuario lo pidió DENTRO del alcance),
4) medir en Codespace vs baseline 2m11s, 5) diferidos: fase de vigentes
(memoria del padre), fundamental, verification; señales/estrategias NO
migran (read-bound medido) pero reutilizarían el harness por FECHAS si
compute_s pasara a dominar. Indicadores dinámicos de usuario: cubiertos
con el seam _resolve_backfill_fn (specs como datos, DDL solo en el padre).

**ETAPA 1 IMPLEMENTADA (17-jul, commit 78bdb8a, pusheado):** eje invertido
en threads — _backfill_batch_worker (lote × 24 códigos, contrato
picklable-ready, retry 1205/1213 con rollback+backoff), backfill_indicator
con asset_ids/skip_force_reset/defer_meta, TRUNCATE izado al padre
(_force_reset_ind_tables, códigos con reset fallido se excluyen),
_partition_assets por rangos CONTIGUOS de asset_id (menos gap locks),
consolidación de ind_asset_meta/diagnósticos en el padre con
try/except por código, errors deduplicado, panel con dn monotónico y fila
final t= por código. 14 tests nuevos en tests/test_indicator_batching.py
(equivalencia multi-lote ≡ lote único sobre sqlite incluida); suite 559
passed. La revisión adversarial (workflow) encontró y se arreglaron:
sesión envenenada sin rollback, falta de retry multi-escritor,
consolidación sin try/except, inflación de errors. Trade-off documentado:
el rebuild deja TODAS las tablas ind_* vacías durante la corrida (antes:
solo las de códigos en vuelo).

**ETAPA 2 IMPLEMENTADA (17-jul, sin commitear aún al escribir esto):**
ProcessPool spawn efímero. Piezas: `process_child.py` (raíz del repo, FUERA
de `app` a propósito — su unpickle no debe importar app.config o el env del
pool de BD llegaría tarde), `app/services/process_pool.py` (make_executor +
spawn_executable_ok), en technical_service `_process_batch_task` (task del
hijo: carga precios de su lote + benchmarks, resamplea local, delega en
_backfill_batch_worker, nunca deja escapar excepción), `_load_prices_for_assets`,
`_count_price_assets`, `_use_process_pool`/`_resolve_pool_procs`, drain
unificado threads/procesos con BrokenProcessPool. Config nueva:
ind_pool_procs (0=auto cores-1), ind_pool_max_procs (12, cap del auto por
presupuesto de conexiones), ind_pool_min_assets (1500), ind_child_db_pool
(2, piso forzado en el initializer). Selección: sqlite→threads siempre;
mod_wsgi con sys.executable≠python→threads (degradación, no falla);
universo<umbral→threads. En modo procesos `_run_current_and_backfill`
libera el price_cache del padre antes del pool. 33 tests (equivalencia
threads≡procesos-inline con round-trip de pickle real). Suite 567 passed.

**PENDIENTE verificar en Codespace (MariaDB, 561 activos < umbral → correrá
en THREADS; para forzar procesos: ind_pool_min_assets=100 e
ind_pool_procs=2):** delta y rebuild reales, que el hijo cargue bien sus
precios+benchmarks, contención entre lotes, tiempo vs 2m11s, y CONFIRMAR
que el pool de BD del hijo es 2 (SHOW PROCESSLIST) — el fix del timing del
env solo se valida con spawn real.

**ETAPA 3 IMPLEMENTADA (commit e90b955, pusheada):** progreso VIVO por
activo en modo procesos vía Queue IPC (Manager proxy) + thread bomba en el
padre; ticks batcheados por el hijo (_TICK_FLUSH=50). El canal solo se arma
si hay progress_cb (el job diario desatendido no levanta Manager). _bump
compartido threads/procesos; _advance_batch eliminado. Cleanup del canal
con try/except por paso. La revisión adversarial confirmó y se arreglaron
esos dos (canal sin progress_cb, cleanup sin proteger).

**LAS 4 ETAPAS COMMITEADAS Y PUSHEADAS (17-jul):** etapa 1 (78bdb8a),
etapa 2 (1d41d73), etapa 3 (e90b955), etapa 3.5 (4eca4ed). Cada una con
revisión adversarial por workflow y fixes aplicados. Suite 589 passed.
PENDIENTE GLOBAL: verificar en Codespace/Railway con la app viva (correr
migración 0076; forzar procesos con ind_pool_min_assets=100 e
ind_pool_procs=2; medir vs baseline 2m11s).

**AVANCE 19-jul (etapa 4 ya verificada por el usuario; sobre modelo ANCHO):**
- BUG bulk-checks ARREGLADO (commit 17a5df9): se quitó el toggle de
  FK/unique en el rebuild (las tablas ya se vacían antes → no aporta). Solo
  afectaba MariaDB (no-op en PG). db_compat.set_bulk_load_checks sigue (lo
  usa fundamental).
- ETAPA 5 — VERIFICACIÓN migrada a lotes/procesos (commit 7cee5dc):
  run_verification/run_fund_verification pasan de submit-por-activo a
  submit-por-LOTE reusando el harness (_use_process_pool/_partition_assets/
  make_executor). _verify_batch/_verify_fund_batch + _run_batched;
  _verify_one_asset/_verify_one_fund_asset con session=None (el lote
  administra la sesión). Auto-review (los workers de review se cortaron por
  límite de sesión, revisé yo) encontró y ARREGLÉ: los lotes NO deben tragar
  excepciones (si no, update_flags_for_assets borra la marca de activos no
  verificados por un fallo silencioso) → propagan y cortan la corrida como el
  código viejo; + regime/vol config pre-asegurados en el padre (carrera de
  creación del default entre lotes). Tests: equivalencia lote≡por-activo +
  orquestador threads≡procesos-inline. Suite 700. PENDIENTE: spawn real en
  Codespace a 10k activos (a 561 corre en threads).
- FUNDAMENTAL — HECHO (19-jul, CON revisión adversarial): `backfill_all_fundamental_values`
  reejado de "1 thread por código" a "1 lote de activos (todos los códigos)".
  Enfoque SEGURO (no reescribe la lógica delta/wide): `_backfill_fund_batch`
  (unidad auto-contenida, picklable, carga su slice de quarters/precios) llama a
  `_backfill_fund_indicator`/`_backfill_fund_daily_all` ESCOPADOS al lote (agregué
  `skip_force_reset` a ambas). TRUNCATE izado al padre (`_fund_force_reset`,
  wipe_table portable). Retry 1205/1213 por lote; NO propaga (resiliente, re-corrible
  por delta) + `_drain` atrapa BrokenProcessPool como technical_service. Bug espejo
  del bulk-check ELIMINADO. Endurecí `_load_fund_prices` (coerción date, arreglaba
  fragilidad sqlite latente de recompute_all_ratios también). Tests nuevos
  (test_fundamental_batching.py, 4): partición-independiente, DELTA gap-filling real,
  cobertura procesos-inline≡un-lote, universo-vacío. 3 revisores adversarios
  (equivalencia/concurrencia/integración): SIN hallazgos ALTA, equivalencia de datos
  confirmada; arreglé F1 (BrokenProcessPool), F3 (wipe portable), test de delta real,
  test-vacío determinista, comentarios stale. Suite 705. PENDIENTE: spawn real en
  Codespace a 10k (a 561 corre en threads).
- FASE DE VIGENTES — HECHO (19-jul, CON revisión workflow): `recompute_current_indicators`
  reejada a lote-de-activos. `_current_batch` computa los 12 _CURRENT_ONLY_CODES para su
  slice reusando `_compute_current_indicator` por código (savepoints + error_collector
  intactos). Cross-asset (benchmark) los trae `_load_prices_for_assets` (ya existía).
  Dos modos de caches (patrón price_cache del backfill): PROCESOS self-load (`_load_prices_for_assets`
  + `_derive_recent_caches`) → **cierra el techo de memoria del padre**; THREADS reciben
  `preloaded` (el padre deriva UNA vez y comparte por referencia, sin relectura). `_run_current_and_backfill`
  en procesos ya NO carga la tabla entera (universo/pesos por `_load_price_weights`). Pre-asegura
  regime/vol/sr en el padre (carrera). `_drain` marca lote muerto sin avanzar progreso (como
  el backfill). Borré `_load_recent_prices` (código muerto). Tests: test_current_batching.py (5:
  partición-independiente, threads+log, procesos-inline≡threads, preloaded≡self-load, vacío) +
  pipeline_order actualizado. Revisión workflow (10 agentes, find→verify): sin ALTA; arreglé el
  MEDIA (relectura redundante en threads → rama preloaded) + 4 BAJA. Suite 710. Spawn real a escala VERIFICADO en Codespace (19-jul, "probado").
  **ETAPA 5 COMPLETA Y VERIFICADA** (verificación + fundamental + vigentes + backfill).
  El plan ProcessPool entero está CERRADO — nada pendiente de este workstream.
- DEUDA TÉCNICA del batching — LIMPIADA (19-jul, commit a22f16b, revisado por workflow,
  sin ALTA/MEDIA): (#1) `run_asset_batches` helper compartido (particiona+pool+drain+
  consume serializado+on_dead) adoptado en verificación/fundamental/vigentes (el backfill
  de indicadores conserva su loop por el IPC de progreso vivo); (#2) `_save_indicator_logs_bulk`
  = indicator_update_log en UN commit (antes 1 por activo); (#3) `_backfill_fund_quarterly_all`
  espejo del daily → _compute_quarterly_ratios 1×/trimestre (8× menos cómputo) + fila ancha
  completa (sin bloat por-columna); se borró `_backfill_fund_indicator` (sin callers). Suite 714.

**RESUELTO — el modelo cambió a TABLAS ANCHAS (18-jul, OTRA sesión):** lo
que yo anoté como "dependencia, esperar la decisión" YA se decidió e
implementó en otra sesión. Los 24 `ind_{code}` fueron DROPEADOS y
reemplazados por 3 tablas anchas por cadencia (ind_daily/weekly/monthly, una
COLUMNA por indicador, una FILA por activo/fecha). Commits: 776969e (fases
1-3, flag OFF), 6acd3b8 (cutover fase 4 + migración 0078), db60b38 (merge en
Python sin bloat), 9b1a700 (fase 5: drop de las 24 tablas, wide por
default), ab4d68f (rebuild sin bloat con buffer de fila completa), 2cb0716
(VACUUM FULL/OPTIMIZE). Flag `use_wide_ind_tables()` en indicator_store
(`_WIDE`, `_WIDE_CADENCE_TABLE/_COLUMNS`, `_get_wide_table`).

**El ProcessPool SOBREVIVIÓ y quedó integrado**: `_backfill_batch_worker`,
`_process_batch_task`, `backfill_indicator`, `_force_reset_ind_tables` siguen;
la otra sesión hizo `_write_ind_series` wide-aware (`_null_wide_column`,
`_wide_buffer_*`) y `_force_reset` con `wide_on`. O sea, el harness + la
unidad de trabajo se mantuvieron; solo el destino de escritura cambió de
tabla-por-código a columna-en-tabla-ancha. → Los diferidos de la etapa 5 y
la verificación (etapa 4) ahora corren sobre el modelo ancho, sin el rework
que yo temía. **A VERIFICAR** cuando se retome: el `_wide_buffer_*` (buffer
de fila completa para evitar bloat) es estado de módulo — en modo PROCESOS
cada hijo tendría su propio buffer (ok si se arranca dentro del worker, mal
si lo arranca el padre). Confirmar que el buffer se inicia por hijo. Ver
[[objetivo-10000-activos]] y docs/notes/design_ind_wide_tables.md.

**CONTEXTO DEPLOY (importante): el usuario despliega en RAILWAY con
gunicorn** (commits 777a4ba Procfile+gunicorn, 847c6eb normalize
postgres://) → **MULTI-WORKER, no el mod_wsgi de un solo proceso**. Implica:
(a) cada worker de gunicorn corre su propio APScheduler → el job diario
podría dispararse en varios workers; el lock persistido HEAVY_WRITE ahora
garantiza que solo uno corra (valor real del cross-proceso). (b) PostgreSQL
en Railway con max_connections limitado → el cap ind_pool_max_procs=12 y el
pool chico del hijo importan. (c) FOLLOW-UP HECHO (commit 26647c0): los 4
botones de la PANTALLA DE PRECIOS ahora toman HEAVY_WRITE (background vía
_launch_locked_bg; update_one síncrona con acquire+release), refusan con
'ocupado' si otra corrida tiene el lock. Cerró también una asimetría
pre-existente (la pantalla de Precios no chequeaba nada antes).

**ETAPA 3.5 (detalle):** lock de corrida
PERSISTIDO con heartbeat. Nuevo: app/models/run_lock.py (RunLock: op PK,
pid, host, started_at, heartbeat), app/services/run_lock_service.py
(acquire atómico por PK = DELETE de muerto por heartbeat<cutoff + INSERT;
beat/release por pid propio; guarded_acquire fail-open; heartbeating context
manager; HEAVY_WRITE='heavy_write', HEARTBEAT=30s, STALE=120s), migración
PORTABLE 0076 (primera post-freeze), tests. Integración: scheduler
_daily_update_job toma el lock (saltea si otro corre) + heartbeating +
misfire_grace_time=3600/coalesce/max_instances=1 en los add_job; Centro de
Datos _start* con gate 'if _any_running() or not guarded_acquire(): BUSY' y
_run envuelve service_fn en heartbeating; clear_stale al arranque. Cierra:
doble corrida tras reciclado con hijos huérfanos, carrera check-then-act de
_any_running, misfire silencioso de APScheduler. Fail-open = aditivo (sin la
tabla, todo funciona igual que antes). PENDIENTE: correr migración 0076 en
Codespace y verificar el gate + heartbeat con la app viva. NOTA de alcance:
los botones de la PANTALLA DE PRECIOS (price_callbacks) NO toman el lock —
en proceso único los cubre _any_running en memoria; extender a
price_callbacks queda para después si se va a multi-proceso.

**BUG PRE-EXISTENTE detectado (NO arreglado, viene de fase 1 / diseño
viejo — orthogonal al ProcessPool):** `_set_bulk_load_checks(session,False)`
en `_backfill_batch_worker` bajo force+THREADS setea SET SESSION
foreign_key_checks=0 sobre la conexión vigente, pero los commits por chunk
devuelven esa conexión al pool COMPARTIDO con checks apagados; el restore
del finally aplica sobre otra conexión. Riesgo: un rebuild force con la app
en uso puede dejar conexiones del pool sirviendo requests ABM sin
validación FK/unique. Solo modo threads (procesos usa pool efímero que
muere con el hijo). Fix real = fijar una conexión para el worker, en
tensión con los commits periódicos (undo log) → cambio aparte, con su
verificación. Mismo patrón a revisar en fundamental_service.
