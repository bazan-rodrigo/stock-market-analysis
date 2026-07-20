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
  activo×código). **QUEDA, validado sobre datos reales** con
  `scripts/bench_pairs_to_write.py` (commit `09b6421`): ningún modo
  regresiona. `_series_stats` 1.60-1.82x; `_pairs_to_write` 1.42-1.55x
  (None), 1.43-1.47x (set), 1.26-1.34x (dict).
  Ahorro real por lote ≈ **4.3-5.0 s** — NO se suman los tres modos de
  `_pairs_to_write` (en cada llamada corre uno solo): es `_series_stats` +
  UN modo. Contra un lote delta de ~19 s eso es **~25%**. De hecho los
  18.7 s medidos con `--raw` ya incluían esta optimización; sin ella el
  lote daba ~24 s.
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

   **REGLA que sale de comparar los dos casos** (`8a73ca4` ganó 1.3-1.8x en
   datos reales; `d607273` no ganó nada y regresionó): vectorizar paga cuando
   la operación por elemento es un DISPATCH CARO (`pd.notna(v)` cuesta ~1.3 µs
   de maquinaria pandas), y NO paga cuando ya es una operación C barata
   (`isinstance` + `math.isnan`) — ahí la conversión de lista a array de numpy
   cuesta más que lo que ahorra. Antes de vectorizar, preguntarse qué se está
   reemplazando.
2. **"Salida byte-idéntica" ≠ "performance intacta".** El camino de texto
   conservaba el hash exacto, y aun así **regresó ~2x**: la detección de tipo
   `next((v for v in vals if v is not None), None)`, agregada ANTES de ese
   camino, escanea hasta el primer no-nulo — carísimo en series largas y
   mayormente nulas. Al tocar una función con varios caminos, medir TODOS,
   no solo el que se quiso optimizar.

## Parte 4 (19-jul-2026) — verificación vectorizada + bloat del delta

**`c589a6e` — `verify_asset_code` vectorizado: QUEDA, validado sobre datos
reales** con `scripts/bench_verify_asset_code.py`. La comparación
fresco-vs-guardado llamaba `_values_equal` y `check_sanity` una vez POR FECHA
(~48k llamadas escalares por código en una serie de 16k barras), casi todas
para descubrir que no hay ninguna diferencia. Ahora se resuelve con máscaras
de array (`_diff_masks`) y, si no hay diffs ni fechas faltantes, se evita
recorrer la serie entera. Medido en la base real (BA, 16.243 barras), con las
24 listas de diffs **idénticas**:

- **La comparación sola: 144 → 65 ms = 2.23x** (`bench_verify_asset_code.py`).
- **La función completa: 267.8 → 188.8 ms = 1.42x.** El end-to-end nuevo se
  midió con `profile_verification.py BA --raw`; el viejo se despeja sin hacer
  checkout: `compute_fn = 188.8 − 65 = 123.8 ms` (no cambió), luego
  `viejo = 123.8 + 144 = 267.8 ms`.
- A 10.000 activos single-thread: **~45 min → ~31 min** (ahorro ~13 min).

**CORRECCIÓN de un overclaim propio:** se había dicho "la comparación es ~85%
del costo de `verify_asset_code`" y de ahí "24 min → 11 min". Ese 85% salía de
la tabla de cProfile y estaba inflado: la comparación hacía millones de
llamadas instrumentadas y `compute_fn` órdenes de magnitud menos, así que el
profiler exageró su peso. Real: **~54%**.

**Chequeo cruzado del factor de inflación:** el profiler daba 1113 ms para
esta función; real 268 ms = **4.2x**. Coincide con el **3.7x** medido
independientemente en el lote del pool (69.2s con profiler vs 18.7s raw). Dos
mediciones distintas convergen en el mismo orden de distorsión.

**`2a4ed68` — bloat del delta.** El buffer de escritura ancha (fila completa
en vez de un UPDATE por columna) sólo se activaba en rebuild; el comentario
asumía que el bloat del delta era chico. Medido: **51.1% de tuplas muertas en
`ind_daily`** (1.08M muertas vs 1.03M vivas) — un backfill masivo corre como
delta pero escribe la serie entera columna por columna, y con 14 columnas son
hasta 13 versiones muertas por fila. En `pg_stat_activity` los INSERT salían
con `wait_event=ClientRead`: la base esperando al cliente, o sea el costo
estaba en el ida y vuelta por statement, no en disco.
Requirió arreglar antes `_wide_buffer_flush`, que volcaba SIEMPRE todas las
columnas de la cadencia con None en las ausentes: en delta eso habría escrito
NULL sobre valores guardados. Ahora agrupa por el conjunto de columnas real.
**CONFIRMADO en la base real.** Con 144 activos en `ind_daily`, un delta
—que siempre recalcula la última fecha, o sea toca una fila por activo—
hizo crecer `n_tup_upd` en exactamente **+144**: UN update por fila. Con el
código viejo habrían sido ~14 por fila (una por columna de la cadencia) ≈
2.000. **~14x menos actualizaciones de fila en el camino delta.**

**Cómo medirlo (técnica reusable):** NO usar `n_dead_tup`/`pct_muertas` —
el autovacuum lo resetea entre la corrida y la medición y da 0% aunque el
problema siga. Usar `n_tup_upd` de `pg_stat_user_tables`, que es acumulado
y no se resetea: tomar la lectura antes del delta, correrlo, y comparar
cuánto creció contra la cantidad de filas tocadas. La proporción
update/fila es la que delata el patrón columna-por-columna.
También: 187 MB para 1,03M filas × 14 columnas es el tamaño esperable
(~144 bytes/fila + índice de la PK), no bloat — no hizo falta VACUUM FULL.

**`5690052` — pytest podía vaciar la base real.** `conftest` usaba
`os.environ.setdefault("DATABASE_URL", stub)`: con una URL real en el entorno
la respetaba y la suite corría contra ESA base (varios fixtures hacen
`DELETE FROM assets`, y prices e `ind_*` tienen ON DELETE CASCADE). Pasó de
verdad — la tabla `ind_zz_test_explorer` en Railway sólo puede haberla creado
pytest. Ahora la URL se fuerza y un hook `pytest_sessionstart` aborta si el
engine no es sqlite.

**LECCIÓN sobre benchmarks sintéticos.** Hoy fallaron 3 veces, SIEMPRE por
optimistas (el "23%" leído del profiler, el 14x del checksum, la hipótesis de
que `None` explicaba la regresión). La excepción fue `verify_asset_code`:
el sintético dio 1.23x y la realidad 2.23x. La diferencia es que ahí se midió
a propósito el PEOR caso (sin datos guardados, el atajo nunca dispara) en vez
de un escenario favorable. **Regla: si se usa un benchmark sintético, que
modele el peor caso** — así sólo puede sorprender para bien.

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
