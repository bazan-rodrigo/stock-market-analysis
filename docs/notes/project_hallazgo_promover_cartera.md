---
name: project_hallazgo_promover_cartera
description: "DIFERIDO — \"Promover a seguimiento\" descarta reglas/rebalanceo/costos; la cartera creada sigue el ranking puro, no la curva gated"
metadata: 
  node_type: memory
  type: project
  originSessionId: 87013aa9-b8a1-4676-b6de-fce6bdf7294c
  modified: 2026-07-20T20:03:09.954Z
---

Hallazgo #2 de la verificación del manual (20-jul-2026), **diferido por el
usuario** para más adelante.

**Problema:** en el Backtest nivel Cartera, el botón "Promover a seguimiento"
crea una cartera teórica que solo hereda `strategy_id` y `top_n`. Las reglas de
entrada/salida, el rebalanceo y los costos de la simulación NO viajan, así que
la cartera promovida sigue el *ranking puro* (top-N equal-weight, ver
`portfolio_service._strategy_topn_members`), no la curva **gated** que el usuario
estaba mirando cuando apretó el botón. Es un hueco de producto: el botón aparenta
promover lo que se ve.

**Por qué es grande (no es un fix de una línea):**
1. El modelo `Portfolio` no tiene dónde guardar el spec de simulación (reglas,
   rebalanceo, costos) → requiere **migración** (columna nueva, tipo Text/JSON;
   portable ≥0076).
2. La valuación de una cartera de seguimiento (`portfolio_service.equity_series`
   + `_strategy_topn_members`) es un **motor distinto** al de la simulación
   gated del backtest (`portfolio_backtest_service.run_portfolio_backtest`).
   Hacer que la cartera siga la curva gated implica cablear el spec en esa
   valuación — cambio sustancial en `/carteras`.
3. No se puede verificar en esta PC (sin BD). Necesita el Codespace.

Guardar solo el spec sin que la valuación lo consuma sería un no-op + migración
inútil: hay que hacer las dos partes juntas.

Relacionado: [[project_manual_usuario]] (de donde salió), [[project_backtest]].
