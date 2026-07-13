---
name: group-scores-scope
description: "group_scores/group_signal_value ahora se calculan solo para los grupos que alguna estrategia consume (commit f5b396f, 13-jul-2026)"
metadata: 
  node_type: memory
  type: project
  originSessionId: 1cfc6581-fa76-4acd-aea2-a61221e684ed
---

**13-jul-2026 (commit `f5b396f`, pusheado):** el usuario notó que
`group_scores` se llenaba de millones de filas muertas (sentencias lentas
al final de la historia densa) — el modo rango escribía la agregación de
~200 grupos por fecha aunque no hubiera ninguna señal `source=group` que la
leyera (él tiene cero señales de grupo hoy).

Cambio: `group_scores`/`group_signal_value` se escriben SOLO para los grupos
que alguna estrategia consume (`_derive_needed_groups` en
`signal_backfill_range.py`):
- Sin señales de grupo → no se escribe historia (solo la última fecha, para
  el mapa de mercado, que lee `group_scores` de la última fecha).
- Señal acotada por el filtro de una estrategia (`country in [Argentina]`)
  → solo ese país. `strategy_filter.restricted_attribute_ids` analiza el
  árbol del filtro (AND=intersección, OR=unión; conservador: ante ambigüedad
  devuelve None=todos, nunca acota de menos).
- La derivación mira TODAS las estrategias que usan la señal (unión), no
  solo las del alcance de la corrida — si no, recalcular la estrategia de
  Argentina borraría los grupos que necesita la de Brasil sobre la misma
  señal; y "Calcular historia" sobre una señal respeta los filtros.

Divergencia deliberada: el camino por-fecha (`compute_group_scores`, uso
diario/scheduler) sigue escribiendo TODOS los grupos todas las fechas para
alimentar el mapa de mercado. Solo el modo rango restringe. La última fecha
del rango se escribe completa para no romper el mapa tras un rebuild.

Sutileza que salió en `/code-review` (arreglada en el mismo commit): el
DELETE de `group_scores` quedó acotado a los tipos que la corrida reescribe
(+ la última fecha completa) — antes borraba todos los tipos por rango, así
que un rebuild acotado a una señal de sector habría borrado la historia de
tipo país de otra señal sin reescribirla.

Aviso en el editor de estrategias: al guardar una con scope de grupo,
recuerda correr "Calcular historia" si cambió el filtro o el alcance.

**PENDIENTE DE VERIFICAR EN EL CODESPACE** (esta máquina Windows no levanta
la app): correr un "Recalcular completo" y confirmar que `group_scores`
queda liviano (cero señales de grupo → solo última fecha); probar el aviso
al guardar. Tests puros+integración en verde local
(`tests/test_group_scope_derivation.py` + casos nuevos en
`test_signal_range_parity.py`). Ver [[filtro-estrategias-y-roadmap-indicadores]].

**Avisos de recálculo (commit 65be243):** al EDITAR una señal o estrategia,
el aviso pide "Recalcular completo" (Centro de Datos → Señales y Estrategias)
y lista qué queda desactualizado — un delta solo recalcula la última fecha.
Al borrar, las FK ON DELETE CASCADE limpian solas (sin aviso).

**Fórmula "composite" de señales REMOVIDA (commit a72bf57, 13-jul-2026):**
el usuario la vio redundante ("si quiero combinar señales lo hago en la
estrategia"). Eliminada de punta a punta: signal_engine, signal_service
(evaluate_composite/_build_composite_scores/_composite_refs/_closure_composites/
refs_by_key/validación de refs), UI (dropdown/ayuda/builder), strategy_filter.
save_signal/import la rechazan. Migración 0068 borra composites huérfanos.
Pack momentum regenerado: `alineacion_timeframes` (composite de tendencia_d/w/m)
→ los 3 como componentes directos con peso 2/3 c/u (reproduce exacto el
promedio simple con peso total 2). El plumbing de callbacks sigpb-comp-* en
signal_params_ui quedó vestigial e inerte (documentado). 398 tests OK.
**PENDIENTE CODESPACE**: `alembic upgrade head` (0068) + confirmar que la
pantalla de señales ya no ofrece "Compuesta".

**Lock timeout al bajar activos + alta de divisas lenta (commit 8069e5d,
13-jul-2026):** el usuario reportó que bajar un activo de divisa mientras
corría un backfill de señales tiraba `1205 Lock wait timeout` en el INSERT de
signal_value. Causa: la baja borra en cascada signal_value/prices/ind_* en una
transacción gigante que retiene locks; el backfill esperaba >50s y abandonaba
el chunk. Fixes: (1) `signal_backfill_range._flush` reintenta 1205/1213 (espejo
de `_fund_worker`; `_is_retryable_lock_error`); logged.update movido a después
del commit. (2) `asset_service._purge_asset_high_volume` borra por lotes de
5000 con commit (guardado a MySQL; sqlite no-op) antes del delete, también en
`delete_synthetics_for_asset`. (3) sync de divisas: el frame del divisor se
precarga una vez y se comparte (`compute_synthetic_prices(price_frame_cache=)`,
solo-lectura). Matiz: el cache ataca el I/O, pero el costo dominante del alta es
`backfill_asset_history` por sintético (CPU/GIL, no acelerable sin ProcessPool
diferido — ver [[pendientes-proxima-sesion]] punto 9). **PENDIENTE CODESPACE**:
bajar un activo de divisa mientras corre un backfill (ya no debería tirar 1205)
y medir si el alta mejoró.
