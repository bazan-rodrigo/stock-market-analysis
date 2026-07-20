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

## Parte 3 (19-jul-2026) — 7 profilers nuevos + 2 optimizaciones

Commit `b9a0d57` suma 7 scripts al patrón aislado, cubriendo lo que no
tenía profiling: `profile_walk_forward`, `profile_portfolio_backtest`,
`profile_regime_zones`, `profile_fullsample_indicators`,
`profile_fundamental_ratios` (corren LOCAL con datos sintéticos, sin BD) y
`profile_verification`, `profile_pool_batch` (Codespace, datos reales).

**LECCIÓN METODOLÓGICA (la más importante): cProfile infla ~3.7x en este
código.** El lote delta medido daba 69.2s con profiler y **18.7s real**
(`--raw`). Instrumenta cada llamada, así que dispara lo llamado millones de
veces (`pd.notna` aparecía ~12x más caro que su costo real). **La tabla del
profiler sirve para saber DÓNDE mirar, nunca CUÁNTO tarda.** Por eso
`profile_pool_batch.py` tiene el flag `--raw` (wall-clock sin instrumentar):
las optimizaciones se juzgan contra ese número.

**NO medir en Railway:** contenedores efímeros (cambia el hostname en cada
sesión) con CPU asignada variable → comparar corridas de sesiones distintas
es ruido. Además `profile_pool_batch` ESCRIBE (hace backfill real). El
Codespace es el lugar: contenedor estable, git disponible, base descartable.

**Optimizaciones aplicadas:**
- `8a73ca4` — máscara `pd.notna` vectorizada una vez en `_pairs_to_write` y
  `_series_stats` (antes: una llamada escalar por valor de serie, por cada
  activo×código). Medido local: 0.708 → 0.321 ms/serie de 4570 (2.2x).
- `d607273` — `_series_checksum` por bytes crudos: **PROBADO Y REVERTIDO**
  (ver abajo). No queda en el código.

**A/B del checksum: RESUELTO — se revirtió `d607273`.** Se midió con
`scripts/bench_series_checksum.py` (commit `aa3b659`): cronometra AMBAS
implementaciones en el mismo proceso sobre series REALES leídas de la base.
Resuelve el problema de que el A/B por commits exige git + máquina estable
(imposible en Railway). Es solo-lectura y corre en cualquier entorno.

Resultado sobre datos reales (20 y 50 activos, series de 10-13k barras):

| | 20 activos | 50 activos |
|---|---|---|
| numéricas | 1.19x | 1.40x |
| **texto (`trend_*`)** | **0.56x** | **0.52x** |
| ahorro por lote | 0.14 s | 0.44 s |

Contra un lote delta de ~19 s eso es 0.7-2.3%: por debajo del criterio
acordado, así que se revirtió.

**DOS ERRORES QUE VALE NO REPETIR:**

1. **El micro-benchmark sintético mintió por 10x.** Daba 14x; en datos reales
   fue 1.2-1.4x. Las series reales son ~3x más largas (10-13k barras vs 4570)
   y tienen otra estructura de nulos. Un benchmark sintético sirve para
   descartar (si no gana ahí, no gana), NUNCA para confirmar.
2. **"Salida byte-idéntica" ≠ "performance intacta".** El camino de texto
   conservaba el hash exacto, y aun así **regresó ~2x**: la detección de tipo
   `next((v for v in vals if v is not None), None)`, agregada ANTES de ese
   camino, escanea hasta el primer no-nulo — carísimo en series largas y
   mayormente nulas. Al tocar una función con varios caminos, medir TODOS,
   no solo el que se quiso optimizar.

**Hot spots encontrados, sin atacar todavía** (de las corridas sintéticas,
recordar que son magnitudes relativas, no absolutas):
- `build_panels` domina el backtest y `_panels_for_range` lo RECONSTRUYE una
  vez por (ventana × trailing) — 12x en un grid de walk-forward → cachear.
- `run_portfolio_backtest` llama `simulate_topn` 2x (ranking + benchmark EW
  con `top_n=1e9`, que ordena el cross-section entero por fecha) → atajo: si
  `top_n >= len(scores)`, pesos equal-weight sin `sorted`.
- `relative_strength_52w` es ~7x más caro que sus pares full_sample y su
  costo es casi todo Python puro (`toordinal`, `_one_year_before`,
  list-comprehensions) → vectorizable.
- `_compute_regime_zones` y `_confirm_codes` ya están bien vectorizados: NO
  son cuello, descartar esa hipótesis.

**Contraejemplo útil:** vectorizar la máscara en `_series_checksum` (el mismo
patrón que ganó 2.2x en `_pairs_to_write`) lo hacía MÁS LENTO (1.603 → 1.689
ms), porque ahí el chequeo escalar ya era barato (`math.isnan`, C) y el costo
estaba en `str()`; la conversión a array no amortizaba. Dos patrones que
parecen idénticos se comportan al revés → medir siempre antes de optimizar.
