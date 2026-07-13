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
