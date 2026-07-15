---
name: backtest-modulo
description: "Módulo de backtesting: MVP nivel A (deciles+IC) hecho 14-jul-2026; diseño de 3 fases acordado; gate de lectura contra scores as-of"
metadata: 
  node_type: memory
  type: project
  originSessionId: 4db31ed2-6727-4196-9e4e-a45306ca9cb0
---

**Diseño acordado (14-jul-2026), 3 fases:**
1. **HECHA — nivel A (calidad de señal)**: análisis por cuantiles (retorno
   forward por decil del ranking a horizontes 1/5/20/60 ruedas), IC de
   Spearman por fecha, spread top−bottom. Pantalla `/backtest` (menú
   Análisis), runs persistidos como SNAPSHOTS (config JSON + resultados;
   nunca se recalculan — se corre uno nuevo y se comparan) en
   `backtest_run`/`backtest_quantile_stat`/`backtest_ic_point`
   (migración 0070). Motor puro `backtest_engine.py` (testeado),
   orquestación `backtest_service.py` (thread + progreso, patrón Centro
   de Datos).
2. Pendiente: simulación de cartera top-N con `trade_simulator` (motor
   homologado, ver [[pendientes-proxima-sesion]]) + costos (bps por lado)
   + curva de equity vs benchmark + desglose por motivo de salida.
3. Pendiente: comparación de runs lado a lado + walk-forward.

**Decisiones metodológicas del MVP** (codificadas en tests):
- Sin look-ahead: señal al cierre de D, ejecución al cierre de D+lag
  (default 1); horizontes en RUEDAS PROPIAS del activo.
- **Gate de lectura**: score entra solo si el activo tiene precio propio
  esa fecha — misma semántica que la alternativa A del pendiente
  [[scores-dias-sin-precio-pendiente]] aplicada al leer; si A se implementa
  en el pipeline el filtro queda redundante sin cambiar resultados. Esto
  DESBLOQUEÓ el backtest sin decidir ese pendiente.
- Cuantiles por rango (n = mejor score), agregación equal-weight por fecha
  (media de retornos diarios del cuantil), mínimo de activos por fecha.
- El backtest NO tiene delta: siempre full a demanda (es barato y los runs
  deben ser reproducibles); depende de que la historia esté completa
  ("Recalcular completo" tras editar señales/estrategias).

**PENDIENTE CODESPACE**: `alembic upgrade head` (0070) + correr un backtest
real desde `/backtest` y validar tiempos con ~500 activos.
