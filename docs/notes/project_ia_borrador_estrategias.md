---
name: project-ia-borrador-estrategias
description: "La IA ya puede diseñar y medir estrategias que NO existen (3-ago-2026); el holdout se EXCLUYE, no se oculta"
metadata: 
  node_type: memory
  type: project
  originSessionId: 848dbb09-b3a7-4efc-92b4-ccbbe3056e22
  modified: 2026-08-03T20:42:49.453Z
---

3-ago-2026. Con 51 señales calculadas y **0 estrategias creadas**, la IA quedaba
en un callejón: `run_backtest_preview` y `backtest_strategy_variant` exigían una
estrategia materializada, así que solo podía proponer ideas de memoria. Se
agregaron `backtest_strategy_draft` (nivel A) y
`simulate_strategy_draft_portfolio` (nivel C) en `app/ai/tools/borrador.py`.

**El eslabón que faltaba era UNO SOLO: el universo.** `compute_variant_backtest`
ya combinaba señales al vuelo — lo único que tomaba de la estrategia base eran
los pares (fecha, activo) elegibles. Lo resuelve
`strategy_filter.eligible_by_dates` (el filtro real evaluado fecha por fecha).
Todo lo demás ya estaba desacoplado: `_computar` acepta `score_rows`.

**Decisiones del usuario** (no re-litigar): filtro declarativo COMPLETO desde el
arranque (no solo atributos), las dos herramientas juntas, holdout SÍ, corte =
último 25% de la historia disponible de señales, y aplicarlo también a las dos
herramientas viejas.

**Lo que hace que el holdout signifique algo** — y que casi se hace mal:
1. **Se EXCLUYE, no se oculta.** Tapar el campo del último tramo no sirve
   mientras el IC medio global lo siga teniendo adentro: se lo mira igual,
   promediado.
2. **El corte es del CALENDARIO, no del pedido.** Si fuera "el último cuarto de
   lo que pediste", mover `date_to` entre intentos descubriría el tramo
   reservado de a pedazos sin pedirlo nunca.

**Hallazgo del final:** el campo `ic_holdout` que ya existía en `_estabilidad`
pasó a mentir en cuanto hubo un holdout de verdad — era el último tramo de la
ventana que la IA mira ENTERA para elegir. Renombrado a `ic_ultimo_tramo`, con
test que exige que `ic_holdout` no exista. Un nombre que promete una prueba
independiente y no la da es peor que no tenerla.

**PENDIENTE de verificación en Railway (= producción):** el costo real del
filtro por fecha (`load_operand_values` es una query por operando y por fecha).
Mitigado con `date_step` (default 5 con filtro) y `date_from` default de 5 años,
pero **medido no está**. La suite (1888) cubre solo lógica pura.

Ver [[project-ia-mcp]], [[project-backtest]], [[project-packs-estandar]],
[[project-indicadores-0098]] (de ahí sale el aviso de cobertura: el score
renormaliza ante dato faltante y el activo incompleto queda mejor rankeado).
