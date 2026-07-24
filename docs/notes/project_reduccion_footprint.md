---
name: project-reduccion-footprint-disco
description: "Reducir tamaño en disco (Railway). #2 (indicadores −148MB medido) y #1 (prices.id, 97MB) HECHOS; #4 en sig_* NO rinde por padding; falta aplicar 0087-0089 + REINDEX en Railway"
metadata: 
  node_type: memory
  type: project
  originSessionId: 34095024-3657-4b9e-9d20-04eb7682920d
  modified: 2026-07-24T02:48:20.825Z
---

23-jul-2026. Base **2,5 GB en Railway** (500 activos, 1 estrategia de 4 señales
`source=asset`, 0 señales de grupo). Sin bloat: `VACUUM FULL` no recuperó nada.
Reparto: **Señales 1,2 GB (48%)**, Indicadores 716 MB (28%), Precios 437→627 MB,
Estrategias 163 MB. Las 4 `sig_*` (~344 MB c/u) pesan cada una ~80% de `prices`
para UN número derivado por (activo,fecha); en ellas los índices pesan MÁS que
el dato. Reporte de `/admin/cleanup` (`maintenance_service.database_size_report`).

## Plan de 6 palancas — estado medido

- **#2 float4 en indicadores anchos — HECHO y MEDIDO en Railway: −148 MB.**
  Indicadores 716→568 MB (`ind_daily` 606→470). `Column(Float)` sin precisión
  daba `double precision` (8 B) en PG (en MySQL era FLOAT 4 B): el bloat es el
  bug; `Float(precision=24)` lo repara y RESTAURA la neutralidad dual. El ALTER
  TYPE de la migración **reescribe la tabla** → compacta sin VACUUM.
  `indicator_store.ensure_wide_ind_tables` + migración **0087**.
- **#4 float4 en `sig_*`/`strat_res_*` — HECHO pero RINDE POCO.** `strat_res_7`
  bajó −13 MB (2 columnas float). **`sig_*` NO bajó nada**: una fila de sig_* es
  `asset_id`(4)+`date`(4)+`score` y PG hace **MAXALIGN de la tupla a 8 B** →
  float8→float4 del único score cae ENTERO en el padding (40 B antes y después).
  Lección: float4 solo rinde donde hay VARIAS columnas float (indicadores) o dos
  (strat_res), no una sola entre enteros. `signal_store._build` + migración **0088**.
- **#1 dropear `prices.id` → PK compuesta — HECHO. 97 MB MEDIDOS.**
  ME EQUIVOQUÉ 2 veces antes: primero lo vendí "PG-only riesgo cero" (es
  clustering key en InnoDB, [[project-postgres-only-estudio]]); después culpé a
  "bloat de prices" (medido `n_dead_tup=0` → NO hay bloat). La verdad: el índice
  `prices_pkey` sobre `id` mide **97 MB con idx_scan=0** — muerto. Ninguna FK lo
  referencia, no se lee en el código, el upsert usa `db_compat._conflict_cols`
  que pasa de fallback (uq_asset_date) a la PK directa sin cambio de target.
  Forma **dual-safe**: PK compuesta `(asset_id,date)` en AMBOS motores, un solo
  esquema. Migración **0089** con rama por dialecto. **OJO PG:** `USING INDEX`
  NO sirve con el índice que respalda un UniqueConstraint ("already associated
  with a constraint" — falló en Railway la 1ª vez, rolleó entero por DDL
  transaccional, sin daño). Fix: DROP de la PK de id + DROP del UNIQUE + ADD
  PRIMARY KEY (asset_id,date) que **reconstruye el índice desde cero** → libera
  los 97 MB del pkey de id Y compacta la fragmentación (hace INNECESARIO el
  REINDEX aparte). MySQL reconstruye la tabla (RAMA NO VALIDADA contra MariaDB).
  `app/models/price.py` + docstring de `_conflict_cols`.

**922 tests verdes.** El efecto de precisión de float4 NO lo capta pytest
(sqlite guarda float64); el único riesgo (score al borde de un umbral que cambie
de bin) SOLO se ve en Railway.

## PENDIENTE Railway
0087/0088 YA aplicadas (los indicadores bajaron). Falta solo **0089**
(`alembic upgrade head`, con el pipeline detenido — el ADD PRIMARY KEY toma
ACCESS EXCLUSIVE). El ADD PRIMARY KEY reconstruye el índice de (asset_id,date)
→ ya reindexa, NO hace falta REINDEX aparte. Después:
- Comparar un día de scores antes/después (riesgo float4).
- Re-medir: con #1 + #2, prices→~470 MB y total→~2,3 GB.

**Hallazgo aparte (bug de UX):** el botón VACUUM de `/admin/cleanup` no puede
compactar `prices` con el web vivo — el `-c lock_timeout=30s` de
`app/database.py` hace fallar el `VACUUM FULL` (lock ACCESS EXCLUSIVE sobre la
tabla más caliente) y `maintenance_service` **traga el error en un warning** →
reporta éxito sin haber tocado prices. (Irrelevante para el tamaño: n_dead=0.)

## Pausados (2ª ronda)
- **#3 trend/volatility categórico (~75 MB).** Peor ratio; el string `trend_*` es
  la CLAVE de matching de las señales `discrete_map` (`params.map` de la señal
  `tendencia_d` id=9) + la UI de edición. Si se hace: smallint en disco +
  traducir en las fronteras (NO tocar params.map). `volatility` casi no aporta.
- **#5 dropear `ix_*_asset_date` de sig_* (~240 MB, el mayor lossless que queda).**
  El float4 no toca las sig_* (padding); su grasa son los 2 índices (mitad de
  cada tabla) + las filas fantasma. Depende de si se usa el gráfico de señal por
  activo / optimizador (lectores por asset_id en signal_history_service,
  trade_optimizer, chart_callbacks). Reversible con CREATE INDEX.
- **#6 gate por precio propio (~175 MB).** `sig_6`=4,05 M vs prices=3,36 M →
  +20,6% filas fantasma (as-of 45 días). Cambia NÚMEROS (ranking + backtests) →
  recálculo completo. Ver [[project-scores-dias-sin-precio]].
