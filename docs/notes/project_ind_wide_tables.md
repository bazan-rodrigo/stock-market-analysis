---
name: project-ind-wide-tables
description: "Refactor de indicadores a tablas anchas por cadencia (ind_daily/weekly/monthly) para reducir footprint; fases 1-4 hechas y validadas en Railway, fase 5 (drop de las viejas) pendiente"
metadata: 
  node_type: memory
  type: project
  originSessionId: 93005631-1539-4bd7-9ea6-53916db01fa3
---

Refactor de footprint de indicadores técnicos: reemplazar las 24 tablas
`ind_{code}` (keep_history=True) por 3 tablas ANCHAS por cadencia —
`ind_daily` (14 cols), `ind_weekly` (5), `ind_monthly` (5): una fila por
`(asset_id, date)`, una columna por indicador. Lossless (no acorta historia,
decisión del usuario). Diseño y plan completos en
**`docs/notes/design_ind_wide_tables.md`**.

**Por qué:** medido en Railway (Postgres, 4 activos de ~17 años) — cada tabla
`ind_` diaria pesa lo mismo que otra, el índice pesa como los datos, y ~80% de
cada fila es overhead InnoDB/Postgres. La ancha paga el overhead UNA vez por
`(activo,fecha)` → **~5.5x** en lo técnico. Motiva: Railway tope **500 MB**, hoy
solo entran ~4 activos de historia profunda (~10 MB/activo). Objetivo escalar a
cientos/miles → ver [[objetivo-escalado-10000-activos]].

**Estado (jul-2026, en master, commits hasta 9b1a700): REFACTOR COMPLETO (código).**
- **Fases 1-5 HECHAS** (639 tests). Wide es el DEFAULT (`use_wide_ind_tables()`
  default True; la suite lo fuerza a 0 en conftest). Fase 4 validada en Railway
  (señales idénticas). Fundamentales siguen per-código.
- Migraciones: **0077** (crea las 3 anchas), **0078** (pobla por merge en Python,
  sin bloat — la 1ª versión con INSERT..ON CONFLICT por código bloateaba ~8x en
  Postgres, reescrita), **0079** (DROP de las 24 ind_{code} técnicas; downgrade
  recrea+repuebla desde las anchas).
- Decisión clave: as-of **fiel por columna** (`col IS NOT NULL`) en
  `query_values_asof`/`_Sweep`/`group_score` — equivalente en per-código.
- Escritura ruteada en `_upsert_ind` y `_write_ind_series` (→ `upsert_ind_cadence`);
  "borrados" = `_null_wide_column` (no se borra la fila, la comparten otros códigos).
- Arranque saltea los códigos `_WIDE` en `ensure_ind_table` (o recrearía las
  dropeadas) + asegura las anchas (bases create_all).
- **Opción B (escritura sin bloat, commit ab4d68f):** el rebuild escribía
  columna-por-columna → cada fila ancha se actualizaba N veces → tuplas muertas
  en Postgres (medido ind_daily 3.4→25 MB tras un rebuild). Fix: buffer
  thread-local (`_wide_buffer_*` en technical_service) que escribe la FILA
  COMPLETA una sola vez al final del worker; `compute_current` agrupa por
  cadencia. El delta NO se bufferiza (bloat chico → autovacuum).

**Ahorro:** ind_* ~22.8→~4.1 MB (~5.5x), base ~42→~24 MB, ~47→~83 activos en 500 MB.

**Fundamentales anchos (HECHO, commits 2dc8421 + 3758b7f):** los 12 fundamentales
→ 2 anchas por cadencia: `ind_fundamental_daily` (4 diarios) + `ind_fundamental_quarterly`
(8 trimestrales). Se ruteó TODO el camino de escritura de fundamental_service
(_upsert_fund_value, backfill_asset_fund_history, _backfill_fund_daily_all con
full-row, _backfill_fund_indicator con nullear-columna en vez de truncar la
compartida). Migración **0081** crea+pivot (mantiene viejas), **0082** dropea las
12 viejas. Encadenan DESPUÉS de `0080_portfolio_tables` (trabajo paralelo de
Carteras del usuario). 666 tests.

**Lectores de display/verificación ruteados (HECHO, 19-jul):** faltaban 4 lectores
que leían la columna del código SIN `col IS NOT NULL` → sobre la ancha traían las
filas que un código HERMANO escribió con esta columna en NULL. `verification_service.
_prefetch_stored` daba **diferencias FALSAS**; `data_explorer.indicator_history`,
historia espuria; panel/chart, "—" en el último valor. Fix: `.where(t.c.value.isnot
(None))` en los 4 (no-op en per-código). Tests en `test_wide_display_readers.py`.
Detalle cosmético: en el explorador el header de la col de valor para códigos anchos
es el nombre del código (`rsi_daily`) en vez de `value`. Suite: **678 tests**.

**Pendiente:**
- **Drops YA aplicados en Railway** (0079 técnicos + 0082 fundamentales, confirmado
  por el usuario 19-jul). Los 12 fundamentales per-código y las 24 técnicas ya no
  existen en prod.
- **Validar en MariaDB/Codespace:** todo el refactor ancho se probó en Postgres/
  Railway; en MariaDB debería andar (migraciones portables + db_compat) pero NO se
  corrió ahí — verificación pendiente en el Codespace (`git pull` primero).
- **REMOTES: ahora son DOS** (bazan-rodrigo, rodrigoqw33) — el usuario sacó
  rodrigoba77 (commit 03ffe6b). CLAUDE.md dice tres; está desactualizado.
- El usuario trabaja EN PARALELO en Backtest+Carteras (migración 0080_portfolio,
  portfolio_metrics, carteras.py) — coordinar numeración de migraciones (mis
  fundamentales quedaron 0081/0082, después de su 0080).

**Coordinación:** esta línea usa migraciones 0077/0078. El rediseño
Backtest+Carteras (design_backtest_carteras_rediseno.md, trabajo paralelo del
usuario) también apunta a "0078+" → sus migraciones deben ir 0079+ o colisionan.
