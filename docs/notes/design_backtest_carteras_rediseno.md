# Rediseño de Backtest + módulo de Carteras

> Diseño acordado con el usuario (18-jul-2026). Estado: **Fase 0 HECHA**
> (motor `portfolio_metrics` + vistas `portfolio_views` + 31 tests, suite verde).
> Siguiente: **Fase 2 (Carteras reales)**.
> Reemplaza el alcance de "fases 2/3" sueltas de `project_backtest.md`: ahora el
> backtest y las carteras son **dos módulos que comparten motor y vistas**.

## Motivación

La pantalla `/backtest` actual sólo hace **nivel A (calidad de señal)**: cuantiles/
IC/spread. No simula ni un trade, no tiene curva de equity ni PnL. En cambio el
gráfico de `/activo` ya tiene un **simulador de trades completo y homologado**
(`trade_simulator.py` ↔ `window._lwc.simulateTrades`) con entradas/salidas/stops/
trailing/cooldown y métricas en vivo — pero por-activo y sin persistir. La brecha:
`/backtest` opera sobre el universo pero **no puede responder "si operara esto,
cuánto gano"**, que es justo lo que el gráfico responde por activo. Además está
**pendiente** la funcionalidad de **carteras reales y teóricas (de seguimiento)**,
que resulta ser *el mismo motor y las mismas vistas* que el nivel de cartera del
backtest — cambia sólo la fuente de datos (histórico simulado / forward simulado /
real). Por eso se construyen juntos.

## Encuadre: dos módulos, motor y vistas compartidos

- **Backtest** = laboratorio de un *plan de operación* (estrategia + reglas del
  simulador + top-N + rebalanceo + costos) sobre el **pasado**. Snapshot inmutable.
- **Carteras** = biblioteca de **N** carteras de primera clase (como Activos o
  Estrategias), de dos tipos: **Seguimiento** (teóricas, sin plata real) y
  **Reales** (con registro de operaciones).

La **capa de vistas** (equity, drawdown, heatmap, KPIs, atribución, log) y el
**motor de métricas** se construyen una sola vez y sirven a ambos.

## Backtest — 4 niveles (tabs)

- **A · Señal** — lo actual (IC/deciles/spread). *¿Hay alpha en el ranking?*
- **B · Reglas** — fan-out de `trade_simulator` por-activo sobre el universo:
  win rate/PF, desglose de salidas por motivo, ranking de activos. *¿Qué tan
  buenas son las reglas en promedio?*
- **C · Cartera** — cartera top-N con equity vs benchmark, drawdown, heatmap,
  KPIs. **Dos sub-modos superpuestos**: *ranking puro* (rota top-N por score, sin
  reglas) y *con reglas (gated)* (entra si la regla de entrada dispara Y está en
  top-N; sale por SL/TP/trailing/score O cae del corte; cupos por mayor score) —
  la brecha entre las dos curvas = cuánto aportan los stops.
- **D · Comparar** — leaderboard de corridas + walk-forward.

**Benchmark doble**: EW del universo (línea base siempre) + índice elegible.

## Carteras — modelo

- **N de cada tipo**, no una sola.
- **Teóricas — 3 métodos de composición**:
  - *curada estática*: activos elegidos a mano (peso opcional).
  - *por regla dinámica*: membresía = regla sobre score/precio/grupo; se recalcula
    sola (ej. "las que están cayendo").
  - *derivada de estrategia*: top-N de un plan (= "promover a seguimiento" del
    backtest).
- **Reales — registro de operaciones** (el usuario prefiere ese nombre, no
  "ledger"): cada compra/venta es una fila (activo, fecha, cantidad, precio;
  **precio vacío → toma el de mercado de esa fecha**). Varios lotes por activo y
  parciales; posición (precio promedio ponderado) y P&L se **derivan** del
  registro.
- **Vínculo real→teórica OPCIONAL**: si una real apunta a una teórica objetivo se
  habilita el **tracking error** (real vs teórica es un caso, no el modelo).
- **Comparador multi-cartera**: superponer cualquier subconjunto + benchmarks.

## Principios (transversales)

- **No tocar el contrato homologado** `trade_simulator` ↔ `window._lwc.simulateTrades`
  ↔ `tests/fixtures/trade_simulator_cases.json`. Todo lo nuevo es un
  **agregador/orquestador por encima**; los **costos (bps por lado)** se aplican
  en el agregador, no en el motor.
- Migraciones **portables 0078+** (renderables offline contra MySQL y PostgreSQL,
  frontera 0076). SQL con sabor a motor → `db_compat`.
- Snapshots de backtest **inmutables**. Modales **ABM no cierran en error**.
  **Registrar** cada página (`_PAGES`/`_CALLBACKS`/navbar; `test_module_registration`).
- **pytest antes de cada push**; lo que toca la app viva se verifica en **Codespace**.
- Escalado a ~10k activos: lotear precios de a 200 (como `backtest_service`);
  cuidar memoria en el simulador de cartera.

## Fases

| Fase | Entrega | Depende | Migración | Estado |
|---|---|---|---|---|
| **0** | Motor de métricas + componentes de vista compartidos | — | ninguna (puro) | **HECHA** |
| **1** | Backtest nivel B (Reglas / fan-out por-activo) | 0 | siguiente libre | pendiente |
| **2** | Carteras **reales** (registro de operaciones) | 0 | 0080 | **en progreso** (esquema + derivación hechos) |
| **3** | Carteras **teóricas** (3 métodos) + vínculo/tracking | 0, 2 | siguiente libre | pendiente |
| **4** | Backtest nivel C (cartera top-N, 2 sub-modos) | 0 | siguiente libre | pendiente |
| **5** | Comparar (nivel D) + comparador multi-cartera | 0–4 | — | pendiente |
| **6** | Pulido (tema, export, gestión, lag/date_to) | — | — | pendiente |

Orden acordado: **0 primero**; después **2** y **4** en paralelo; **1** entra donde
convenga (es la extensión más barata).

### Fase 0 — Motor de métricas + capa de vistas
- `app/services/portfolio_metrics.py` (puro, sin BD): a partir de una serie de
  equity / retornos / lista de trades cerrados deriva **CAGR, retorno total,
  Sharpe, Sortino, max drawdown (+serie underwater), volatilidad, win rate,
  profit factor, expectancy, payoff, exposición, turnover, matriz de retornos
  mensuales, desglose por `reason`**. Convención del proyecto: no computable → `None`.
- `app/components/portfolio_views.py`: figuras Plotly / tablas reutilizables
  (equity+benchmark, underwater, heatmap, tiles KPI, tabla de trades/holdings,
  histograma, ranking), tema-aware.
- Tests: `tests/test_portfolio_metrics.py` con casos fijos.

### Fase 1 — Backtest nivel B
- `app/services/rules_backtest_service.py`: por lotes de 200, `load_series` +
  `simulate_trades(spec)` + agrega con `portfolio_metrics`. Spec desde los
  controles del gráfico (`spec_from_controls`).
- Modelo (0078): `backtest_asset_stat` (hija de `backtest_run`) + `run_type`.
- UI: tab Reglas en `/backtest`.

### Fase 2 — Carteras reales
Decisión tomada: registro **completo** (comisión + impuestos en columnas
separadas, dividendos/ajustes vía `kind`, multi-moneda por operación). Montos en
**Float** (consistencia con `prices`, evita el choque Decimal↔Float).

- **HECHO** — Modelo (migración **0080**, portable, renderiza offline en ambos
  dialectos): `portfolio` (id, name, ptype `seg|real`, owner_id, base_currency,
  benchmark_asset_id?, linked_portfolio_id?, created_at) + `portfolio_transaction`
  (portfolio_id FK CASCADE, asset_id, kind `buy|sell|dividend|split`, trade_date,
  quantity, price *nullable*→fallback mercado, commission, taxes, currency, note).
- **HECHO** — `positions_from_transactions()` en `portfolio_service.py` (puro,
  testeado): posición por activo con costo promedio ponderado, ventas parciales,
  P&L realizado neto de costos; cierre resetea. `unrealized_pnl()` también.
- **HECHO** — capa con BD (testeada con sqlite): `market_close()` (fallback de
  precio vía `Price`), `resolve_holdings()` (posiciones + valor de mercado +
  P&L realizado/no realizado), CRUD (`create_portfolio`/`list_portfolios`/
  `get`/`delete`/`add_transaction`/`list_transactions`).
- **HECHO** — visibilidad: `owner_id` + `is_public` (migración 0080), reusa
  `visibility.py`. Política elegida: **todas opt-in público** (privadas por
  defecto, el dueño puede compartir cualquiera; admin ve/edita todo).
- **HECHO** — `equity_series()` (valuación diaria mark-to-market, testeada):
  nav = cash + valor de tenencias; `initial_cash=0` → curva de P&L acumulado,
  `initial_cash=capital` → valor de cuenta. Helpers `price_calendar`,
  `_close_asof` (bisect). **Convención a fijar al armar la curva vs benchmark:**
  P&L vs valor-de-cuenta, y tratamiento time-weighted de depósitos/retiros.
- **HECHO (sub-paso A)** — página `/carteras` (`app/pages/carteras.py` +
  `app/callbacks/carteras_callbacks.py`), registrada en `_PAGES`/`_CALLBACKS` +
  navbar (Análisis → Carteras): biblioteca con filtro por tipo (DataTable) +
  alta/edición/baja con modal ABM (no cierra en error) + visibilidad
  (propias+públicas, `can_edit`). Suite verde (importa/registra OK).
- **HECHO (sub-paso B)** — detalle de la cartera (`render_detail`): KPIs
  (valor, P&L total/no realizado, posiciones) + curva de equity (valor de
  tenencias) + tabla de posiciones + registro de operaciones, reusando
  `portfolio_views`/`portfolio_metrics`; modal ABM de **operación** (alta al
  registro, no cierra en error). `realized_pnl_total()` en el servicio para el
  KPI (incluye posiciones cerradas).
- **Revisión adversarial multi-agente** (workflow, 4 lentes) sobre la página y
  callbacks — no corre local: cazó y se corrigieron 4 bugs de runtime —
  (1) selección desincronizada al recargar la tabla → recarga por señal monótona
  `cart-reload` + reset de `selected_rows`; (2) P&L realizado de posiciones
  cerradas omitido; (3) recarga por flanco de alert; (4) modal de operación sin
  limpiar campos. Suite verde.
- **Pendiente** — conversión multi-moneda as-of y dividendos/splits (follow-ups);
  y armar la **curva vs benchmark** (definir P&L vs valor-de-cuenta / TWR).
- **A verificar en Codespace** (toca la app viva): `git pull` + `alembic upgrade
  head` (aplica 0080) + abrir `/carteras`, crear una cartera real, cargar
  operaciones y ver KPIs/equity/tenencias.

### Fase 3 — Carteras teóricas
- Modelo (0080): `portfolio.composition_method` (`curated|rule|strategy`),
  `strategy_id?`, `rule_json?`, `rebalance`; tabla `portfolio_member`.
- Servicio: `resolve_membership(as_of)` (curada/regla/strategy top-N); equity
  forward + cambios/órdenes de hoy; tracking error si hay vínculo.
- **Decisión al entrar**: vocabulario de reglas dinámicas — ¿reusar
  `strategy_filter`/`signal_engine` o set acotado propio?

### Fase 4 — Backtest nivel C
- `app/services/portfolio_sim_engine.py` (puro, testeado): eje de fechas +
  cross-section de scores; sub-modo *ranking puro* y sub-modo *gated* (máquina de
  estados de cartera que orquesta la spec sin tocar el contrato).
- Modelo (0081): `backtest_equity_point`, `backtest_trade`, `backtest_attribution`.
- UI: tab Cartera (dos curvas) + "Promover a seguimiento" → crea teórica derivada.

### Fase 5 — Comparar (nivel D)
Comparador multi-cartera/multi-run (overlay + tabla KPI); walk-forward; leaderboard.

### Fase 6 — Pulido
Tema claro/oscuro (quitar hardcode), export CSV, borrar/gestionar runs y carteras,
exponer `lag`/`date_to`/ventana móvil.

## Anclas de código (jul-2026)

- Head de migraciones: **0078** (`0078_populate_ind_wide_tables`) → las nuevas
  desde **0079**, en orden de construcción (los números del cuadro de fases son
  tentativos).
- Motor: `simulate_trades(closes, scores, spec, percentiles=None)` y
  `summarize_trades(trades)` en `app/services/trade_simulator.py`;
  `load_series(asset_id, strategy_id)` y `spec_from_controls(vals)` en
  `app/services/trade_optimizer.py`.
- Persistencia de referencia: `BacktestRun` + tablas hijas
  (`app/models/backtest.py`, migración 0070) + thread daemon con polling
  (`app/callbacks/backtest_callbacks.py`).
- Motor puro del nivel A: `app/services/backtest_engine.py` (reutilizable).

## Mockup de referencia

Mockup navegable (datos ilustrativos) publicado como Artifact con los dos módulos
y todos los tipos de vista — sirve de referencia visual del rediseño.
