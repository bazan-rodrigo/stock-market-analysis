---
name: remover-senales-grupo-y-alcance
description: "Removidas las señales de grupo (source=group) y el Alcance de grupo en estrategias (own_group/specific_group); group_scores + Mapa de Mercado se conservan. Paso 2 hecho, migración 0090 pendiente de aplicar en Railway."
metadata: 
  node_type: memory
  type: project
  originSessionId: dd4d7c3d-1e30-4930-9919-a072e593f1f3
  modified: 2026-07-25T01:59:03.802Z
---

**24-jul-2026:** el usuario decidió REMOVER las señales de grupo y el Alcance de
grupo en estrategias, **para que los usuarios reales no lo usen** — hoy es barato
solo porque nadie lo usa; usarlo enciende la escritura de la historia COMPLETA de
group_scores (el bloat que hubo que contener en f5b396f) y suma superficie de
fallos/tests. Nota archivo-por-archivo en
`docs/notes/design_remover_senales_grupo_y_alcance.md`.

Aclaración clave: `group_scores` NO se calcula desde señales — se calcula desde
los indicadores de tendencia (ind_trend_*) y alimenta el **Mapa de Mercado**. Por
eso SOBREVIVE intacto. Las señales de grupo eran CONSUMIDORAS de group_scores.

**Rollout en 2 pasos (decisión del usuario):**
- Paso 1 (commit 19ac3c7, pusheado): gate de UI — sacar la opción de las listas,
  sin migración.
- Paso 2 (un commit): remoción de raíz, −1000 líneas netas. Se fue la derivación
  (`_derive_needed_groups`, `_load_derivation_inputs`, `restricted_attribute_ids`),
  la escritura de group_signal_value, las ramas de scope en el scoring, y la UI
  (combo Fuente en señales, Alcance/Tipo grupo en estrategias). **Migración 0090**
  portable dual dropea la tabla `group_signal_value` + columnas `signal.source`,
  `signal.group_type` y `strategy_component.scope/group_type/group_id`.

**Opción (a) — frontera con la otra sesión (Mapa de Mercado):** el backfill por
rango (`signal_backfill_range`) CONSERVA la escritura de group_scores de la ÚLTIMA
fecha (para el mapa); el resto de su historia no la lee nadie. Se PRESERVÓ el
`covering()` que dejó el fix Semanal/Mensual de la otra sesión, y `_Sweep.exact`
sigue en pie para el fix diario que quedó diferido. No se tocó ningún archivo del
mapa (group_score_service, technical_service.get_market_map_data, market_map*).

Decisiones puntuales: (1) dropear `source` y `group_type` (no dejarlas fijas);
(2) el import **RECHAZA** `source=group` / componentes con `scope` con error, no
los importa en silencio; (3) rollout en 2 pasos por el riesgo del DDL en prod.

Verificación: suite **904 passed** (incl. 4 tests nuevos en
`test_import_rechaza_grupo.py` + paridad rango/por-fecha reescrita). Sin código
muerto (chequeo AST + grep repo-wide). 8 strategy_packs reescritos sin las
columnas muertas, datos intactos y reimportan OK. Manual: 720/730 + 11 secciones.

**PENDIENTE Railway (producción):** aplicar `alembic upgrade head` (la 0090) — es
DDL irreversible; el push del código NO la corre. Después confirmar que el Mapa de
Mercado sigue con datos y las estrategias rankean. Ver [[pendientes-proxima-sesion]].

Reemplaza el enfoque de [[group-scores-scope]] (el modo rango acotado por
`_derive_needed_groups`), ahora removido.
