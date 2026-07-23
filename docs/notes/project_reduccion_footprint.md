---
name: project-reduccion-footprint-disco
description: "Reducir tamaño en disco (Railway). #2/#4 float4 HECHOS (0087/0088), falta aplicar en Railway; #1/#3/#5/#6 pausados"
metadata: 
  node_type: memory
  type: project
  originSessionId: 34095024-3657-4b9e-9d20-04eb7682920d
  modified: 2026-07-23T18:45:30.649Z
---

23-jul-2026. La base ocupa **2,5 GB en Railway** (500 activos, 1 estrategia de
4 señales `source=asset`, 0 señales de grupo). Medido con el reporte de
`/admin/cleanup` (`maintenance_service.database_size_report`); el `VACUUM FULL`
no recuperó nada relevante → **no hay bloat, casi todo es dato vivo**. Reparto
real: **Señales 1,2 GB (48%)**, Indicadores 716 MB (28%, `ind_daily` 606 MB),
Precios 437 MB (17%), Estrategias 163 MB. Las 4 `sig_*` grandes (~344 MB c/u)
pesan cada una el 79% de `prices` para guardar UN número derivado por
(activo,fecha). En `sig_*` **los dos índices pesan más que el dato** (44 de 88 B/fila).

**Hallazgos medidos** (consola SQL de admin):
- `prices_pkey` (sobre `id`) y todos los `ix_*_asset_date` de señales:
  `idx_scan = 0`. El de `id` está muerto (peso muerto en PG). Los secundarios
  en 0 solo prueban que no se abrieron esas pantallas, no que sobren.
- **Filas fantasma confirmadas:** `sig_6` = 4,05 M vs `prices` = 3,36 M → **+20,6%**
  de scores en fechas donde el activo no cotizó (as-of arrastra 45 días). Es el
  problema abierto de [[project-scores-dias-sin-precio]], acá con costo en disco.

**Plan de 6 palancas.** Hecho: #2 y #4. Pausado el resto por decisión del usuario.

- **#2 float4 en indicadores anchos (~190 MB) — HECHO.** `Column(Float)` sin
  precisión se materializó `double precision` (8 B) en PG al migrar de MySQL
  (donde era FLOAT 4 B): el bloat es el bug, declarar `Float(precision=24)` lo
  REPARA y **restaura la neutralidad dual** (MySQL FLOAT(24)=no-op; PG→real 4 B).
  `indicator_store.ensure_wide_ind_tables` + migración **0087** (ALTER de las 5
  anchas, nombres fijos, renderiza offline).
- **#4 float4 en `sig_*`/`strat_res_*` (~55 MB) — HECHO.** `signal_store._build`
  (score/pct) + migración **0088** (dinámica: enumera por prefijo, se saltea
  offline con guard `as_sql`, igual que el pivot de 0081).
- **922 tests verdes.** El efecto de precisión NO lo capta pytest (sqlite guarda
  float64); el único riesgo real (un score al borde de un umbral que cambie de
  bin) SOLO se ve en Railway.
- **PENDIENTE Railway:** aplicar 0087/0088 (ALTER que en PG **reescriben** cada
  tabla → lock exclusivo, disco temp ≈ tamaño de tabla → con el pipeline
  detenido) y comparar un día de scores antes/después. Sin commit/push todavía.

**Pausados:**
- **#1 dropear `prices.id` (~55 MB inmediatos).** ME EQUIVOQUÉ al venderlo como
  "riesgo cero, dual-safe": sale del ítem C.1 del **corte PG-only DESCARTADO**
  ([[project-postgres-only-estudio]]). En PG `id` es peso muerto, pero **en
  InnoDB es la clustering key** — dropearlo cambia el orden físico de inserción,
  cambio de comportamiento en un motor que no se ejercita hace semanas. La salida
  dual-safe es PK compuesta `(asset_id,date)` en AMBOS motores, con verificación
  en MySQL. Las otras tablas con `id` sustituto (`fundamental_quarterly`,
  `group_scores`) son minúsculas (640/72 KB): no vale bifurcar esquema por 55 MB.
- **#3 trend/volatility categórico (~75 MB) — PAUSADO (2ª ronda).** Peor ratio y
  el único que toca datos cargados a mano: el string `trend_*` es la CLAVE de
  matching de las señales `discrete_map` (`params.map` de la señal `tendencia_d`
  id=9), más la UI de edición. `volatility` casi no aporta (ya son strings
  cortos + índices 1-4 internos). Si se hace: columna smallint en disco +
  traducir int↔string en las fronteras (NO tocar `params.map` ni la UI), solo
  `trend`. Tras float4 el ahorro baja por padding de PG.
- **#5 dropear `ix_*_asset_date` (~320 MB, el mayor).** Depende de si se usa el
  gráfico de señal por activo / optimizador de trades (lectores por `asset_id`
  en `signal_history_service`, `trade_optimizer`, `chart_callbacks`). Reversible
  con `CREATE INDEX`.
- **#6 gate por precio propio (~175 MB).** Remedia las filas fantasma pero cambia
  NÚMEROS (ranking transversal + backtests), no solo bytes → recálculo completo.
  Ver [[project-scores-dias-sin-precio]].
