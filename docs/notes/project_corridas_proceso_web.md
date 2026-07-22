---
name: project-corridas-proceso-web
description: Las corridas del Centro de Datos viven en el proceso web y gunicorn las mataba; ARREGLADO y verificado en Railway. Falta confirmar si el ProcessPool se activó
metadata: 
  node_type: memory
  type: project
  originSessionId: 058bdf43-5053-4c50-8ab6-4687533295a0
  modified: 2026-07-22T16:20:04.022Z
---

22-jul-2026 (commit 00e61da). Una corrida de precios de 1400 activos lanzada
desde el Centro de Datos "desaparecía" sin dejar error al pasar de descargar
precios a calcular indicadores. Causa: esas corridas viven en un thread daemon
DENTRO del proceso web de gunicorn, que tenía `--timeout 120`; la fase de
indicadores es cálculo puro y no le da señales de vida al árbitro, que mata al
worker con SIGKILL (sin traceback, sin log). La descarga sobrevivía por ser I/O
de red. Evidencia: en una corrida que sí terminó, esa fase tardó **113s con 499
activos** — al 94% del presupuesto de 120s. Subido a `--timeout 1800`.

**VERIFICADO EN PRODUCCIÓN (22-jul, 15:45→15:59).** Una *redescarga global*
—el caso más pesado que existe: 3,36M de filas borradas y reinsertadas en
`prices` más rebuild completo de `ind_daily`, 999 activos, 9m55s— completó
entera. Y en `pg_stat_activity` se vio `autovacuum: VACUUM ANALYZE
public.prices` corriendo DURANTE la corrida: evidencia directa de que el xmin
horizon ya no queda fijado. Los `idle in transaction` que quedan son de 11s y
sub-segundo (ciclo normal de cada worker), no los de 7 minutos de antes.

Entorno real de Railway: **8 vCPU y 8 GB** (`os.cpu_count()` reporta 48 — son
los del host, no la cuota del contenedor; leer `/sys/fs/cgroup/cpu.max` y
`memory.max`). PostgreSQL con `max_connections=500`, así que el presupuesto de
conexiones no es restricción para nada acá.

Variables aplicadas en el único servicio (no hay servicio worker; el scheduler
está apagado y la línea `worker:` del Procfile está inerte):

    IND_POOL_MIN_ASSETS=300     # default 1500: con 1400 activos quedaba justo debajo
    IND_POOL_PROCS=4            # explícito; en auto con 48 cores detectados daría 12

**CONFIRMADO (22-jul):** `_use_process_pool(_count_price_assets(get_session()))`
devuelve `(True, 4)` con 499 activos con precios. El pool se activa, así que el
padre ya NO llama a `_load_all_prices` (era el techo de memoria) y el cálculo
pesado sale del proceso web. Esa consulta a la app es la forma barata de
verificarlo sin logs, y confirma de paso que el contenedor ve las variables
(cambiarlas en Railway dispara redeploy: si se cargan después de lanzar una
corrida, esa corrida todavía corre en threads). Con pocas vCPU esto NO acelera
— el objetivo es sacar carga del proceso web. Queda opcional subir a 6-7
procesos si el pico de memoria resulta holgado contra los 8 GB; sin medir.

Si con eso no alcanza, la alternativa es migrar las corridas manuales a
`worker.py`. Eso es un proyecto, no un cambio: el progreso vive en un dict en
memoria (`_state` en data_center_callbacks) con sub-estructura por código, y
`progress_cb` se llama miles de veces por corrida — cruzarlo de proceso exige
cola de trabajos, progreso persistido, despacho en el worker y la UI leyendo de
la base. Diseño NO escrito todavía.

Relacionado: [[project_scaling_target]], [[project_pendientes]].
