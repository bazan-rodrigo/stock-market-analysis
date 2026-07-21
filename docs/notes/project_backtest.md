---
name: backtest-modulo
description: "Módulo de backtesting: MVP nivel A (deciles+IC) hecho 14-jul-2026; REDISEÑO acordado 18-jul (2 módulos: Backtest niveles A-D + Carteras biblioteca de N reales/teóricas, motor y vistas compartidos); gate de lectura contra scores as-of"
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

**REDISEÑO acordado (18-jul-2026) — en diseño, sin codear todavía.** El usuario
pidió repensar `/backtest` porque "no explota las posibilidades de simulación
del gráfico". Decisiones tomadas (vía preguntas):
- **Dos módulos que comparten motor + capa de vistas** (NO son lentes de un
  solo plan — corregido 18-jul tras feedback):
  - **Backtest** = laboratorio de un *plan de operación* (estrategia + reglas
    del simulador + top-N + rebalanceo + costos) sobre el pasado; snapshot
    inmutable; niveles A-D (abajo).
  - **Carteras** = biblioteca de **N** carteras de primera clase (como Activos o
    Estrategias). Ata la funcionalidad PENDIENTE de "carteras reales y teóricas"
    que el usuario marcó como parte del valor del producto — se construye junto
    al backtest para reusar motor y vistas.
- **Modelo de Carteras (decidido vía preguntas):**
  - Hay **N de cada tipo**, no una sola. Tipos: **Seguimiento** (teóricas, sin
    plata real) y **Reales**.
  - **Teóricas — 3 métodos de composición:** *curada estática* (activos a mano,
    peso opcional), *por regla dinámica* (membresía = regla sobre score/precio/
    grupo, se recalcula sola; ej. "las que están cayendo"), *derivada de
    estrategia* (top-N de un plan; = "promover a seguimiento" del backtest).
  - **Reales — registro de operaciones** (el usuario prefiere ese nombre, no
    "ledger"): cada compra/venta es una fila (activo, fecha, cantidad, precio;
    **precio vacío → toma el de mercado de esa fecha**); varios lotes por activo
    + parciales; posición y P&L se DERIVAN del registro.
  - **Vínculo real→teórica OPCIONAL:** si una real apunta a una teórica objetivo,
    se habilita tracking error (el "real vs teórica" es un CASO, no el modelo).
  - **Comparador multi-cartera:** superponer cualquier subconjunto + benchmarks.
    Benchmark doble: EW del universo (línea base siempre) + índice elegible.
- **Backtest en 4 niveles (tabs):** A **Señal** (lo actual, IC/deciles) · B
  **Reglas** (fan-out del `trade_simulator` por-activo sobre el universo:
  win rate/PF/desglose de salidas por motivo/ranking de activos) · C **Cartera**
  (top-N con equity vs benchmark, drawdown, heatmap mensual, KPIs) · D
  **Comparar** (leaderboard de runs + walk-forward).
- **Nivel C con DOS sub-modos superpuestos:** "ranking puro" (rota top-N por
  score, sin reglas) y "con reglas/gated" (entra si regla de entrada dispara Y
  top-N; sale por SL/TP/trailing/score O cae del corte) — la brecha entre las
  dos curvas = cuánto aportan los stops.
- **Benchmark doble:** EW del universo como línea base SIEMPRE + índice elegible
  opcional (ej. Merval).
- **Costura de UX clave:** las reglas se diseñan jugando en el gráfico de
  `/activo` y se corren sobre el universo acá (reusar `spec_from_controls` /
  `window._lwc.buildSpec`).
- **Reuso:** todo el motor ya existe — `trade_simulator.summarize_trades`
  permite derivar equity/drawdown/Sharpe/PF/expectancy/CAGR/exposición/salidas
  por motivo SIN tocar el contrato homologado (solo un agregador nuevo + capa de
  vistas); costos se aplican en ese agregador. No derivable sin cambiar input:
  MAE/MFE (requiere serie intra-trade).
- **Mockup navegable publicado** (artifact, datos ilustrativos) con las 3 lentes
  y todos los tipos de vista, como referencia de diseño. Falta: feedback del
  usuario sobre qué priorizar → luego plan de implementación (tablas hijas
  portables tipo migración 0070 para equity/trades/atribución).

**ESTADO IMPLEMENTACIÓN (18-jul, commit b698877 en master, SIN pushear):**
- Plan completo en `docs/notes/design_backtest_carteras_rediseno.md` (6 fases).
- **Fase 0 HECHA**: `portfolio_metrics.py` (CAGR/Sharpe/Sortino/drawdown/PF/
  expectancy/matriz mensual/exit-reasons, puro) + `portfolio_views.py` (figuras
  Plotly + KPI tiles). Tests verdes.
- **Fase 2 (Carteras reales) HECHA**: modelo `portfolio`+`portfolio_transaction`
  (**migración 0080**, registro con comisión+impuestos+moneda), `portfolio_service`
  (posiciones con promedio ponderado, parciales, fallback de precio, equity_series,
  `realized_pnl_total`, visibilidad owner_id/is_public opt-in público), página
  `/carteras` (biblioteca+ABM+detalle KPIs/equity/tenencias/operaciones). Revisada
  con workflow adversarial (4 bugs de runtime corregidos). Suite verde.
- **Alembic**: hubo colisión transitoria (otra sesión creó y retiró un 0080);
  quedó head único 0080 (el mío). Si otra sesión commitea otra migración, encadena
  en 0081.
- **Nivel B (Reglas) HECHO y pusheado** (commit cd4fa52): fan-out del simulador
  sobre el universo → distribución/salidas por motivo/ranking.
  `rules_backtest_service` + sección "Reglas" en `/backtest`.
- **Nivel C (Cartera top-N) HECHO y pusheado** (commits 064a1c4/96089e4/0a2be2f):
  `portfolio_sim_engine` (`simulate_topn` ranking-puro + `simulate_gated`) +
  `portfolio_backtest_service` (orquestación: cross-section + elegibilidad vía
  trade_simulator + benchmark EW) + sección "Cartera" en `/backtest` (dos curvas
  + drawdown + KPIs, on-demand SIN persistir). Bug corregido (revisión adversarial):
  huecos interiores de calendario — `build_panels` arrastra score/elegibilidad a
  través de huecos para no evictar y perder el retorno que los cruza.
- **Carteras teóricas (Fase 3) HECHO y pusheado** (migración 0083; commits
  66e1a70/df19186/a8621e9): schema (composition_method/strategy_id/top_n/
  rebalance/rule_json + tabla portfolio_member) + `resolve_membership` (curada =
  lista con pesos; strategy = top-N por score as-of) + UI en `/carteras` (alta con
  método curada/estrategia + detalle con miembros) + **equity de las curadas**
  (`simulate_fixed_weights` constant-mix + `curated_equity_series`, sincrónica).
  Derivadas de estrategia: muestran miembros + apuntan a `/backtest → Cartera`.
- **`/backtest` en TABS** (Señal / Reglas / Cartera; intervals al tope).
- **VERIFICADO en Codespace (19-jul)**: TODO el rediseño corre en runtime —
  `/carteras` (reales + teóricas curadas/estrategia), `/backtest` (Señal/Reglas/
  Cartera en tabs), migración 0083 aplicada.
- **"Promover a seguimiento"** (nivel C → teórica) HECHO (9618bbb); **vínculo
  real→teórica** con desvío de composición HECHO (8581030, `tracking_drift`);
  **heatmap mensual** en Cartera HECHO (3f764e0).
- **Nivel D (comparar) HECHO y pusheado** (migración 0084; commits d1fc81b/
  0f83b49): `portfolio_run` + `portfolio_run_point` + save/list/get en
  portfolio_backtest_service; UI = botón "Guardar corrida" en Cartera + tab
  "Comparar" (curvas superpuestas + KPIs lado a lado). Endurecido por revisión:
  sello de productor al guardar (estado global), filtro de visibilidad en
  get/render, safe_callback en load. **Patrón de estado global de corrida (todos
  los niveles): es del PROCESO, no de la sesión — al persistir bajo un owner hay
  que sellar quién la produjo.**
- **Walk-forward de OPTIMIZACIÓN HECHO y pusheado** (commits d69822a motor /
  69ba7c5 UI+fixes; sin migración, on-demand). `walk_forward` en
  portfolio_backtest_service: ventanas anclado-expansivo, optimiza (top_n,
  trailing) por retorno del gated en cada train, aplica en el test OOS (fresco),
  concatena → curva OOS. UI = tab "Walk-forward" en /backtest. Fixes de revisión:
  **comparación train/test ANUALIZADA (CAGR)** — clave, los retornos totales
  crudos no son comparables (train expansivo vs 1 tramo); `session.rollback()`
  tras cargar (libera read-view en el cómputo puro); panels 1× por trailing (no
  por top_n); mínimo de ruedas por tramo; try/except en thread-start; costura
  conservadora (re-arme desde plano) documentada. **Con esto Nivel D está 100%.**
- **WF mejorado (commit 390840d)**: (1) **objetivo risk-adjusted** — elige la
  config por mejor **Sharpe** en el train (no retorno crudo), `_wf_score` testeado,
  guarda `train_sharpe`; (2) **batching N+1 resuelto** — nuevo `_load_raw` carga
  precios/scores por LOTE (IN de 200, patrón `backtest_service`), lo comparten
  nivel C (`run_portfolio_backtest`) y WF (`_load_universe`): de ~2 queries/activo
  a ~2/lote. Revisión adversarial: equivalencia de datos confirmada (sin regresión
  en nivel C), Sharpe sin hallazgos.
- **Método "regla dinámica" de teóricas — DESCARTADO (19-jul)**: es redundante
  con "derivada de estrategia". La estrategia YA lleva su filtro AND/OR de
  elegibilidad, y la cartera derivada toma el top-N de lo que pasa ese filtro →
  ya es una cartera filtrada. Única diferencia (menor): derivada = top-N rankeado;
  regla pura = todos los que pasan sin ranking — y eso se cubre con top-N grande.
  No se implementa el método aparte.
- **Pendientes (menores/opcionales)**: (ya no queda regla dinámica)
  (definir vocabulario), equity inline de las **derivadas** (background),
  **"promover a seguimiento"** (nivel C → teórica), **vínculo real→teórica**
  (tracking error); **Nivel D** (comparar corridas + walk-forward, migración);
  **multi-moneda** (modelo de divisores, necesita diseño) + **dividendos/splits**.
- **Patrón de UI aprendido (aplicar siempre)**: corrida en background = thread
  daemon + estado global + `dcc.Interval` polling + **`@safe_callback` en poll Y
  start** (si no, una excepción en el render deja el Interval prendido = spinner
  infinito); chequear visibilidad de estrategia con `visibility.current_viewer`;
  universo = `strat_res` con `score IS NOT NULL`. Modal ABM no cierra en error.
- **PENDIENTE**: teóricas (Fase 3 — migración + decisión de vocabulario de reglas
  dinámicas); multi-moneda (modelo de **divisores sintéticos**, necesita diseño) +
  dividendos/splits; nivel D (comparar runs + walk-forward) + persistencia de
  corridas de cartera (migración); pulido (tabs Señal/Reglas/Cartera en `/backtest`
  en vez de secciones apiladas; "promover a seguimiento").
