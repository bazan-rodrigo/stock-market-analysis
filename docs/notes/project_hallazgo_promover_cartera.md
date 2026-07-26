---
name: project_hallazgo_promover_cartera
description: "IMPLEMENTADO (26-jul) — 'Promover a seguimiento' ahora hereda la corrida gated (reglas+rebalanceo+costo) como snapshot; /carteras la dibuja + botón Recalcular"
metadata:
  node_type: memory
  type: project
  originSessionId: 87013aa9-b8a1-4676-b6de-fce6bdf7294c
  modified: 2026-07-26T18:40:32.892Z
---

Hallazgo #2 de la verificación del manual (20-jul-2026). Estuvo DIFERIDO y se
**IMPLEMENTÓ el 26-jul-2026** (aprobado por el usuario; elección de alcance:
"snapshot + botón Recalcular").

**El problema (original):** "Promover a seguimiento" del Backtest de cartera creaba
una teórica que sólo heredaba `strategy_id`+`top_n`; el spec (reglas), el rebalanceo
y el costo NO viajaban. Peor que lo anotado antes: una teórica `strategy` en
/carteras **ni siquiera dibujaba curva** —mostraba el top-N y un texto "corré esto en
/backtest"—. (La `curated_equity_series` constant-mix es sólo para las CURADAS.)

**La solución (v1):** al promover, `_port_state["result"]` ya tiene la curva gated
que el usuario ve → se **congela como PortfolioRun** (reusa `save_portfolio_run` /
`PortfolioRun`/`PortfolioRunPoint`, ya existían) y se vincula a la cartera. Nada
pesado al promover.

- **Migración 0095** (`0095_portfolio_sim_spec.py`): `portfolio.sim_spec` (Text/JSON
  `{top_n, rebalance, cost_bps, spec}`, autocontenida/re-corrible) + `source_run_id`
  (Integer **plano, SIN FK de BD**, igual criterio que `strategy_id`: tolera run
  borrado y renderiza offline sin ADD CONSTRAINT). Portable, `test_bootstrap_portability` verde.
- **`promote_to_seguimiento`** ([app/callbacks/portfolio_backtest_callbacks.py]):
  ahora lee de `_port_state` (la corrida real, no los States del form); refuse si
  no hay `result` o si corre; persiste el run y crea la cartera con sim_spec +
  source_run_id. Nombre: "Seguimiento: … · top-N (con reglas)".
- **Servicio** (`portfolio_backtest_service.py`): `strategy_gated_equity_series`
  (lee la serie gated del snapshot, barato, para /carteras) y
  `snapshot_strategy_portfolio` (re-corre → nuevo run → repunta source_run_id, NO
  borra el viejo). `create_portfolio` acepta sim_spec/source_run_id.
- **/carteras** ([app/callbacks/carteras_callbacks.py] + [app/pages/carteras.py]):
  una `strategy` CON sim_spec dibuja la curva gated + KPIs + badges de config, con
  botón **Recalcular curva** (lock `_recalc_lock` + thread + `cart-recalc-interval`
  de progreso persistente en el layout). Una `strategy` sin sim_spec = comportamiento
  viejo intacto.
- Tests: `test_portfolio_backtest_service.py` (curva desde snapshot / None sin
  snapshot / None si el run se borró / snapshot repunta) y `test_portfolio_service.py`
  (create_portfolio persiste/omite sim_spec). Repaso post-implementación (26-jul):
  se agregó `test_carteras_callbacks.py` (4, `_spec_summary`, el único helper puro
  que había quedado sin cubrir) y se corrigieron dos secciones más del manual que
  tenían el encuadre viejo (400-backtest.md "siguiendo ese mismo top-N"; celda de la
  tabla comparativa de 460). Sin código muerto (todo lo nuevo referenciado). Suite
  completa verde. Sin target nuevo para cProfile (Recalcular reusa
  run_portfolio_backtest, ya cubierto por [[project_scaling_target]]).

**Fuera de v1 (diferido):** auto-avance por scheduler (el snapshot sólo avanza al
apretar Recalcular). "Miembros vigentes" sigue siendo top-N por ranking (etiquetado;
el gate as-of exigiría re-simular = pesado).

**Cadena de migración: LINEAL, sin multi-head.** La sesión de resiliencia pusheó
**0096** (`run_history`) con `down_revision="0095"` → `0094→0095→0096`, una sola
cabeza. `alembic upgrade head` en Railway aplica las dos de una (la preocupación de
multi-head que había flagueado quedó descartada).

**PENDIENTE en Railway = producción:** `alembic upgrade head` (aplica 0095+0096) +
verificar el flujo vivo (promover → ver curva en /carteras → Recalcular; que la curva
promovida sea idéntica a la del backtest). No verificado contra la app viva; la suite
local es la única red.

Relacionado: [[project_manual_usuario]] (de donde salió), [[project_backtest]].
