---
name: project-score-semanal-mensual-mapa
description: Fix del Score Semanal/Mensual vacío en el Mapa de Tendencia; falta verificar en Railway
metadata: 
  node_type: memory
  type: project
  originSessionId: efee85dd-9d14-4abb-a9ea-6f7458a1a84b
  modified: 2026-07-24T04:10:42.092Z
---

24-jul: **arreglado en código+tests el bug del Score Semanal/Mensual siempre
vacío en el Mapa de Tendencia de Mercado.** Causa raíz: la tendencia semanal se
guarda etiquetada al CIERRE de su período (`resample("W")` → domingo,
`resample("M")` → fin de mes), que cae DESPUÉS del último día con precio; pero
`compute_group_scores` (camino por-fecha) y el camino de rango leían la tendencia
con fecha EXACTA = target_date (viernes) → `regime_score_w`/`regime_score_m`
quedaban en NULL casi siempre (afectaba a TODOS los activos, no solo currencies).
La diaria andaba porque hay barra cada día hábil.

Fix (elegido por el usuario: mostrar la barra EN CURSO, preliminar): leer la
barra cuyo período contiene target_date = la primera con fecha `>= target_date`
(tope `COVERING_MAX_AHEAD_DAYS=40`). En `group_score_service.compute_group_scores`
(SQL) y en `_Sweep.covering` de `signal_backfill_range` (espejo, para que el
test de paridad siga verde); además se extiende la ventana de carga +40 días
solo para `trend_weekly`/`trend_monthly`. Diaria intacta (match exacto). Tests:
`tests/test_group_score_covering.py` + comentarios de paridad; **928 passed**.
Es cambio de solo-lectura: **sin migración ni rebuild** (relee lo ya guardado).

Lo otro que reportó el usuario ("otros grupos vacíos": Sectores/Industrias/Países)
NO es bug: solo había 8 currencies con indicadores para la fecha, y las monedas
solo tienen grupo market e instrument_type. Se llenan al cargar acciones.

**PENDIENTE (Railway, esta PC no levanta la app):** verificar que tras el próximo
recálculo el mapa muestre Semanal/Mensual poblados. Ver [[feedback-entorno-verificacion]].

**Why:** el mapa ([get_market_map_data]) solo lee la última fila de `group_scores`;
el defecto estaba 100% del lado de escritura. Relacionado con [[project-group-scores-scope]]
y [[project-scores-dias-sin-precio]].

**How to apply:** semanal/mensual se leen "en curso" (barra del período que
contiene la fecha), no la ya cerrada; si se toca la semántica de lectura de
tendencias de grupo, cambiar los DOS caminos a la vez (por-fecha y rango) o
`test_signal_range_parity` rompe.
