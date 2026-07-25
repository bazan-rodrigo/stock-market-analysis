# Diseño: tablas anchas de señales y estrategias

**Objetivo:** reducir el footprint de las señales (`sig_{id}`) y estrategias
(`strat_res_{id}`) — hoy **~50% de la base** (1,2 GB de 2,3 GB en Railway) —
**sin perder historia**, aplicando el mismo modelo ancho que ya rindió en los
indicadores (`design_ind_wide_tables.md`). El backfill de señales ya está muy
optimizado; esto cambia el **blanco de almacenamiento**, no el motor de cómputo.

## Motivación (medido — `project_reduccion_footprint.md`)

- Cada `sig_{id}` pesa ~344 MB para **un solo número** por `(activo,fecha)`:
  ~85 B/fila con ~12 B útiles → **~80% overhead**, idéntico al caso indicadores.
- **"Los índices pesan MÁS que el dato"**; **la mitad de cada tabla son los 2
  índices** (`PK (date,asset_id)` + `ix (asset_id,date)`), pagados **N veces**
  sobre el mismo grid con N señales.
- **float4 NO rinde en `sig_*`** por MAXALIGN: `asset_id`(4)+`date`(4)+`score`(4)
  se alinea a 8 y el `score` cae en el padding. Lección anotada: *"float4 solo
  rinde donde hay VARIAS columnas float"*.

El modelo ancho ataca las tres cosas: paga header + los **2 índices UNA vez** por
`(activo,fecha)` amortizado sobre todas las señales; hace que **float4 por fin
rinda** (varias columnas float empacadas); y **subsume la palanca #5** (dejar de
pagar el índice secundario N veces) sin perder el índice.

## Decisión: DOS tablas anchas separadas (no una combinada)

- `signal_values_wide (asset_id, date, sig_1, sig_2, …)` — una col float4/señal
  (nombre = `sig_{id}`, por ID inmutable como hoy).
- `strategy_results_wide (asset_id, date, strat_1_score, strat_1_pct, …)` — dos
  cols por estrategia (conserva el `pct` cross-sectional).

**Por qué separadas, no una combinada:**
1. **Grids distintos:** señales cubren el subconjunto que puntúa el evaluador;
   estrategias, la cross-section elegible del filtro. Combinar une con NULLs.
2. **Unidades de recálculo distintas:** `strategy_only` recalcula estrategias
   **sin tocar señales**; en una combinada, el `UPDATE` de columnas de estrategia
   reescribe la fila entera (PG reescribe toda la tupla) → **bloatearía las
   señales**. Separarlas las aísla.
3. Combinar **no ahorra** extra: la amortización de header+índice ya se captura
   por tabla.

## Estimación de ahorro (anclada a lo medido)

Caso medido (4 señales `source=asset`, 500 activos): 4 × ~344 MB ≈ 1,2 GB →
**~0,3–0,35 GB** (~**3,5–4×**). El ahorro **crece con la cantidad de señales**
(16 señales → ~8–10×, como indicadores) — y las señales son la entidad que
**crece con el uso**, al revés del catálogo fijo de indicadores. El número real
lo da `scripts/measure_signal_storage.py` en Railway ANTES de comprometer
migraciones.

## Qué cambia en el cómputo (poco)

El backfill (`signal_backfill_range.py`) ya tiene barrido cronológico por chunks,
as-of por punteros, escritor asíncrono único, lectores paralelos por tabla,
`executemany` y TRUNCATE por unidad. **No se rediseña el motor.** Cambia:

- **Escritura:** N `bulk_insert` (uno por `sig_{id}`) → construir la **fila ancha**
  por `(activo,fecha)` y escribir una vez. El loop ya arma
  `sv_scores={(sig_id,aid):v}` por fecha → pivotar es natural. Rebuild reusa el
  **buffer full-row (Opción B)** que evita el bloat de escribir columna-por-columna.
- **Lectura en `strategy_only`:** leer las columnas de la ancha con
  **`col IS NOT NULL`** (as-of fiel por columna, ya resuelto y testeado en
  indicadores).
- **Reconcile / ciclo de vida:** `reconcile_dynamic_tables` pasa de CREATE/DROP
  TABLE a **ADD/DROP COLUMN** (instantáneo en PG y MariaDB 10.3+).

**Reuso directo de indicadores:** as-of `col IS NOT NULL`, buffer full-row sin
bloat, `db_compat` (UPSERT-por-columna, quoting dual, `information_schema`),
patrón de migración-pivot merge-en-Python sin bloat (0078).

## Contención, eje de paralelización y rebuild (decidido)

- **Contención por escritura:** el backfill tiene **UN escritor** (los paralelos
  se descartaron con datos: espera 0s). Se mantiene → **cero contención nueva**;
  la ancha hace *menos* INSERTs. Matiz: la ancha engrosa el lock a nivel fila
  (no hay lock por columna), pero el **`run_lock`** serializa las corridas y los
  escritores concurrentes reales (delta vs baja de activo) ya tienen el **retry**
  de lock. La propiedad "insertar en vacío" se conserva en rebuild (TRUNCATE) y
  delta (append); solo la pierde el recálculo de UNA señal suelta sobre toda la
  historia (UPSERT de columna → bloat temporal, autovacuum lo recupera).
- **Eje rango→activos: NO.** Las estrategias son **transversales**
  (el ranking en D depende de todos los activos en D) → no se particionan por
  activo (misma razón que CLAUDE.md da para el delta por-fecha). Las señales
  solas sí, pero no son el cuello (read-bound: lectura 158s vs cómputo 19–89s),
  la fase de estrategia exige datos por-fecha (forzaría un transpose) y el PK
  `(date,asset_id)` está optimizado para append cronológico. La ancha es
  **ortogonal al eje**: no lo exige ni lo cambia. (Dato: si algún día se quisiera
  escritura por-activo, la ancha con filas disjuntas por `asset_id` sería la
  forma SIN contención — pero las estrategias transversales bloquean ese eje.)
- **Rebuild:** dos sentidos. (a) *Recalcular completo* (existente) = TRUNCATE +
  insert full-row, **disparo de usuario** desde el Centro de Datos, bajo
  `run_lock`, igual que hoy. (b) *Recrear la tabla para reclamar columnas
  dropeadas* (creep de `DROP COLUMN`): **se cuelga del mismo "Recalcular
  completo"** — en vez de TRUNCATE hace `DROP TABLE` + `CREATE` con solo las
  columnas vivas + insert (cuesta cero extra, ya reescribe todo). No hay paso
  nuevo ni DDL de arranque. Alta de señal = `ADD COLUMN` instantáneo, sin
  rebuild; baja = `DROP COLUMN` instantáneo pero no libera hasta el recreate (b).

## Riesgos / tensiones honestas

1. **Se pierde "recálculo = TRUNCATE en vacío" para UNA señal suelta** (la
   propiedad de `project_tablas_por_senal`). En ancha es UPSERT de columna → bloat
   MVCC (autovacuum). Mitiga: el cómputo no cambia, el bloat es temporal y a
   escala de una columna, el delta y el rebuild siguen limpios.
2. **`DROP COLUMN` acumula** (no libera hasta recrear; cuenta contra el límite
   ~1600 col de PG). Con señales de usuario que van y vienen es creep real →
   recreate en el rebuild (b). A escala de decenas de señales float4 está lejos
   del límite, pero documentar.
3. **Dual MySQL/PG:** ADD/DROP COLUMN portable, float4 (`Float(precision=24)`),
   UPSERT-por-columna e `information_schema` — todo con patrón en `db_compat`
   del refactor previo; se reusa.

## Plan por fases (cutover coordinado con flag, estilo 0077–0079)

Flag `USE_WIDE_SIGNAL_TABLES` (default OFF → ON al final). Última migración en
master: **0090** → las nuevas encadenan **0091+**.

0. **Medición (HECHA):** `scripts/measure_signal_storage.py` (read-only, dual).
   Correr en Railway (`--exact-union` para el conteo real de filas de la ancha) y
   confirmar el ahorro ANTES de comprometer migraciones.
1. **Fundaciones:** esquema `signal_values_wide` / `strategy_results_wide`,
   `ensure_wide_signal_tables`, migración **0091** (crea vacías, portable), tests.
2. **Escritor ancho:** pivot de `_flush`/`_bulk_insert` a fila ancha + buffer
   full-row en rebuild; gateado por el flag. Tests.
3. **Lector ancho:** `strategy_only` lee columnas con `col IS NOT NULL`; reconcile
   por columna (ADD/DROP). Tests.
4. **Cutover:** migración **0092** (pobla por merge-en-Python full-row, sin bloat,
   chunked por rangos de asset_id, guard offline). Deploy fases 2+3, flag ON,
   validar señales viejas vs nuevas en Railway.
5. **Limpieza:** migración **0093** DROP de las `sig_{id}`/`strat_res_{id}` viejas
   (downgrade recrea+repuebla); wide default; rebuild recrea la tabla (reclama
   columnas). Status del Centro de Datos → nombres anchos.

## Estado (jul-2026)

- **Fase 0 HECHA y MEDIDA en Railway:** `scripts/measure_signal_storage.py`.
  Resultado real: señales 53,2% de la base (1,19 GB), idx/dat 1,01; `--exact-union`
  = 4.052.162 filas ≈ la mayor `sig_` sola (+77) → grillas casi idénticas, cero
  penalización por dispersión. **Señales ancha: 3,1× / −825 MB.** Estrategias:
  1,0× hoy (una sola). Decisión del usuario: **hacer AMBAS** (señales + estrategias).
- **Fase 1 HECHA (código, sin cutover — flag OFF, 916 tests):**
  - `signal_store.py`: `use_wide_signal_tables()` (default OFF), `SIG_WIDE_TABLE`/
    `STRAT_WIDE_TABLE`, helpers de columna (`sig_column_name`, `strat_score_column`,
    `strat_pct_column`), `ensure_wide_signal_tables` (tablas base) y primitivas
    `ensure_sig_column`/`ensure_strat_columns`/`drop_*` (ADD/DROP COLUMN dinámico,
    checkfirst por introspección, tipo compilado por dialecto). float4.
  - Migración **0091**: crea `signal_values_wide` + `strategy_results_wide` base
    (asset_id + date, PK (date,asset_id), ix (asset_id,date), sin columnas de valor
    ni FK). Portable (sa puro).
  - Tests: `tests/test_wide_signal_tables.py`.
  - **Decisión de wiring:** en fase 1 `ensure_wide_signal_tables` NO se cablea al
    arranque (`ensure_builtin_data`) — la migración 0091 es la ÚNICA creadora en
    Railway. Como las migraciones se aplican A MANO en Railway, cablear el ensure
    al arranque crearía la tabla antes de la migración → `op.create_table` chocaría.
    El cableo al startup + save/delete + reconcile-por-columna va en el cutover
    (fases 3-5), cuando la 0091 ya corrió en Railway (mismo orden que indicadores).
  - **PENDIENTE Railway:** pushear + `alembic upgrade head` (crea las 2 tablas base,
    vacías; con el flag OFF nada las toca — deploy-safe).
- Fases 2-5 sin empezar.

> Coordinación de migraciones: esta línea usa **0091/0092/0093**. Si hay trabajo
> paralelo (Backtest/Carteras del usuario), encadenar después para no chocar
> (alembic multiple heads).
