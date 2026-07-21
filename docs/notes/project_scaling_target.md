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
  `_series_stats`. **QUEDA, validado sobre datos reales** con
  `scripts/bench_pairs_to_write.py` (`09b6421`): ningún modo regresiona.
  `_series_stats` 1.60-1.82x; `_pairs_to_write` 1.42-1.55x (None), 1.43-1.47x
  (set), 1.26-1.34x (dict). Ahorro real ≈ **4.3-5.0 s por lote** — NO sumar
  los tres modos (en cada llamada corre uno solo): es `_series_stats` + UN
  modo. Contra un lote delta de ~19 s eso es **~25%**; los 18.7 s medidos con
  `--raw` ya lo incluían (sin la optimización el lote daba ~24 s).
- `d607273` — `_series_checksum` por bytes crudos: **PROBADO Y REVERTIDO**
  (ver abajo). No queda en el código.

**A/B del checksum: RESUELTO — se revirtió `d607273`.** Se midió con
`scripts/bench_series_checksum.py` (commit `aa3b659`): cronometra AMBAS
implementaciones en el mismo proceso sobre series REALES leídas de la base.
Resuelve el problema de que el A/B por commits exige git + máquina estable
(imposible en Railway). Es solo-lectura y corre en cualquier entorno — el
patrón a reusar para cualquier duda "¿esta optimización se nota de verdad?".

Resultado sobre datos reales (20 y 50 activos, series de 10-13k barras):
numéricas 1.19-1.40x, **texto (`trend_*`) 0.52-0.56x (REGRESIÓN)**, ahorro
total 0.14-0.44 s contra un lote delta de ~19 s = 0.7-2.3%. Por debajo del
criterio acordado.

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

   **SEGUNDA CONFIRMACIÓN de la regla (y van 2):** se intentó vectorizar las
   conversiones de fecha de `_bf_relative_strength_52w`
   (`[d.toordinal() for d in dates]` y el loop de `_one_year_before`, que el
   profile mostraba como 180k + 60k llamadas por activo). Medido sobre datos
   reales: **1.58 → 3.33 ms, o sea 2x MÁS LENTO**, y las conversiones eran
   apenas el **7%** de la función → end-to-end 0.93x. **Revertido.**
   `date.toordinal()` es un método C barato, del lado de `math.isnan` y no del
   de `pd.notna`; encima `pd.to_datetime` sobre un DataFrame year/month/day es
   caro. La regla lo predecía y NO se aplicó: se decidió por el conteo de
   llamadas del profiler, que es justo la métrica que cProfile infla.

   **HEURÍSTICA MÁS FUERTE, del score completo del día** (3 ganadas,
   2 perdidas): **eliminar TRABAJO gana siempre; re-expresar trabajo solo gana
   si lo que se reemplaza es caro.**
   - Ganaron: buffer del delta (13 updates → 1, **14x**), `verify_asset_code`
     (evita recorrer 16k fechas cuando no hay diffs, 1.42x), máscara `notna`
     (elimina dispatch caro, 1.3-1.8x).
   - Perdieron: checksum por bytes y `toordinal` vectorizado — ambos
     re-expresaban operaciones C que ya eran baratas.

   Corolario para los leads que quedan: el atajo de `simulate_topn`
   (`top_n >= len(scores)` → equal-weight sin `sorted`) y el caché de
   `build_panels` (que hoy se reconstruye 12x en el grid) son del tipo
   ELIMINAR TRABAJO, no del tipo re-expresar. Son los candidatos con mejor
   pronóstico.
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

## Parte 5 (19-jul-2026) — el bloat real estaba en el backfill POR ACTIVO

**`backfill_asset_history` era la fuente principal del 51%, no el camino que
se había arreglado primero.** Tiene SEIS callers y está en los caminos vivos:
`price_service.py:199,361,460` (tras CADA descarga de precios),
`price_callbacks.py:291`, `synthetic_service.py:287`. No pasaba por el buffer
—`_wide_buffer_start()` se llamaba en UN solo lugar, `_backfill_batch_worker`.

Y el problema no eran solo las escrituras: con `existing=None`,
`_write_ind_series` llama `_null_wide_column` POR CÓDIGO — un UPDATE que pone
esa columna en NULL sobre TODA la historia del activo. Con 14 columnas son
**~28 versiones de fila por cada fila de historia** (14 nulls + 14 escrituras).
Un activo de 16k barras genera ~450k versiones; por 144 activos, decenas de
millones. **Bufferizar solo las escrituras habría arreglado la mitad.**

Fix (`ea5d632`): si los códigos cubren TODAS las columnas de una cadencia
(verificado: daily 14/14, weekly 5/5, monthly 5/5), se borran las filas del
activo de esa cadencia UNA vez y las escrituras se bufferizan para volcar fila
completa → inserts puros. La cobertura se chequea EN RUNTIME porque depende de
`keep_history` en la BD; si falta alguna columna, fallback al nulleo per-código.

**El camino FUNDAMENTAL tenía el bug idéntico (`b436554`).** Salió de una
pregunta del usuario: "¿consideraste por igual técnicos y fundamentales?" — la
respuesta era NO. Se había mirado por encima y etiquetado como "hueco menor".
`backfill_asset_fund_history` hacía 12 nulls + 12 escrituras por columna.
Cobertura verificada (fund_daily 4/4, fund_quarterly 8/8) → mismo arreglo.

**Bug de portabilidad propio, en el mismo commit:** `ea5d632` usaba SQL crudo
`DELETE FROM "tabla"` con comillas dobles — válido en PostgreSQL y sqlite,
**RECHAZADO por MariaDB** (usa backticks). Como la suite corre sobre sqlite,
NUNCA lo habría detectado; habría explotado en un deploy MySQL. Reemplazado
por el objeto `Table` (`_get_wide_table`), que delega el quoting al dialecto.
**Lección: la suite sobre sqlite no valida portabilidad de SQL crudo.**

**Atajo de `topn_weights` (`1110a5b`):** el sub-modo 'benchmark' llama a
`simulate_topn` con `top_n=10**9`, así que ordenaba el cross-section completo
una vez por fecha para después darle a todos el mismo peso. Con `top_n >=
len(scores)` ahora devuelve equal-weight sin ordenar. Medido: 200 act 1.66x,
500 act 1.94x (−64 ms), 2000 act 1.93x (−256 ms) — escala con el universo.
Equivalencia numérica verificada empíricamente (el atajo cambia el orden del
dict, y `sum()` de floats no es asociativa): equity y turnover bit-idénticos
en 5 escenarios, incluido uno adverso con magnitudes 1e-18 junto a 5.0.

**MÉTODO que quedó consolidado (4 pasos, no confundirlos):**
1. **cProfile** → dónde mirar. NUNCA cuánto tarda (infla 3.7-4.2x acá).
2. **Leer el código** → qué es el desperdicio. Esto es lo que da CERTEZA, y no
   depende de que la medición sea precisa.
3. **Medir en la base real** → cuánto vale arreglarlo. Lo único que decide.
4. **Verificar que no cambie el resultado** — el paso que casi se saltea. En
   `topn_weights` se había afirmado "idéntico por construcción" y era falso.

Las dos reversiones del día (`d607273`, `2589e2d`) salieron de saltar del
paso 1 al 3 sin el paso 2.

**LEAD ABIERTO:** `build_panels` se reconstruye 12x en el grid del
walk-forward (`_panels_for_range`, una vez por ventana × trailing) → cachear
por ventana. Es el más grande de los que quedan y del tipo ELIMINAR TRABAJO,
pero también el más invasivo (riesgo de servir paneles de una ventana en
otra). Ojo con el encuadre: igual que el atajo del benchmark, es del BACKTEST
—corre bajo demanda— así que para el objetivo de 10k activos pesa menos que
lo del pipeline diario.

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

## Parte 6 (21-jul-2026) — reporte de escrituras: cierre en verde

Pedido del usuario: "validar el bloat es mucho trabajo para mí" → **card
"Escrituras por corrida" en el Centro de Datos** (`write_stats_service` +
`db_compat.table_write_stats`, snapshot automático alrededor de `_run`, el
chokepoint de todas las corridas). PG-only, registro en memoria, semáforo
✓/⚠/✗ con el caso real de +8.916 como fixture del nivel ⚠.

**El reporte encontró él solo, en su primer día, dos bugs invisibles:**

1. **Ciclo eterno del delta fundamental (`5c271d4`)**: `pe_growth_yoy` es NULL
   legítimo el primer año (sin trimestre previo) → esas fechas se
   re-targeteaban en cada delta ("existente" = columna no-NULL) y la fila se
   reescribía ENTERA e idéntica porque pe_ttm sí tiene valor. ~21.4k updates
   por corrida, para siempre. Residuo del cutover a tablas anchas (en
   per-código el batch filtraba NaN y no escribía). Fix: escribir solo si un
   código que TARGETEÓ la fecha produjo valor. 21.432 → 153 medido.
2. **`ind_asset_meta` incondicional (`79c31e7`)**: el caché de
   stats/checksum/benchmark se persistía entero en cada corrida (+5.331
   clavados, 66% de un delta limpio). Fix: comparar contra el caché leído (ya
   en memoria) y persistir solo cambios; centinela para "sin fila" vs
   "benchmark NULL". 5.331 → 0-4 medido.

**Validación final en producción (21-jul):** corrida repetida de Indicadores
técnicos → **✓ verde, 1.0 upd/activo**, ind_asset_meta ausente del reporte.
El fix por-activo (`ea5d632`) también quedó validado: recálculo completo de
un sintético = ind_daily +5.943 ins / 0 upd (inserts puros; antes ~28
versiones por fila). Señales: inserts puros de fábrica, corridas repetidas
escriben 0.

**Reescrituras que QUEDAN y son correctas por diseño (no tocar):** vigentes
(~1.650/corrida en current_indicator_values), logs por activo, última
fecha/último trimestre "preliminares" (~310/corrida fundamental), y el
re-ranking full_sample tras dato nuevo (⚠ legítimo, magnitud variable).

El card queda como detector permanente: una regresión de escrituras aparece
sola como ✗ sin medición manual.
