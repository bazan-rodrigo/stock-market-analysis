# Diseño: tablas anchas de indicadores por cadencia (`ind_daily`/`weekly`/`monthly`)

**Objetivo:** reducir el footprint de los indicadores técnicos con historia
**sin perder ni un dato** (lossless, sin acortar historia) y **sin penalizar el
cómputo** — idealmente acelerándolo.

## Motivación (medido, jul-2026)

`scripts/measure_indicator_storage.py` sobre la base real (Postgres) confirmó:

- **El overhead domina.** `ratio índice/datos ≈ 1.02`: el índice (`ix_date` +
  PK) pesa lo mismo que los datos. Cada fila `ind_{code}` diaria ocupa
  ~94-102 B para un payload útil de ~16 B → **~80% es estructura** (header de
  tupla + entradas de índice), no dato.
- **Cada tabla `ind_` diaria (~1,5 MB) ≈ medio `prices` entero.** Las ~13-14
  diarias juntas (~20 MB) cuestan **~7× la tabla de precios de la que derivan**,
  porque cada indicador es una tabla propia con su overhead × N.
- Con 4 activos de historia profunda (~17 años): 42 MB de base, `ind_*` ~54%.
- Contexto: Railway tope **500 MB**; objetivo escalar a cientos/miles de activos
  ([[objetivo-escalado-10000-activos]]). **La retención (acortar historia) está
  DESCARTADA por decisión del usuario.**

**Historia del storage:** EAV única (`indicator_values`, migr. 0039) → una tabla
por indicador (`ind_{code}`, migr. 0043, por contención del PK autoincremental
de la EAV). La contención ya no aplica: el backfill particiona **por activo**
(ProcessPool fase 1, `backfill_all_indicator_values`), varios workers ya
escriben las mismas tablas con retry de deadlock. Una tabla ancha con PK
`(asset_id, date)` no revive esa contención (filas disjuntas por activo).

## Decisión

Reemplazar las **24 tablas `ind_{code}` técnicas** (keep_history=True) por **3
tablas anchas por cadencia** — una fila por `(asset_id, date)`, una columna por
indicador (nombre de columna = code):

- `ind_daily` (14): `trend_daily`, `volatility_daily`, `atr_percentile_daily`,
  `rsi_daily`, `dist_sma20`, `dist_sma50`, `dist_sma200`,
  `dist_optimal_sma_daily`, `return_daily`, `return_monthly`,
  `return_quarterly`, `return_yearly`, `return_52w`, `relative_strength_52w`.
- `ind_weekly` (5): `trend_weekly`, `volatility_weekly`, `atr_percentile_weekly`,
  `rsi_weekly`, `dist_optimal_sma_weekly`.
- `ind_monthly` (5): `trend_monthly`, `volatility_monthly`,
  `atr_percentile_monthly`, `rsi_monthly`, `dist_optimal_sma_monthly`.

PK `(asset_id, date)` + `ix_date`; `VARCHAR(50)` para `trend_*`/`volatility_*`,
`FLOAT` el resto; todas nullable. **`return_monthly/quarterly/yearly` son
cadencia DIARIA** (rolling calculado cada día) pese al nombre.

**Fuera de alcance (fase 1):** `ind_fundamental_*` (12, los escribe otro
servicio) y `current_indicator_values` (keep_history=False) **no se tocan** —
caen al camino legacy per-tabla. Fundamentales: candidato a `ind_fundamental_daily`
en una fase 2 de la optimización.

## Por qué es compute-positiva (respeta "no penalizar el cómputo")

- **Escritura:** 14 `executemany` por activo (uno por código diario) → **1** fila
  ancha. Menos filas, menos mantenimiento de índice.
- **Lectura de señales:** ~24 `query_values_asof`/sweeps por fecha → **3** (una
  por cadencia). El pool `_READ_WORKERS=3` mapea 1-a-1 a las 3 tablas.
- **`tail_stats`:** 24 full-scans (el cuello medido en
  [[objetivo-escalado-10000-activos]]) → **3**.

El cómputo sigue **por-código** (cada `compute_fn` independiente); solo se
coalesce la **persistencia**. **Gate:** validar con `profile_current_indicators`
+ backfill real en Codespace; no se mergea si no queda **≥ hoy**.

## Riesgo principal: semántica as-of con columnas NULL (clase homologación)

Hoy un código que se invalida en la cola **no escribe fila** (`_pairs_to_write`
filtra `pd.notna`) → su `max(date)` queda atrás y el as-of devuelve el último
valor válido. En la ancha esa `(activo,fecha)` **existe** (la escribió otro
código) con la columna en NULL. Fix: **`col IS NOT NULL`** en `query_values_asof`
Y en `_Sweep` (`signal_backfill_range`) — **idéntico en ambos** o rompe
`test_signal_range_parity`.

**DECIDIDO (fase 3): as-of POR COLUMNA (fiel).** `MAX(date) WHERE col IS NOT
NULL` — salta la columna NULL y arrastra el último valor válido. Aplicado
idéntico en `query_values_asof`, `_load_sweep` y el read de `group_score`. En
las `ind_{code}` per-código (que nunca guardan value NULL) es **equivalente al
comportamiento previo** → deploy-safe. Cambia solo el caso defensivo artificial
de `test_query_values_asof` (actualizado). En producción, un código que se
invalidaba en la cola YA arrastraba el último valor válido (vía borrado de la
fila en per-código); la ancha lo reproduce dejando la columna en NULL + este
as-of fiel.

## Plan por fases

Desarrollo escalonado y testeado por partes; **cutover en vivo = un solo release
coordinado** (lectura y escritura cambian juntas; si no, el delta diario deja las
anchas desactualizadas). Las 24 tablas viejas quedan **congeladas como rollback**
hasta validar; se dropean al final.

1. **Fundaciones (sin cambio de comportamiento):** mapping `_WIDE`
   (`indicator_store.py`), `ensure_wide_ind_tables`, migración **0077** (crea las
   3 tablas vacías, portable). Wiring en `ensure_builtin_data`. Tests.
2. **Escritor ancho:** `upsert_ind_cadence` + buffer por `(activo,cadencia)` en
   `compute_current_indicators` y el backfill; `_force_reset_ind_tables` por
   cadencia; `tail_stats`/`ind_asset_meta` siguen por-código, `min/max/count` con
   `col IS NOT NULL`. **Gate de cómputo** en Codespace.
3. **Lector ancho:** `_CodeView` proxy en `get_ind_table` (los readers de
   display/grupo/verificación no cambian); `col IS NOT NULL` en
   `query_values_asof` y `_Sweep`.
4. **Cutover coordinado:** migración **0078** (pivot en Python, **preserva byte a
   byte**, por rangos de asset_id — excluida del render offline, verificada en
   Codespace). Deploy fases 2+3. Validación con 500 activos en Codespace antes de
   prod.
5. **Limpieza:** migración **0079** `DROP` de las 24 viejas (tras validar); quitar
   camino legacy; `data_center` status → 3 nombres anchos.

## Notas

- **Extensibilidad:** indicador diario nuevo = `ALTER TABLE ind_daily ADD COLUMN`
  (instantáneo en MariaDB 10.3+/PG) + una línea en `_WIDE`, en vez de `CREATE
  TABLE`. El futuro módulo de indicadores por plantilla debe emitir `ADD COLUMN`.
- **500 activos en 500 MB:** ni optimizado entran los de historia profunda; la
  ancha estira cada MB (~1,7× total, ~5× lo diario) pero el techo de 500 MB es
  duro — la prueba grande va al Codespace; a futuro, plan con más disco.

## Estado (jul-2026)

- **Fase 1: HECHA.** Mapping `_WIDE` + `ensure_wide_ind_tables` (usada por
  tests y por el cutover; **NO** por el arranque — la migración 0077 es la única
  que crea las tablas, para no chocar con `op.create_table` en bases migradas) +
  migración 0077 + tests (`test_wide_ind_tables.py`).
- **Fase 2 (escritor): primitiva HECHA.** `upsert_ind_cadence` en
  `technical_service.py` (UPSERT parcial por columna, testeado en
  `test_wide_writer.py`). **Aún NO conectada** al pipeline vivo (ver cutover).
- **Fase 3 (lector): HECHA.** Flag `use_wide_ind_tables()` (env, default OFF) +
  `_CodeView` proxy + `_get_wide_table` en `indicator_store.py`; `get_ind_table`
  devuelve el proxy con el flag ON. As-of FIEL (`col IS NOT NULL`) aplicado en
  `query_values_asof`, `_load_sweep` y `group_score`. Tests: `test_wide_reader.py`,
  `test_query_values_asof.py` actualizado. Con el flag OFF todo es idéntico a hoy.
- **Fase 4 (cutover): maquinaria HECHA, falta VALIDAR.** Escritura gateada por
  el flag ruteada en los dos chokepoints: `_upsert_ind` (cubre
  `compute_current_indicators` + `_run_current_and_backfill`) y `_write_ind_series`
  (backfill), escribiendo la columna vía `upsert_ind_cadence`; los "borrados"
  (`existing=None`/stale) nullean la columna (`_null_wide_column`) en vez de
  borrar la fila. Prefetch del delta con `col IS NOT NULL`. Force: `_null_wide_column`
  (inline) / TRUNCATE por cadencia (`_force_reset_ind_tables`). Migración **0078**
  (**merge en Python**: arma la fila completa e inserta UNA vez, byte a byte,
  **sin bloat** — el INSERT..ON CONFLICT por código actualizaba N veces cada fila
  → tuplas muertas; chunked por activo; guard offline). Tests: `test_wide_cutover.py`.
  **Falta:** validar en Railway (migrar 0078, `USE_WIDE_IND_TABLES=1`, correr el
  pipeline y comparar señales viejas vs nuevas). El path completo de
  `backfill_indicator` con flag ON no está unit-testeado end-to-end (los
  chokepoints sí) → se valida en Railway.
  Fase 4 **validada en Railway**: 0078 pobló las anchas (bloat de la 1ª versión
  corregido), flag ON, señales idénticas leyendo de las anchas.
- **Fase 5: HECHA.** Migración **0079** dropea las 24 `ind_{code}` técnicas
  (punto de no retorno; downgrade recrea + repuebla desde las anchas). Wide pasa
  a ser el DEFAULT (`use_wide_ind_tables()` default True); la suite lo fuerza a 0
  en `conftest` (per-código sqlite). El arranque saltea los códigos `_WIDE` en
  `ensure_ind_table` (si no, se recrearían tras el drop) + asegura las anchas
  (bases create_all). `data_center` status → nombres anchos; script de medición
  reconoce las anchas.

- **Opción B (escritura sin bloat): HECHA.** El rebuild escribía columna por
  columna → cada fila ancha se ACTUALIZA N veces → tuplas muertas en Postgres
  (medido: ind_daily 3.4→25 MB tras un rebuild). Fix: buffer thread-local
  (`_wide_buffer_*`) que junta las columnas de una cadencia por (activo,fecha)
  durante el rebuild y las escribe como **fila completa una sola vez** al final
  del worker (tabla truncada → inserts puros, sin bloat). `compute_current`
  agrupa por cadencia (una fila vs 24 upserts). El **delta NO se bufferiza**
  (escribe la cola per-columna; su bloat chico lo recupera autovacuum). Test:
  `test_wide_cutover.py` (fila completa una vez).

**Refactor COMPLETO (652 tests).** Wide es el camino permanente para los 24
indicadores técnicos con historia; los fundamentales siguen per-código.
Pendiente opcional: fundamentales anchos (`ind_fundamental_daily`) — misma técnica.

> Nota de coordinación: esta línea usa las migraciones **0077, 0078 y 0079**. El
> rediseño Backtest+Carteras también planea "migraciones 0078+" — sus migraciones
> deben encadenar DESPUÉS (**0080+**), o colisionan (alembic multiple heads).
