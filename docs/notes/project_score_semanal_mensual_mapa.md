---
name: project-score-semanal-mensual-mapa
description: Mapa de Tendencia calcula scores de grupo AL VUELO (no persiste group_scores); diario as-of + sem/men covering
metadata: 
  node_type: memory
  type: project
  originSessionId: efee85dd-9d14-4abb-a9ea-6f7458a1a84b
  modified: 2026-07-26T00:54:58.336Z
---

25-jul: **el Mapa de Tendencia de Mercado ahora calcula los scores de grupo AL
VUELO** (`group_score_service.group_scores_for(target_date)`), desde ind_trend_*,
con **selector de fecha**. Ya NO persiste `group_scores` (esa tabla no la leía
nadie más que el mapa desde que se removieron las señales de grupo). Committeado
en **f4aa785** (Fases 1-2), **913 passed**.

Semántica de lectura (los tres timeframes toman su barra vigente aunque
target_date no sea día hábil del activo):
- **Diario: as-of** hacia atrás (última barra `<= target_date`, tope
  `ASOF_MAX_LOOKBACK_DAYS=45`).
- **Semanal/mensual: covering** hacia adelante (primera barra `>= target_date`,
  tope `COVERING_MAX_AHEAD_DAYS=40`) — la barra en curso, que cierra domingo /
  fin de mes DESPUÉS de target_date.

Esto arregló DOS bugs de una: (1) semanal/mensual siempre vacíos (leían fecha
EXACTA=viernes, pero la barra cierra domingo/fin de mes → NULL); (2) diario
vacío en Sectores cuando 2 monedas de fin de semana empujaban `MAX(prices.date)`
a un sábado y las acciones (último diario el viernes) no matcheaban el exacto.
El cálculo al vuelo con as-of/covering los resuelve sin persistencia ni cache
desfasado. "Otros grupos vacíos" (Sectores/Industrias/Países) nunca fue bug: es
falta de datos (solo había currencies, que no tienen sector).

Cambios clave: `group_scores_for`/`_read_asset_trends`/`_load_asset_meta` en
group_score_service (se removieron `compute_group_scores`/`run_daily`);
`get_market_map_data(target_date=None)` usa el al-vuelo; se quitó
`_refresh_group_scores` (technical/price) y `group_score_service.run_daily` del
delta y run_recalculate (signal_service); signal_backfill_range dejó de escribir
group_scores (fuera `_Sweep.covering/exact`, extensión de ventana, `gs_rows`);
market_map con DatePickerSingle + dcc.Store y callbacks partidos. Costo del
al-vuelo: decenas de ms hoy, sub-segundo a 10k (**a medir en Railway**).

**Fase 3 HECHA (25-jul, b8e6d43): la tabla group_scores se dropeó.** Migración
`0092_drop_group_scores` (down_rev 0091; downgrade la recrea vacía; portable,
cubierta por test_bootstrap_portability; head único = 0092). Se removió el modelo
`GroupScore` + su export, el dataset del data_explorer, y las refs en
cleanup_service/maintenance_service (listas de limpieza/bloat + clasificador);
`test_db_utils_y_escritor` pasó a usar signal_eval_log como tabla de muestra para
delete_by_ranges. 912 passed. Se pudo hacer sin colisión porque el árbol estaba
limpio (la sesión paralela había commiteado sus cambios de cleanup/maintenance).

**PENDIENTE en Railway:** (1) `alembic upgrade head` para dropear la tabla real
(o la nueva del sig-wide si la sesión paralela sumó migraciones — verificar head);
(2) que el mapa renderice con el selector y muestre Diario+Semanal+Mensual en
Sectores; (3) cronometrar `group_scores_for` a escala. Ver
[[feedback-entorno-verificacion]].

**Why:** el mapa ([get_market_map_data]) era el único consumidor de group_scores;
calcularlo al vuelo elimina la clase de bugs de cache. Relacionado con
[[project-group-scores-scope]] y [[project-scores-dias-sin-precio]].

**How to apply:** el mapa se lee al vuelo por fecha; diario as-of hacia atrás,
semanal/mensual covering hacia adelante. NO volver a persistir group_scores.
