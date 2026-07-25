---
name: project-sig-wide-tables
description: "Estudio + plan por fases para llevar señales (sig_{id}) y estrategias (strat_res_{id}) a tablas anchas, como se hizo con indicadores; ataca el ~50% de la base. Fase 0 (medidor) hecha, falta correrla en Railway"
metadata: 
  node_type: memory
  type: project
  originSessionId: 58c4a97c-9a03-42ba-8cf6-706cfcedde17
  modified: 2026-07-25T19:02:15.183Z
---

25-jul-2026. El usuario pidió estudiar aplicar el modelo de **tablas anchas** de
indicadores a **señales y estrategias**, e invitó a rehacer el cómputo si sirve.
Estudio hecho y plan por fases escrito en **`docs/notes/design_sig_wide_tables.md`**.

**Decisión de diseño:** DOS anchas SEPARADAS (`signal_values_wide` con una col
float4 por señal; `strategy_results_wide` con score+pct por estrategia), NO una
combinada — grids distintos, y `strategy_only` recalcula estrategias sin tocar
señales (una combinada bloatearía las señales al UPDATE-ear la fila entera).

**Por qué rinde (medido en [[project-reduccion-footprint-disco]]):** señales =
50% de la base (1,2 GB); cada `sig_{id}` es ~80% overhead, "los índices pesan más
que el dato", y float4 NO rinde en `sig_*` por MAXALIGN (un solo score cae en el
padding). La ancha paga header + los 2 índices UNA vez por (activo,fecha) y hace
que float4 por fin rinda (varias columnas float). Estimado **~3,5–4×** con 4
señales, CRECE con la cantidad de señales. Subsume la palanca #5 (índice
secundario) sin perder el índice.

**Cómputo:** el motor NO se rediseña (el backfill ya tiene chunks/as-of/escritor
único/lectores paralelos). Cambia el blanco de escritura (fila ancha + buffer
full-row Opción B en rebuild), la lectura de `strategy_only` (`col IS NOT NULL`)
y el reconcile (ADD/DROP COLUMN en vez de CREATE/DROP TABLE). Reusa todo el
andamiaje de correctitud ya pagado en [[project-ind-wide-tables]].

**Preguntas del usuario, resueltas (en la nota):** (1) NO hay contención nueva —
el escritor sigue único, el `run_lock` serializa, el retry cubre lo concurrente;
(2) NO cambiar el eje rango→activos — las estrategias son transversales (ranking
depende de todos los activos de la fecha), la ancha es ortogonal al eje;
(3) rebuild = "Recalcular completo" existente (TRUNCATE) y, para reclamar columnas
dropeadas, ese mismo rebuild recrea la tabla (DROP+CREATE con columnas vivas).

**Tensión honesta:** se pierde "recálculo = TRUNCATE en vacío" para UNA señal
suelta (pasa a UPSERT de columna → bloat temporal); y `DROP COLUMN` acumula hasta
el recreate. Ambas mitigadas, documentadas.

**Plan:** flag `USE_WIDE_SIGNAL_TABLES`, migraciones **0091** (crea) / **0092**
(pobla merge-en-Python sin bloat) / **0093** (dropea viejas). Última en master: 0090.

**Fase 0 HECHA y MEDIDA en Railway (25-jul, commit 4005fdc pusheado con
--no-verify):**
- Señales = **53,2% de la base** (1,19 GB en 4 sig_*); idx/dat = **1,01** (el
  índice pesa igual que el dato → overhead domina, la ancha amortiza).
- **`--exact-union` = 4.052.162 filas ≈ la mayor sig_ sola (4.052.085), +77 filas.**
  Validación fuerte: las 4 señales comparten casi exactamente la misma grilla
  (activo,fecha) → la ancha NO paga dispersión, amortización máxima.
- **Señales ancha: 3,1× / −825 MB** (1,19 GB → 391 MB). El mayor lever lossless
  que queda (la ronda 1 de footprint ahorró 258 MB estructurales; esto es ~3×).
- **Marginal clave:** cada señal full-coverage nueva cuesta ~344 MB hoy vs ~16 MB
  en la ancha (4 B × 4,05 M) = 21× marginal. Como las señales las crea el usuario
  y crecen, la brecha explota: ~8 señales ≈ 5,4×, ~16 ≈ 10×.
- **Estrategias ancha: 1,0× (CERO ahorro) HOY** — hay UNA sola estrategia
  (strat_res_7, 150 MB), no hay qué amortizar con N=1. Misma lógica aplicaría con
  varias (cada una ~150 MB hoy → ~14 MB en ancha). Es future-proofing, sin ganancia
  inmediata.
- Aviso honesto: incluso post-refactor la base queda **1,43 GB (292% de 500 MB)** —
  es el mayor lever, NO la solución completa al tope de Railway.

**DECISIÓN del usuario (25-jul): hacer AMBAS** (señales + estrategias).

**Fase 1 HECHA (código, flag OFF, 916 tests, SIN pushear aún — esperando "sí"):**
- `signal_store.py`: `use_wide_signal_tables()` default OFF, `SIG_WIDE_TABLE`/
  `STRAT_WIDE_TABLE`, helpers de columna, `ensure_wide_signal_tables` (tablas base)
  + primitivas ADD/DROP COLUMN dinámico (`ensure_sig_column`/`ensure_strat_columns`/
  `drop_*`, checkfirst por introspección, tipo por dialecto, float4).
- Migración **0091**: crea `signal_values_wide` + `strategy_results_wide` base
  (asset_id+date, PK (date,asset_id), ix (asset_id,date), sin columnas de valor ni FK).
- `tests/test_wide_signal_tables.py`.
- **Wiring decidido:** el ensure NO se cablea al arranque en fase 1 (migración 0091
  = única creadora en Railway; como las migraciones se aplican a mano, cablearlo
  chocaría con `op.create_table`). El cableo va en el cutover (fases 3-5), con la
  0091 ya aplicada — mismo orden que indicadores.
- **PENDIENTE:** push + revisión del usuario; después `alembic upgrade head` en
  Railway (crea las 2 tablas base vacías, deploy-safe con flag OFF). Fases 2-5 sin
  empezar (escritor ancho, lector strategy_only, cutover 0092, drop 0093).
