---
name: objetivo-escalado-10000-activos
description: La app debe soportar hasta 10000 activos; hoy se prueba con 500 — guía la prioridad del trabajo de performance en el pipeline de indicadores
metadata: 
  node_type: memory
  type: project
  originSessionId: bade44f4-ff2e-4eca-bcb9-12e503d58c7d
---

El universo de prueba actual es de 500 activos, pero la app debe soportar
hasta 10000 (20x). El usuario pidió explícitamente usar el profiling
aislado (patrón de `scripts/profile_vol_zones.py`, ver [[project_pendientes]])
para bajar al mínimo los tiempos de los procesos pesados del pipeline de
indicadores (backfill/delta), no solo resolver el caso puntual de
volatility_*.

**Why:** a 20x de activos, cualquier costo por-activo que hoy parece
tolerable (segundos) se vuelve significativo (minutos/horas) en el
delta/backfill diario. Los indicadores full_sample (recorren todo el
historial, no solo la cola) son los que más se sienten con el crecimiento
de activos, porque no se benefician del camino rápido tail-mode del delta.

**How to apply:** al proponer optimizaciones de `technical_service.py` o del
pipeline de backfill, priorizar por (a) indicadores full_sample primero
(volatility/atr_percentile, trend, dist_optimal_sma, relative_strength_52w)
y (b) patrones ya identificados como anti-pattern de pandas: reducciones
`axis=1` (`.max(axis=1)`, `.sum(axis=1)`), pasar `pd.Series` a funciones de
numpy (`np.nanpercentile`, etc. — dispara `__array_function__` y cae en la
maquinaria pesada de pandas), loops por zona/fila en vez de vectorizado.
Siempre validar con la suite de pytest (paridad con la referencia JS del
gráfico) antes de dar por buena una optimización.

**Avance (jul-2026, commits ef3c2a4, e45f510, b65e808 — pusheados a
origin/master):** ya resueltos ATR/percentiles de volatility_daily, y
sintéticos completos (`synthetic_service.py` vectorizado + orden topológico
para sintético-de-sintético + descarga YF troceada en chunks de 200
tickers). Ver [[project_pendientes]] para el detalle (fundamental_service.py
ya estaba bien, no requirió cambios).

De paso se encontró y arregló un bug preexistente (commit b65e808): un
sintético tipo `index` calculado en modo incremental (delta, no full) solo
cargaba precios de sus componentes desde `last_date` en adelante (tail-mode),
así que si `base_date` era anterior a esa ventana el precio base no se
encontraba y el componente se excluía en silencio. Se agregó `_anchor_price`
(query liviana e independiente de la ventana tail) para resolver el precio
base real. Ya está corregido y pusheado, no queda pendiente.

**Avance parte 2 (jul-2026, commits 33fe3f0, 8082eba, 2c1ff72, e4c23d5,
f027d10, 53adbf7):** con datos reales (561 activos en el Codespace) el
delta seguía en ~3min pese a los fixes de CPU. Se agregaron
`scripts/profile_current_indicators.py` y `scripts/profile_synthetic_service.py`
(mismo patrón que profile_vol_zones.py) que confirmaron:
- `compute_current_indicators(quick=True)` bajó de 364ms a 124ms/rep
  agrupando los ~11 upserts a `current_indicator_values` en un solo INSERT
  multi-fila (antes uno por código).
- `_ohlc_dict` de sintéticos bajó de 13.5ms a 8.1ms/rep evitando indexar un
  `pd.Index` elemento por elemento dentro de un dict comprehension.
- `compute_synthetic_prices` ya no arma un objeto ORM `Price` por fecha
  (podían ser miles): ahora usa insert en batch (`_bulk_insert_synthetic_prices`,
  mismo criterio que `_upsert_prices` de price_service.py).

**El hallazgo más importante para 10000 activos** salió de mirar
`information_schema.processlist` en vivo durante una corrida real: el delta
seguía tardando ~3min por un `SELECT asset_id, MIN(date), MAX(date), COUNT(*)
FROM ind_{código} GROUP BY asset_id` (`tail_stats` en `backfill_indicator`)
que en la práctica es un full-scan de cada tabla `ind_*` — el `COUNT(*)`
impide el *loose index scan* que `MIN`/`MAX` solos permitirían sobre la PK
`(asset_id, date)`. Corriendo un thread por indicador en paralelo, esto
significaba 24-30 full-scans compitiendo por el mismo disco a la vez. Subir
`_POOL_WORKERS` de cores+2 a cores+6 **empeoró** el delta (3m08s → 3m42s,
el hueco de scheduling creció de ~30s a ~61s), confirmando que el cuello de
botella era contención de I/O, no falta de paralelismo.

**Fix:** `_precompute_all_tail_stats` calcula el `tail_stats` de todos los
códigos tail-mode SECUENCIALMENTE (una sola sesión, antes de lanzar el
pool), y cada worker recibe el suyo ya resuelto en vez de recalcularlo.
`_POOL_WORKERS` vuelto a cores+2. Resultado real: **2m11s** (vs 3m08s
línea base). Este costo escala con el TAMAÑO de cada tabla (activos ×
historial), así que a 10000 activos seguirá creciendo — si en el futuro
esto vuelve a ser el cuello de botella, la palanca siguiente es cachear
`(min, max, count)` incrementalmente en `IndAssetMeta` en vez de recalcularlo
con un scan completo cada corrida (bug/mejora anotada, no implementada:
requiere mantener el cache en sync en cada escritura, más riesgo).

De paso: la consola SQL de administración (`admin_sql_callbacks.py`) no
reconocía `EXPLAIN`/`SHOW`/`DESC` como lectura (solo `SELECT`), así que
`EXPLAIN SELECT ...` se trataba como DML pendiente de commit/rollback sin
mostrar resultado — arreglado (`_is_read_only`).

También se corrigió que la barra de progreso de
`update_indicator_history`/`rebuild_indicator_history` se "reseteaba" al
pasar de la fase de indicadores vigentes a la de backfill histórico (cada
fase reportaba su propio total interno); ahora comparten un total
combinado vía `_run_current_and_backfill`.
