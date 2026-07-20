---
name: pendientes-proxima-sesion
description: Tareas acordadas pendientes al cierre de la sesión del 9-jul-2026
metadata: 
  node_type: memory
  type: project
  originSessionId: 4589549a-6aad-4d01-a4e5-246338bd5547
---

**Sesión 14-jul-2026 (4, commits `b7b0ad2` `4bcd715` `bb2ab7e`, pusheados):
iteración del simulador tras uso real del usuario.** (1) Ayudas en pantalla:
popover "?" con referencia completa + tooltip por modo. (2) Rediseño de
taxonomía a pedido del usuario: modo OPCIONAL ("Sin salida por score"),
"horizonte fijo" eliminado como modo (era el tope N ruedas duplicado —
modo=señal, tope=precio/tiempo), topes COMBINABLES (spec.caps lista, gana
el primero en orden de lista; UI con 4 checkbox+valor). (3) Frenos de
re-entrada anti-whipsaw: rearm por cruce (desarmado tras salida, re-arma
al caer bajo el umbral) + cooldown N ruedas — opcionales, apagados por
default. Contrato homologado en cada paso (31 casos en fixtures).
**IMPORTANTE (el usuario lo marcó por 3ª vez): NO editar sin proponer y
esperar el "sí" — ni ante pedidos directos ni reportes de bugs.**

**Continuación 15-jul-2026 (5, commits `c969212` `dfcbac3`, pusheados):
profiling a fondo de señales/estrategias (pedido explícito: "lo más
crítico") + limpieza post-auditoría.** Dos scripts nuevos de cómputo puro
sin BD (corren en cualquier máquina): profile_signal_pipeline.py y
profile_trade_optimizer.py. Hallazgos: (1) el optimizador NO necesita
optimización (0.6 ms/combo; 1600 combos en 0.95s); (2) ~75% del cómputo de
señales era despacho por llamada de evaluate() → FIX: señales COMPILADAS a
closures (signal_engine.compile_evaluator, cableado vía _prepare_signals
["compiled_by_id"]) — evaluadores 1.9×, pipeline 1.6× (8.92→5.71 ms/fecha;
proyección 10k activos: 7.5→4.8 min de CPU). Red: 4 tests de propiedad
hypothesis (compilado ≡ evaluate, exacto, con NaN) + paridad intacta.
Hotspot residual: filtro (_resolve/_compare) — solo vale vectorizar cuando
los 10k sean reales. Limpieza previa (`c969212`): assets/chart.js (252
líneas muertas) y dropdown_dark.js eliminados; spec_from_controls y
load_series movidas a trade_optimizer con tests (el orden posicional de
_SIM_CONTROL_IDS quedó fijado por test). 497 tests.

**Continuación 15-jul-2026 (4, commits `b3c1ed8` `f96db8e` `1b52ff5`,
pusheados):** BUG RAÍZ del colapso encontrado con captura del usuario:
Bootstrap genera `d-flex` con !important y PISABA el display inline de los
callbacks de colapso (nunca funcionó desde 039f7eb) — fix: sacar d-flex de
los 3 contenedores toggleados, display exclusivo del callback (comentarios
de advertencia). "Cruce" default ON. Dropdowns: menú 300px + opciones
compactas (CSS global). **OPTIMIZADOR de parámetros** (`1b52ff5`):
trade_optimizer.py puro (grillas gruesas solo sobre condiciones activas,
poda de incoherentes, objetivo retorno compuesto con mín. 10 trades,
train/test 70/30) + botón "Optimizar" con modal top-10 Train/Test y
"Aplicar" por fila. TERCER espejo del armado de spec:
optimizer_callbacks._spec_from_controls (junto a buildSpec JS y
_SIM_CONTROL_IDS — sincronizar los 3). Tras primera corrida real del
usuario (Percentil≥80/Percentil<30/Cruce: train +292% / test +21%, los
trades cuadraron 122+15=137 con el gráfico): `b595217` agrega "total"
compuesto al label del gráfico (campo total_ret en summarize_trades +
espejo JS) — regla de lectura: el optimizador reporta train/test POR
SEPARADO, el gráfico corre la historia entera. 489 tests. Pendiente de diseño
aceptado: la versión robusta del optimizador (sobre el universo) es parte
de la fase 2 del backtest. También pendiente: 2 edits de texto en
/backtest (equivalencia de vocabulario con el simulador + matiz pct vs
cuantiles) — propuestos y aceptados conceptualmente, sin aplicar.

**Continuación 15-jul-2026 (3, commits `8973b66` `c45304a`, pusheados):**
iteración de UX del simulador: rótulos sin acrónimos ("Entrada por (todas)",
"Score ≥"/"Percentil ≥"/"Enfriamiento"/"Percentil <"), grupo propio
"Condiciones de re-entrada", resultado dentro del borde ind-group con
fuente 0.82rem, tooltips en TODOS los controles de la pantalla (helper
_tip/_screen_tips), AND/OR explícito en rótulos+tooltips. Salida nueva
`absolute_above` ("Abs >"): take profit del score, lógica contrarian, con
acople inverso (piso = entrada Sc). HALLAZGO CLAVE del "bug" de colapso:
los 11 callbacks están registrados y los divs arrancan ocultos (verificado
importando el módulo con yfinance stubbeado) — el problema real era que el
estado ACTIVO de los toggles (gris .active de bootstrap) era invisible en
dark; fix CSS: activos en celeste #38bdf8. **PENDIENTE CODESPACE: el
usuario debe re-verificar MACD/ATR con los colores nuevos** (si ve params
con botón gris apagado, ahí sí hay bug real). 477 tests.

**Continuación 15-jul-2026 (2, commits `09bdcc1`..`d295be0`, pusheados):**
fix 404 de /backtest (página sin registrar en _PAGES — sin auto-discovery;
red nueva: tests/test_module_registration.py ata filesystem a las listas,
convención en CLAUDE.md). Bug perseguido en vivo: las líneas de umbral del
panel de score NUNCA se pintaban desde el refactor de segmentos (5351a2d) —
createPriceLine no renderiza (ni en serie whitespace ni colgado de un
segmento con datos); solución final `a598cc3`: umbrales como SERIES
horizontales punteadas (mismo camino de render que los segmentos).
**REDISEÑO GRANDE (`d295be0`): spec de tres listas** — entries (AND:
Sc≥/Pct≥), score_exits (OR combinables: Abs</Ent−Δ/Máx−Δ/Media k/Pct<),
caps (OR); precedencia filtro>precio>score; UI unificada checkbox+valor
con título "Simulación de estrategias", grupos rotulados y "Resultado de
la simulación:" en línea propia; sliders eliminados; acople vía max
dinámico; buildSpec único en JS (orden posicional en _SIM_CONTROL_IDS).
44 tests del simulador, 476 total. **PENDIENTE CODESPACE: pull +
REINICIAR PROCESO + hard refresh; probar el panel nuevo completo.**

**Continuación 15-jul-2026 (commits `a632933` `38ebc8b`, pusheados):**
ajustes tras más uso real: default "Sin salida por score", min/max en las
métricas del label (con retornos coloreados verde/rojo, innerHTML),
renombres claros ("% ganadoras", "cierres por filtro"). `entry_pct` nuevo
en el contrato (toggle Sc|Pct: la entrada y el re-armado pueden ser por
percentil, independiente del modo de salida — el modo percentil ya no
convierte la entrada). Acople de sliders: salida ≤ entrada cuando
comparten unidad (Sc+absoluto, Pct+percentil), techo dinámico del slider.
Fix clave del panel de score: las price lines NO participan del
auto-escalado en lightweight-charts — la línea de entrada existía pero
quedaba fuera del rango visible si los scores no la cruzaban; `addSeries`
ganó `autoscaleRange` (autoscaleInfoProvider) para forzar los niveles
dentro de la escala. 35 casos en fixtures, 468 tests.

**Sesión 14-jul-2026 (3, commit `9ad0cba`, pusheado): percentil
precalculado en strategy_result (migración 0071).** El usuario reportó 62s
en la ventana PERCENT_RANK del overlay (materializaba TODA la estrategia
para filtrar un activo, y se pagaba en cada selección aunque no se usara
el modo percentil). Fix estructural: columna `pct` escrita por AMBOS
caminos del pipeline vía `strategy_service.percent_ranks` (helper puro,
semántica SQL PERCENT_RANK, paridad extendida a pct); el overlay lee
`date, score, pct` de una sola query indexada. De paso: conftest borra el
stub sqlite en cada corrida (create_all no altera tablas existentes — el
primer cambio ADITIVO de esquema rompió la suite con el stub viejo).
**PENDIENTE CODESPACE: `alembic upgrade head` (0070+0071) + "Recalcular
completo" de Señales y Estrategias — la historia previa queda pct=NULL y
el modo percentil no ve esas fechas hasta recalcular.**

**Sesión 14-jul-2026 (2, commit `4106525`, pusheado): simulador de trades
con modos de salida configurables.** Incluye además: controles de
estrategia movidos a fila propia del toolbar, y fix del pisado de `var pc`
en el JS del gráfico (la EMA de régimen y las zonas ATR se dibujaban en el
panel de score cuando la estrategia estaba activa — `var` es
function-scoped; la variable del panel de score ahora es `stratPc`, con
comentario de advertencia). El fix del régimen/ATR y el layout NO son
testeables por pytest (JS/Dash puro, verificar en vivo). El usuario pidió
reemplazar la salida por umbral absoluto del overlay de estrategia por un
menú de alternativas, pensado como semilla del módulo de backtesting.
Diseño acordado: motor Python puro `app/services/trade_simulator.py` =
CONTRATO (fixtures JSON en tests/fixtures/trade_simulator_cases.json, 24
tests) + espejo JS `window._lwc.simulateTrades` en chart_callbacks.py.
**REGLA NUEVA DEL SISTEMA (pedida explícitamente): mantener HOMOLOGADAS
ambas implementaciones — todo cambio de semántica toca los dos archivos +
fixtures en el mismo commit (documentado en CLAUDE.md).**
6 modos: absolute / delta_entry / trailing_score / score_ma / horizon /
percentile (percentil entra Y sale por percentil; serie de percentiles
server-side con PERCENT_RANK). Tope opcional ÚNICO (a elección: max_bars /
stop_loss / trailing_stop / take_profit) — uno solo a la vez, para poder
medir cuál rinde mejor. Precedencia: filtro > tope > modo. Elegibilidad
perdida (barra propia sin score interior) = cierre forzado SIEMPRE; cola
sin score (señales aún no corridas hoy) NO cierra. Métricas nuevas en el
label: cerradas, % positivas, media, mediana, ruedas, cierres por filtro.
**PENDIENTE CODESPACE: probar los 6 modos + topes en el gráfico** (dropdown
reconfigura el slider por modo; percentil re-rangea también la entrada).

**Sesión 14-jul-2026 (commit `57f6883`, pusheado): baja de divisor de
divisas en background.** El usuario reportó que eliminar un conversor
tardaba minutos con el modal de confirmación colgado (el request HTTP se
cortaba; el `_remove_lock` sí evitó el doble borrado en el re-click).
Fix: modal se cierra al confirmar, borrado en thread daemon + polling
(`ars-remove-interval`/`ars-remove-alert`), `progress_cb` nuevo en
`purge_assets` (avance por tabla), tabla/stats se refrescan al terminar.
**PENDIENTE CODESPACE: probar la baja real de un divisor** (flujo
modal→alerta→progreso solo se ve con la app viva). Anotado sin tocar:
query lenta de `strategy_result` (overlay del visualizador,
"Creating sort index") vista durante el DELETE masivo — hacer `EXPLAIN`
con la base tranquila antes de decidir si amerita índice.

**Sesión 9-jul-2026 — auditoría de correctness del sistema tail-mode +
performance de fundamentales, 4 commits locales sin pushear (`8aff073`,
`a75585d`, `d1474cb`, `f1f3544`):**

El usuario planteó la duda "toda esta ingeniería de caché ¿no hace propenso
a errores de cálculo?" — auditoría dirigida encontró y arregló 2 bugs
reales preexistentes (no introducidos en esta sesión) en
technical_service.py, además de lo que ya estaba en curso (punto 7 de más
abajo):

- `8aff073`: `_confirmed_empty_fast_path` — activos con serie 100% inválida
  (`_series_stats` devuelve `None`) nunca cacheaban esa confirmación, así
  que repetían el camino lento para siempre en cada delta. Motivo nuevo
  `"empty"` separado de `"gap"` en path_counts/log — deliberadamente
  excluido del wire format `__pc__:` que ve el panel de Centro de Datos
  (4 campos fast/gap/checksum/bench, sin tocar), para no mezclarlo con
  huecos reales que sí ameritan revisión.
- `a75585d`: `_pairs_to_write` nunca borra filas, solo agrega/actualiza —
  si un valor pasa de válido a inválido (activo transición, benchmark
  removido) la fila vieja quedaba obsoleta para siempre. Fix:
  `_stale_dates_to_delete` + DELETE puntual en `_write_ind_series`.
- `d1474cb`: **el más serio de los dos.** `trend_daily/weekly/monthly` NO
  tenía la compuerta de checksum que sí tienen `volatility_*`/
  `atr_percentile_*`, pese a depender de `regime_cfg` (editable por el
  admin, EMA recursiva sobre TODA la historia). Sin la compuerta, editar
  la config y correr un delta normal solo actualizaba la cola reciente,
  dejando TODA la historia de tendencia calculada con parámetros viejos,
  silenciosamente, para los 554 activos — el UI (`regime_config_callbacks.py`)
  ni siquiera especifica qué botón usar ("Recalculá los indicadores").
  Fix: agregar los 3 códigos a `_CHECKSUM_DEP_CODES`, mismo mecanismo ya
  probado. **Primera corrida post-deploy cae al camino lento para
  trend_* en TODOS los activos (aprende el checksum inicial), se
  autocorrige desde la segunda en adelante — mismo patrón que
  volatility/atr.**

Auditoría adicional sin hallazgos: orden `recompute_current_indicators` →
`backfill_all_indicator_values` (ya corregido en sesión anterior, sigue
bien); resto de `_bf_*` no tiene dependencia de config admin-editable
(`_MA_PERIODS` de dist_optimal_sma_* es constante hardcodeada);
`synthetic_service.py` no comparte este patrón de caché.

**Hallazgo separado, no relacionado (mismo día): delta de fundamentales
más lento que el full.** El usuario notó que "Ratios fundamentales"
tardaba más en delta (50s) que en full (39s) pese a hacer menos trabajo
por código, y que el panel no mostraba el thread. Causa raíz:
`_run_ratios_and_backfill` invierte el orden de fases entre modos (full:
backfill primero, ratios después; delta: ratios primero, backfill
después) — `recompute_all_ratios` hacía 2 queries `GROUP BY MAX(date)`
contra TODA la tabla `prices`, caras con buffer pool frío (delta, corre
primera) y baratas con buffer pool tibio (full, corre después de que
backfill ya tocó esos datos) — asimetría de ~30s+ que no tenía que ver
con el trabajo real. Fix (`f1f3544`): `price_cache` se carga una vez en
`_run_ratios_and_backfill` y se comparte entre las 2 fases (mismo patrón
ya usado para `quarters_cache`); `recompute_all_ratios` deriva
`latest_price`/`price_1y` del caché en memoria (`_price_asof_from_cache`,
bisect) en vez de esas 2 queries. De paso: `recompute_all_ratios`
commiteaba una vez por activo (322-351 round-trips secuenciales) — no es
el cuello de botella dominante hoy pero pesa a escala de 10000 activos;
ahora cada activo corre en su propio SAVEPOINT (aísla errores puntuales
igual que antes) pero el commit real se batchea cada 50
(`_RATIO_COMMIT_BATCH`). También se agregó `_worker_slot()` a
`backfill_all_fundamental_values` (mismo patrón que technical_service.py)
— el panel ya sabía renderizar el tag `[wN]`, fundamentales nunca lo había
emitido.

**Pusheado (9-jul-2026) y VERIFICADO con datos reales el fix de
fundamentales:** full 34s (workers arrancan a los ~7s, sin cambios) vs
delta 21s (workers arrancan a los ~9s, antes ~38s) — el hueco frío
desapareció casi del todo, y de paso delta pasó a ser más rápido que full
en total (esperable, hace menos trabajo; antes el orden de fases lo
escondía). Tag `[wN]` visible en todas las filas del panel, confirmado
que `pb`/`pe_growth_yoy`/`pe_ttm`/`ps_ttm` comparten worker (son el
thread combinado de indicadores diarios).

**PRÓXIMO PASO: correr un delta real de indicadores técnicos en el
Codespace para confirmar que `trend_*` cae al lento una vez (aprende el
checksum inicial) y se autocorrige en la corrida siguiente — todavía sin
verificar con datos reales.**

**Tercer bug de la misma familia (commit `dbdbf0e`, local, sin pushear
— el usuario preguntó puntualmente por `relative_strength_52w`):**
depende del VALOR de los precios del benchmark, no solo de
`Asset.benchmark_id` — `bench_stale` detecta cambio de id, pero no
detecta si se redescargan/corrigen precios ya guardados del benchmark
vigente (`redownload_prices` admite apuntar a un activo puntual). Mismo
fix: agregado a `_CHECKSUM_DEP_CODES` (convive con `_BENCHMARK_DEP_CODES`,
una compuerta por motivo). **PRÓXIMO PASO: pushear junto con los demás y
verificar en el Codespace igual que `trend_*`.**

**Cuarto bug, encontrado VERIFICANDO el tercero con datos reales (commit
`a41c012`, local, sin pushear):** `trend_*` bajó a 0 limpio (553→0→0),
pero `relative_strength_52w` quedó estancado en 46 activos con
`checksum` estable (nunca 0) en dos corridas seguidas. IDs consecutivos
(1001-1047) — no es ruido. Antes de tocar código, el usuario pidió
verificar con una query real (no asumir): `SELECT ... FROM
ind_asset_meta WHERE code='relative_strength_52w' AND asset_id IN
(...)` confirmó `max_date` 3 días atrás de la fecha de la corrida —
la última fecha VÁLIDA propia de esos activos queda atrás de la última
fecha de su calendario (el mecanismo exacto de por qué no se resolvió
del todo — `_vlkup` usa "precio más reciente disponible", no debería dar
NaN por un benchmark simplemente atrasado un día; posiblemente el hueco
es más profundo o hay otra causa — pero no hacía falta resolverlo para
el fix).

Causa raíz real: el checksum se guardaba con `vals_list[:-1]` (todo
menos la última POSICIÓN del array) pero se comparaba con
`vals_list[:k]` (posición real de `mx` cacheado, vía
`_delta_tail_start`) — cuando `mx` ≠ última fecha del calendario, esos
dos slices tienen distinto largo y el checksum nunca puede coincidir,
para siempre. El activo queda pagando el camino lento sin necesidad
(no es un bug de datos — el camino lento sigue escribiendo bien — es
desperdicio de trabajo).

Fix: `_checksum_prefix(dates_list, vals_list, own_mx)` — nueva función
pura, guarda con la posición real de la propia última fecha válida
(`stats[1]`), no con `[:-1]` a ciegas. Requirió reordenar: `stats` ahora
se calcula ANTES del bloque de checksum (antes era al revés). 4 tests
nuevos. En principio el mismo bug podría afectar a `trend_*`/`volatility_*`
si alguna vez tienen una zona sin confirmar justo en el tramo final (no
se vio en las corridas de prueba, pero la función queda correcta para
ese caso también).

**PRÓXIMO PASO: pushear cuando el usuario confirme, correr un delta más
en el Codespace y verificar que `relative_strength_52w` también baja a
0 desde la segunda corrida (no solo `trend_*`).**

**Quinto bug, mismo patrón (commit `0be9841`, local, sin pushear —
el usuario preguntó puntualmente por `dist_optimal_sma_*`):**
depende de `best_sma_*`, recalculado TODOS los días
(`_find_best_ma`) — si un día nuevo de precio hace que otro período
gane, la fórmula de TODA la historia cambia (`rolling(best_val)` con
un `best_val` distinto), no solo la cola, y no había compuerta para
detectarlo (el chequeo de huecos de calendario no sirve acá, porque no
deja huecos). Mismo fix: agregado a `_CHECKSUM_DEP_CODES`. No afecta a
los ~23/11/13 activos con `best_sma_*` estructuralmente inválido (gap
legítimo de mitad de serie, ya documentado, sin relación con este fix).
**PRÓXIMO PASO: pushear junto con los demás y verificar en el
Codespace.**

**Cierre de sesión (9-jul-2026): 2 commits más, pusheados
(`676bcb1`, `0fa7fb9`), ninguno verificado en vivo todavía —
esta máquina Windows no puede levantar la app completa (sin
mysqlclient/MySQLdb ni yfinance).**

- `676bcb1`: "Actualizar Precios"/"Actualizar Fundamentales" (Centro de
  Datos, y el scheduler diario que usa la misma función) dejaron de
  recalcular indicadores/ratios activo por activo inline — ahora solo
  descargan datos y encadenan `update_indicator_history()`/
  `_run_ratios_and_backfill(force=False)` (mismo sistema de delta con
  todos los fixes de esta sesión). Antes el scheduler diario NUNCA
  ejecutaba el sistema de delta — dependía de que alguien entrara a
  Centro de Datos y clickeara "Ejecutar" a mano. Se encontraron y
  arreglaron 2 callbacks (páginas standalone de Precios y Fundamentales)
  que se habrían roto: sus `progress_cb` solo aceptaban 2 argumentos,
  el sistema de delta ahora manda 3 (con label de fase).
  **PRÓXIMO PASO CRÍTICO: probar "Actualizar Precios" a mano en el
  Codespace ANTES de dejar correr el scheduler nocturno desatendido.**

- `0fa7fb9`: sacados los botones de acción masiva duplicados
  ("Actualizar todos"/"Redescargar todos") de las páginas standalone de
  Precios y Fundamentales (ya cubiertos por Centro de Datos). Fundamentales
  emparejado con Precios: selección múltiple en la tabla (antes
  `row_selectable="single"`), "Actualizar seleccionados" ahora procesa
  todos los marcados (antes solo el primero pese a decir "seleccionado"),
  nuevo botón "Redescargar seleccionados" (no existía ninguna versión).
  `redownload_all_fundamentals` ahora acepta `asset_ids` opcional.
  **Sin verificar en vivo**: revisado a mano correspondencia Output/Input
  entre layout y callbacks + `py_compile` limpio, pero ningún click real.

Commits de la sesión completa (9-jul-2026), todos pusheados en orden:
`b67a3d2` `8aff073` `a75585d` `d1474cb` `f1f3544` `dbdbf0e` `a41c012`
`0be9841` `676bcb1` `0fa7fb9` `8a66b78`.

**`8a66b78`: pantalla nueva `/admin/verify`** (link en navbar → "Datos de
Mercado" → "Verificación de Datos"). Dos secciones independientes:
1. Corre `pytest tests/ -q` como subproceso desde un botón, muestra
   salida cruda + resumen OK/fallo.
2. "Verificación de datos reales": recalcula en memoria (sin escribir)
   los indicadores de una muestra de activos y los compara contra
   `ind_{código}`, fecha por fecha — parámetros (códigos/muestra/tickers)
   elegibles desde la pantalla. Solo lectura, segura contra producción.
   La lógica vive en `app/services/verification_service.py`, compartida
   con `scripts/verify_delta_correctness.py` (ahora wrapper CLI delgado).
**Sin verificar en vivo** (igual que `676bcb1`/`0fa7fb9`) — esta máquina
no puede levantar la app completa.

**`8ed345c`: 3 validaciones más, pedidas explícitamente por el usuario
tras preguntar "qué más podríamos agregar" — property-based testing,
chequeos de cordura, y extender la verificación a fundamentales.**

- `tests/test_delta_tail_properties.py` (hypothesis, nueva dep dev):
  5 propiedades sobre datos generados al azar (no ejemplos a mano).
  La primera (`test_checksum_guardado_coincide_con_comparacion_
  siguiente_corrida`) encodea EXACTAMENTE la invariante que rompía el
  bug de `a41c012` — verificado a mano simulando el bug viejo
  (`vals[:-1]` en vez de `vals[:k]`): la propiedad lo detecta al toque.
- `check_sanity()` en `verification_service.py`: valida que un valor
  tenga sentido (RSI en [0,100], `trend_*`/`volatility_*` en una
  categoría real, retornos/ratios dentro de límites laxos) —
  independiente de la comparación delta-vs-fresco, agarra bugs de
  FÓRMULA (si la fórmula está mal, ambos caminos calculan lo mismo mal).
  Corre automático sobre cada valor fresco en `verify_asset_code`.
- `run_fund_verification()`: mismo patrón para `ind_fundamental_*`.
  Motivado por un hallazgo real charlando el alcance: el delta de
  fundamentales (`_backfill_fund_indicator`) SÍ existe (solo escribe
  fechas faltantes) pero es más simple que el de indicadores técnicos —
  si un trimestre viejo se revisa después de escrito, el ratio histórico
  de esa fecha NUNCA se recalcula (salvo el último trimestre, tratado
  como preliminar). Sin protección hoy, esta verificación lo detectaría.
- `/admin/verify` y el CLI (`scripts/verify_delta_correctness.py`) ahora
  tienen selector de dominio (indicadores técnicos / ratios
  fundamentales) — repuebla el dropdown de códigos según cuál se elija.
- 18 tests nuevos (5 property-based + 13 de `check_sanity`), suite en
  verde. **Sin verificar en vivo** la parte de fundamentales del panel
  web (misma limitación de siempre).

**`b327560`: primer bug real encontrado probando en vivo — `/admin/verify`
tiraba 500 al cargar.** `dbc.Spinner` (dash-bootstrap-components 2.0.4 en
el Codespace) no acepta `style` genérico, solo `spinner_style`. Fix:
envuelto en un `html.Div` plano con el id que ya usan los callbacks (sin
tocar `admin_verify_callbacks.py`). De paso se movió el link de navbar de
"Datos de Mercado" a "Administración" (junto a Consola SQL/Limpieza de
datos), a pedido del usuario — encaja mejor temáticamente ahí.
**Este tipo de bug (props de componente Dash) es invisible a
py_compile/pytest — solo aparece con la app corriendo de verdad.**

**PRÓXIMO PASO (orden recomendado en el Codespace):**
1. `git pull`.
2. `pip install -r requirements-dev.txt` (agrega `hypothesis`, necesaria
   para que `pytest` corra los tests nuevos).
3. Entrar a `/admin/verify`, correr la suite de pytest (debería dar OK) y
   la verificación de datos reales — primero dominio "Indicadores
   técnicos" apuntado a `trend_*`, `relative_strength_52w`,
   `dist_optimal_sma_*` (los códigos tocados esta sesión) sobre una
   muestra grande; después dominio "Ratios fundamentales" sobre una
   muestra también. Es la confirmación real de que todo calcula bien,
   no solo que no crashea.
4. Probar "Actualizar Precios" en Centro de Datos a mano (crítico, corre
   solo todas las noches vía scheduler desde `676bcb1`).
5. Entrar a las páginas de Precios y Fundamentales, confirmar selección
   múltiple y los botones que quedaron (`0fa7fb9`).

Pendientes acordados con el usuario (julio 2026), en orden:

0. **HECHO (commits d6394b4, 1ad3b50, 43402f7, 1620963): camino rápido del delta
   técnico completo** — los 24 códigos con historia escriben solo la cola
   cuando es seguro (_DELTA_TAIL_MODE + _delta_tail_start, prefetch por
   GROUP BY); delta bajó de 5m35 a 2m48-2m52 en las corridas del usuario.
   Dos compuertas de invalidación adicionales (tabla ind_asset_meta,
   migraciones 0053/0054, requiere alembic upgrade head):
   - relative_strength_52w: _stale_bench_assets detecta cambio de
     Asset.benchmark_id (editable desde el ABM) y fuerza dict-compare
     en ese activo.
   - volatility_*/atr_percentile_* (full_sample, antes excluidos por
     completo): _series_checksum hashea el prefijo histórico calculado;
     si coincide con el guardado no hubo deriva de percentiles y alcanza
     con la cola; si no, dict-compare solo para ese activo.
   Fix de precedencia (commit 1620963) también hecho: rebuild_indicator_history
   corre recompute_current_indicators ANTES que backfill_all_indicator_values.

   **RESUELTO (commits 07ce585, cc82517, ef3c2a4)**: la hipótesis del checksum
   de dur_regime se descartó con logs reales (checksum=0, ~100% camino rápido
   en todos los códigos). El costo real se aisló con
   scripts/profile_vol_zones.py (cProfile single-thread, sin contención de
   GIL): volatility_daily 15.0ms/rep vs rsi_daily 5.5ms vs trend_daily 4.0ms.
   Dos causas concretas encontradas en el profile:
   - `_atr_series` usaba `pd.concat([...], axis=1).max(axis=1)` para el true
     range — reducción por filas, notoriamente lenta en pandas.
   - `_compute_vol_zones` pasaba una `pd.Series` a `np.nanpercentile` (x3):
     numpy despacha vía `__array_function__` y termina recorriendo la
     maquinaria pesada de pandas en vez de ir directo a la implementación en C.
   Fix: ambos casos migrados a arrays numpy puros (`np.fmax`, no `np.maximum`,
   para preservar el skipna de pandas en la fila 0 donde prev_close es NaN).
   186 tests OK. Commit local `ef3c2a4`, sin pushear todavía (usuario pidió
   solo commit local por ahora).
   **PRÓXIMO PASO: pushear cuando el usuario confirme, hacer pull en el
   Codespace y volver a correr profile_vol_zones.py + una corrida real del
   delta para confirmar la mejora esperada (~15ms → ~8ms/rep).**

   Pendiente adicional: replicar el patrón tail-mode en fundamental_service
   (verificar antes la semántica de reportes que llegan tarde: ¿los ratios
   históricos se recalculan retroactivamente?).

1. **HECHO (commit 42aa6e5): vectorización de zonas** — regime 12×, mapeo 63×,
   vol 2× (resto numpy). PERO el benchmark reveló que el grueso del tiempo real
   de volatility_daily NO era ese loop (~16ms/activo vs ~570ms/activo medidos).
   **Hipótesis desmentida (jul-2026)**: vectorizar la comparación de
   _pairs_to_write con numpy resultó MÁS LENTO que el escalar (0,5-0,7×;
   el dict/set escalar ya cuesta ~1 ms/activo) — se revirtió y quedó nota en
   el docstring. Nuevo sospechoso del costo del delta: el prefetch
   (fetchall de ~500k filas fecha+valor por chunk) + contención del GIL entre
   workers. Posible palanca futura: checksum por activo para saltear la
   comparación entera cuando nada cambió.
2. **HECHO (commit 04425cc): panel del Centro de Datos** — _announce_worker_union
   emite la unión de los 36 códigos al inicio de update/rebuild_indicator_history.
3. **Indicadores nuevos a agregar** (elegidos, sin arrancar): dist_optimal_ema
   d/w/m, MACD histograma d/w/m, Estocástico %K, Bollinger %B, estado P&F.
   Patrón: función _bf_* + entrada en _BUILTIN_INDICATORS + migración de tabla ind_*.
4. Ofrecido y sin decidir: audit de excepts que muestran error sin loguear;
   migrar prices a DOUBLE (precisión FLOAT ~7 dígitos pierde centavos del MERVAL).

5. **HECHO (commit 2162a02, pusheado): caché de tail_stats en ind_asset_meta.**
   La palanca futura anotada en [[project_scaling_target]] (cachear
   min/max/count en vez de recalcularlo con full-scan) se implementó:
   migración 0055 agrega min_date/max_date/row_count a ind_asset_meta;
   backfill_indicator los recalcula en cada corrida exitosa (_series_stats,
   derivado de la serie completa recién calculada, no de un delta
   aritmético) y los escribe con _upsert_ind_stats_meta (función separada de
   _upsert_ind_asset_meta a propósito, para no pisar con NULL cuando bench/
   checksum/stats tienen distinto conjunto de asset_id). _query_tail_stats
   ahora lee ese caché (lookup por PK) en vez de escanear ind_{code}.
   Propiedad de seguridad clave: cualquier falla a mitad de camino deja el
   caché AUSENTE o más chico, nunca optimista (nunca hace creer que no hay
   huecos cuando sí los hay). De paso se corrigió un bug de atomicidad
   preexistente: el TRUNCATE de un force/rebuild ahora limpia
   ind_asset_meta (incluye benchmark_id/checksum) en el mismo commit, no
   sólo al final — si el proceso se cae a mitad de un rebuild, el caché
   queda ausente en vez de apuntar a una tabla ya truncada.
   Alcance deliberado: no se tocó backfill_asset_history (alta de activo
   nuevo) ni compute_current_indicators/_upsert_ind (recompute del valor de
   hoy) — ya hoy no actualizan benchmark_id/checksum para esos casos
   puntuales y el sistema se autocorrige en el siguiente delta masivo;
   mismo criterio ya aceptado para esas dos compuertas. Tampoco se blindó la
   consola SQL admin (permite DML arbitrario sobre ind_*/ind_asset_meta sin
   pasar por estos servicios) — mismo trust boundary que ya existía para
   benchmark_id/checksum (admin único hardcoded); documentado en el
   docstring de IndAssetMeta que una edición manual ahí requiere forzar un
   rebuild del indicador afectado.
   **PRÓXIMO PASO: correr `alembic upgrade head` en el Codespace/entorno
   real. La primera corrida de delta post-migración cae al camino lento
   para todos los activos en los 24 códigos tail-mode (caché vacío) — es
   esperado, se autopobla en esa misma corrida. Repetir el profiling real
   para confirmar la mejora.**

6. **HECHO (commit 42ccd65, pusheado): botón "Recalcular caché" en Centro
   de Datos.** Complementa el punto 5: `reconcile_ind_asset_meta` (misma
   sesión de service que backfill_indicator) reconstruye desde cero, por
   código, TODO lo cacheado en ind_asset_meta — no solo min/max/count.
   min_date/max_date/row_count se recalculan del full-scan real de
   ind_{code} (verificable sin ambigüedad); benchmark_id/checksum se
   BORRAN en vez de adivinarse (no hay forma de derivarlos sin recomputar
   el indicador entero) — fuerza el camino lento una vez en el próximo
   delta normal para esos ~7 activos-código, que se autocorrige solo.
   Botón nuevo en la tarjeta de Indicadores Técnicos, mismo patrón de
   callbacks/estado que "Ejecutar"/"Recalcular completo" (thread daemon +
   `_state`/`dcc.Interval`, sin long-callback nativo de Dash). No se
   colgó de ningún scheduler todavía (a pedido del usuario, "para el
   futuro"); la firma `progress_cb=None` + limpieza de sesión propia ya
   la deja lista para eso.
   **Sin verificar en vivo**: esta máquina Windows no tiene mysqlclient
   instalado ni una instancia de MariaDB corriendo (el stack completo con
   datos reales solo existe en el Codespace) — la verificación in situ
   (clickear el botón, confirmar que la barra avanza y que
   `ind_asset_meta` queda consistente) quedó pendiente para el Codespace.

7. **VERIFICADO con datos reales (jul-2026) y con hallazgos nuevos:**
   el usuario corrió el delta dos veces post-migración 0055: primera
   corrida (cold-start, caché vacío) 7m32s, segunda corrida (caché tibio)
   2m13s — confirma que el diseño se autocorrige en un ciclo, tal cual lo
   planeado. El contador `lento=N` (con desglose gap/checksum/bench, ver
   commit `9bf1d18`) mostró números **estables y esperados**, no bugs:
   `relative_strength_52w` con `gap=141` (25% de los activos) es
   estructural — esos activos tienen un NaN legítimo a mitad de serie por
   desalineamiento de calendario con su benchmark, así que SIEMPRE van a
   caer al camino lento para ese código (correcto, documentado en el
   propio código). Los `dist_optimal_sma_*`/`*_monthly` con lento estable
   (7, 15, 16, 25) son activos sin suficiente historia para esos cálculos
   (best_val inválido o serie mensual vacía) → nunca cachean stats → caen
   al lento por siempre. Ninguno es un problema a resolver.

   **CERRADO con evidencia puntual (commit `b67a3d2`, 9-jul-2026):**
   `backfill_indicator` ahora loguea `slow_asset_ids` por motivo (no solo
   el conteo). Corrida real confirmó DOS causas distintas, ambas ya
   esperadas, ninguna es bug:
   - Activos con historia corta (id 1153 `AZUL`: 27 filas, listado
     2026-05-28; id 740/1249 `RICH.BA`/`RICH.BA_USDARS=X`: 240 filas desde
     2025-07-18) caen lento en todo lo que requiere lookback largo
     (SMA50/200, retorno anual/52w, semanal/mensual) pero son rápidos en
     lookback corto (`return_daily/monthly/quarterly`, `rsi_daily`,
     `dist_sma20`) — se autocorrige con el tiempo, sin acción.
   - Los `dist_optimal_sma_*` con lento estable NO son por falta de
     historia (algunos tickers tienen hasta 8431 filas desde 1993) sino
     por `_find_best_ma` (technical_service.py:40): descarta cualquier
     período de SMA con menos de 5 "toques" (`low <= ma <= high`); varios
     tickers extranjeros ilíquidos (BA=Buenos Aires, SA=São Paulo,
     SN=Santiago, KS=Corea, PA=París, SW=Suiza) nunca tocan ninguna SMA
     candidata → `best_sma_*` queda `None` para siempre → serie NaN
     completa → nunca cachea stats.

   **HECHO (commit `8aff073`, local, sin pushear): el usuario pidió no
   dejarlo solo documentado — arreglar que dejen de ir por el camino
   lento.** `_series_stats` devolviendo `None` (serie sin ningún valor
   válido) nunca se cacheaba, así que estos activos repetían el camino
   lento en TODOS los deltas, para siempre. Ahora `(None, None, 0)` se
   cachea como confirmación válida de "sin datos" (`_confirmed_empty_fast_path`,
   con 4 tests nuevos en test_delta_tail.py); si la corrida siguiente
   confirma que sigue vacío, pasa al camino rápido sin tocar la tabla
   `ind_{code}`. Se evaluó un precheck de filas mínimas por código
   (alternativa del usuario) pero se descartó: varios códigos
   (`rsi_weekly/monthly`, `atr_weekly/monthly`) ya tienen guarda interna
   propia, y `trend_*`/`volatility_*` dependen de `regime_cfg`/`vol_cfg`
   editables por el admin — un precheck estático quedaría desincronizado
   ante cambios de config. El mecanismo de caché autoaprendido reacciona
   solo (`compute_fn` corre siempre, si la config cambia y el activo pasa
   a tener datos válidos, se detecta y reescribe en esa misma corrida).

   Motivo nuevo `"empty"` (separado de `"gap"`) en `path_counts`/
   `slow_asset_ids`: no es un hueco real de calendario, es la naturaleza
   del indicador para ese activo (best_sma_* inválido, sin benchmark,
   etc.) — deliberadamente NO se envía al panel de Centro de Datos (el
   wire format `__pc__:` sigue con 4 campos fast/gap/checksum/bench) para
   no ensuciar el `lento=N` que se ve en pantalla; sí queda en el log de
   texto (`empty=N` + lista de asset_id) para diagnóstico.
   **PRÓXIMO PASO: pushear cuando el usuario confirme, correr un delta
   real en el Codespace y verificar que los ~23 tickers de
   dist_optimal_sma_* dejan de aparecer bajo "lento" desde la segunda
   corrida en adelante.**

   **Hallazgo importante (commit `fd26a42`): bug de scheduling LPT
   preexistente, no relacionado con el caché de hoy.** `last_backfill_seconds`
   ordenaba la cola LPT (pesados primero) tanto para delta como para
   rebuild completo (force=True) — pero son costos MUY distintos para el
   mismo código (delta reescribe 1 fila/activo, rebuild reescribe la
   historia entera). Un rebuild completo real (8m08s, log del usuario)
   mostró `dist_sma20/50/200`, `dist_optimal_sma_daily`, `return_quarterly`
   arrancando en la 2da/3ra tanda de workers (2m+ cada uno) en vez de la
   primera junto a `volatility_daily`/`trend_daily`, porque la cola LPT los
   creía livianos (medición heredada de deltas recientes, donde sí son
   baratos). Fix: migración 0056 agrega `last_rebuild_seconds` separado;
   cada modo (force sí/no) lee y persiste su propio campo.
   **PRÓXIMO PASO: correr `alembic upgrade head` (migración 0056) en el
   Codespace antes del próximo rebuild — sin ella, force=True va a fallar
   al leer/escribir la columna nueva. La primera corrida de rebuild
   post-migración no tiene `last_rebuild_seconds` todavía (cae a la
   heurística `_cost_rank`), recién desde la segunda ordena por costo real
   de rebuild.**

8. **DESCARTADO tras prueba real:** `innodb_flush_log_at_trx_commit=2`
   (probado con `SET GLOBAL`) no cambió el tiempo del delta (59s vs 62.9s
   antes, dentro del ruido) — la sospecha de contención de fsync entre
   workers no era la causa real. Ver punto 9. El Codespace quedó en `1`
   (default); no vale la pena insistir con este parámetro hasta después
   de resolver el punto 9 (si se migra a procesos, ahí sí podría volver a
   importar).

9. **CONFIRMADO con `scripts/profile_pool_concurrency.py` (commit
   `74ec50a`): el cuello de botella real del pool de indicadores es
   contención de GIL, no fsync ni cómputo.** Correr los 6 códigos más
   pesados secuencial vs concurrente (6 threads, mismo cómputo puro, sin
   tocar la BD) dio **0.9x** de speedup — los threads no paralelizan nada,
   incluso empeoran un poco. Contradice la primera hipótesis (que había
   sido descartada erróneamente con `profile_pool_contention.py`, que solo
   medía secuencial y no comparaba contra concurrente real).
   **Palanca pendiente, no arrancada — la más grande que queda para 10000
   activos:** migrar `backfill_all_indicator_values`/
   `backfill_all_fundamental_values` de `ThreadPoolExecutor` a
   `ProcessPoolExecutor` (procesos reales, sin GIL compartido). Requiere
   que cada proceso tenga su propia sesión de BD y no pueda compartir
   `price_cache`/`df_w_cache`/`df_m_cache`/`best_sma_cache` como dict en
   memoria tal cual — hay que serializar o que cada proceso cargue su
   propia porción. Sin diseñar todavía.
   **Brecha sin explicar del todo:** incluso con el factor GIL confirmado,
   `volatility_daily` sola tardaba 53-63s de pared con solo ~2s de cómputo
   puro — el GIL no alcanza a explicar un 30x. Nunca se aisló si el resto
   es el commit a la base, el lock compartido `_lock`/`_tick()` del
   contador de progreso, u otra cosa. Sería el próximo profiling si se
   retoma este tema (una versión de `profile_pool_concurrency.py` que
   además escriba a la BD, para separar cómputo+GIL de I/O real).

10. **HECHO — varios bugs encontrados y arreglados en la misma sesión
    (jul-2026), todos pusheados:**
    - `6b10a9d`: NaN llegaba sin filtrar hasta el INSERT de indicadores
      (`_upsert_ind` solo chequeaba `None`, no `NaN`) — un `close` NULL en
      una fila de precio (activos recién importados, mercados europeos)
      propagaba NaN a través de `_pct_change` y explotaba con
      `MySQLdb.ProgrammingError`. Fix en dos capas: `_upsert_ind` filtra
      NaN también, y `last_close`/`prev_close`/`_closest_price_on_or_before`
      corregidos en el origen.
    - `65bf5a5`: deadlocks de InnoDB (error 1213) al actualizar
      fundamentales en paralelo (4 workers escribiendo cada uno un
      asset_id distinto en `fundamental_quarterly`, pero InnoDB puede
      deadlockear igual por gap locks/FK checks). `_fund_worker` reintenta
      la transacción completa hasta 3 veces ante deadlock/lock timeout
      (1213/1205) — recomendación estándar de InnoDB, no es un bug de
      lógica.
    - `074d1b2`: contador "497/495" en el panel (el loop de
      `backfill_indicator` iteraba `Asset.id` completo pero el denominador
      del progreso usaba solo `price_cache`) + `MySQLdb.ProgrammingError
      (2014, "Commands out of sync")` en sintéticos (objetos ORM
      `SyntheticFormula` cargados en la sesión del hilo principal, tocados
      desde threads del pool — lazy-load de `f.asset` compartía la misma
      conexión DBAPI entre threads). Ambos arreglados.
    - `a0076c5`: barra de progreso de "Fundamentales" volvía a 0% al pasar
      de `recompute_all_ratios` a `backfill_all_fundamental_values` (mismo
      bug ya resuelto para indicadores técnicos con
      `_run_current_and_backfill`, nunca portado a fundamentales) —
      `_run_ratios_and_backfill` combina el progreso de ambas fases y de
      paso comparte `quarters_cache` una sola vez entre las dos (antes se
      cargaba duplicado).

11. **HECHO (commit `b2e3747`): `scripts/clean_data.py` redefinido.**
    Se descubrió que el script original borraba `assets`/`prices`/
    catálogos con `FOREIGN_KEY_CHECKS=0` sin limpiar ~45 tablas
    relacionadas (`fundamental_quarterly`, `current_indicator_values`,
    `synthetic_formula/component`, varias `ind_fundamental_*`, etc.) —
    quedaron huérfanas y causaron errores de FK + lentitud severa en
    corridas posteriores (limpiado manualmente por el usuario vía SQL
    directo, ver detalle abajo). Redefinido: ya NO toca
    `assets`/`prices`/`price_sources`/catálogos ni
    `synthetic_formula`/`synthetic_component`/`currency_conversion_divisor`
    (datos que no se recrean solos — activo cargado a mano como el MERVAL
    de Ámbito, precios de fuente externa, fórmulas de sintéticos, config
    de conversión de moneda). Ahora solo borra datos derivados/
    recomputables (indicadores técnicos y fundamentales — descubiertos
    dinámicamente vía `information_schema` en vez de mantenerlos a mano,
    `current_indicator_values`, logs, señales, resultados de estrategias).

    **Causa raíz de la corrupción de datos**: el usuario corrió
    "Limpieza de datos" (`clean_data.py`, versión vieja) en un Codespace
    más antiguo; eso dejó las ~45 tablas mencionadas con filas apuntando a
    activos ya borrados. Diagnosticado con queries `LEFT JOIN ... WHERE
    a.id IS NULL` tabla por tabla, confirmado con una query a
    `information_schema.KEY_COLUMN_USAGE`/`REFERENTIAL_CONSTRAINTS` para
    listar TODAS las tablas con FK a `assets.id` (49 en total). El usuario
    limpió manualmente los datos huérfanos con DELETE ad-hoc antes de que
    se arreglara el script.

Contexto clave: scheduling LPT auto-calibrado activo, con campos
SEPARADOS para delta (`last_backfill_seconds`) y rebuild
(`last_rebuild_seconds`, migración 0056 — no compartir uno para el otro,
son costos muy distintos); delta no borra nada; force usa TRUNCATE;
commits por volumen (~25k filas); suite de tests con ~200 casos (pytest
en verde en cada commit de esta sesión).

12. **NTM P/E (forward), postergado (11-jul-2026) tras investigar el costo
    real.** `FundamentalQuarterly.eps_estimated` está muerto: en
    `app/sources/fundamental/yahoo.py` se hardcodea a `None` siempre (nunca
    se implementó la lectura real desde Yahoo), y aunque estuviera poblado
    solo cubre trimestres YA reportados (estimado-vs-real, no proyección a
    futuro). Para un NTM P/E real hace falta `ticker.info.get('forwardEps')`
    de yfinance — dato que el código nunca toca hoy para fundamentales.
    Dos motivos por los que se posterga: (1) `ticker.info` es una de las
    llamadas más lentas/pesadas de yfinance, se sumaría a cada actualización
    masiva de fundamentales; (2) no puede tener historia real (a diferencia
    de `pe_ttm`, que se reconstruye para cualquier fecha pasada porque
    `net_income`/`shares` de trimestres viejos son datos fijos) — el
    consenso de analistas a futuro solo se puede guardar como valor
    "vigente" del día de la corrida, como `best_sma_*`, nunca como serie
    histórica. Si se retoma: agregar el fetch en `yahoo.py`, decidir dónde
    persistir `forward_eps` (no encaja en `FundamentalQuarterly`, que es
    tabla de datos trimestrales fijos) y aceptar el costo de la llamada
    extra.

13. **HECHO — la pantalla `/admin/cleanup` estaba desactualizada; alcance
    unificado en un servicio (19-jul-2026).** El punto 11 arregló
    `scripts/clean_data.py` pero NO la pantalla, que mantenía su propia
    lista `_TABLES_INFO` — la vieja, con `assets`/`prices`/catálogos y
    `SET FOREIGN_KEY_CHECKS = 0`: exactamente la combinación que dejó
    huérfanas las 49 tablas con FK a `assets.id`. Además no tocaba nada del
    pipeline (`ind_*`, `sig_*`, `strat_res_*`, `group_scores`,
    `current_indicator_values`, fundamentales) ni lo agregado después
    (backtest, carteras). Y ninguna de las dos entradas limpiaba
    `verification_run_log`, `asset_verification_flag` ni `run_lock`.

    Ahora el alcance vive SOLO en `app/services/cleanup_service.py`, que
    consumen la pantalla y el script. Decisiones de producto tomadas en la
    sesión: política fija (un botón, sin checkboxes) y los snapshots de
    backtest/cartera (`backtest_run`, `portfolio_run` + hijas) SÍ se borran
    aunque no se recalculen. Se preservan activos, precios, fuentes,
    catálogos, definiciones, configuración, sintéticos y —clave— las
    carteras con su registro de operaciones (`portfolio`,
    `portfolio_member`, `portfolio_transaction`), que son datos cargados a
    mano.

    Cambios técnicos: sin `FOREIGN_KEY_CHECKS` (con la lista corregida no
    hace falta, y apagarlo era la causa raíz — MySQL no dispara los
    `ON DELETE CASCADE`); `db_compat.wipe_table` (TRUNCATE) en vez de
    `DELETE FROM` crudo, salvo `backtest_run`/`portfolio_run`, que van con
    DELETE porque MySQL rechaza TRUNCATE sobre una tabla con FKs entrantes
    aunque la hija esté vacía; las hijas se vacían antes que los padres; y
    se filtra por tablas existentes (`screener_snapshot` ya no tiene modelo
    y su DELETE reventaba la corrida en una base nueva).

    Red nueva: `tests/test_cleanup_service.py` (9 casos) fija que no entren
    tablas curadas, que estén todos los logs, que los prefijos dinámicos
    lleven `_` (sin él, `ind_` se lleva `industries`/`indicator_definitions`
    y `sig_` se lleva `signal`), y que ni la página ni el script vuelvan a
    definir su propia lista. Antes no había NINGÚN test sobre esto: por eso
    la divergencia pasó desapercibida.

    **VERIFICAR EN EL CODESPACE:** correr la limpieza desde la pantalla
    contra MariaDB y confirmar (a) que no quedan huérfanos —el chequeo del
    punto 11 sobre `KEY_COLUMN_USAGE` sirve—, (b) que activos, precios y
    carteras siguen intactos, y (c) que después de "Recalcular completo" el
    pipeline reconstruye todo. Probar también con `DB_ENGINE=postgres`: el
    orden hijas→padres y el TRUNCATE/DELETE mixto es lo que cambia entre
    motores.

14. **HECHO — dos arreglos en "Recuperar espacio" de `/admin/cleanup`
    (19-jul-2026).** Salieron de preguntar si el vacuum dejaba sesiones
    abiertas. **No las dejaba**: `maintenance_service` importa solo `engine`
    (nunca `Session`), usa `with engine.connect()` —que cierra incluso ante
    excepción— y `isolation_level="AUTOCOMMIT"`, obligatorio porque PG no
    permite `VACUUM FULL` dentro de una transacción. Por eso
    `admin_cleanup_callbacks` era el único módulo con threads sin
    `Session.remove()` en el `finally`, y estaba bien así (los otros 13 sí lo
    necesitan: `scoped_session` es thread-local y el `teardown_session` de
    Flask corre en el thread del request, no en el daemon).

    Pero aparecieron dos problemas reales:

    (a) **Un fallo midiendo tamaño abortaba todo el vacuum, solo en
    PostgreSQL.** El `try/except ... continue` existe para que una tabla que
    falla no frene a las demás, pero las dos llamadas a `_table_size_bytes`
    quedaban FUERA del try. Caso real: `signal_store` dropea
    `sig_{id}`/`strat_res_{id}` al borrar una señal o estrategia; si eso pasa
    entre `bloat_tables()` y el vacuum de esa tabla, en PG
    `pg_total_relation_size()` sobre tabla inexistente LANZA `undefined_table`
    → se cortaba la corrida y las tablas siguientes quedaban sin compactar. En
    MySQL no pasaba (la consulta a `information_schema` da NULL y el COALESCE
    lo vuelve 0). Arreglado moviendo las mediciones dentro del try.

    (b) **Ni el vacuum ni la limpieza tomaban `run_lock`.** Ahora ambos usan
    `HEAVY_WRITE` vía un helper `_launch_locked` (mismo patrón que
    `price_callbacks._launch_locked_bg`; `heartbeating` libera el lock al
    salir, no hace falta `release` aparte). Importa por dos motivos distintos:
    el VACUUM/OPTIMIZE toma lock exclusivo por tabla —en PG ACCESS EXCLUSIVE,
    que bloquea hasta los SELECT— y dejaría al pipeline esperando; y la
    limpieza con una corrida en curso deja la base a medias, con el agravante
    de que un `signal_eval_log` repoblado parcialmente hace que el delta
    SALTEE fechas recién limpiadas. Antes solo lo advertía un texto en
    pantalla. Si el lock está tomado, el botón no arranca y el alert muestra
    "hay otra operación pesada en curso".

    Nota: `_launch_locked` duplica en espíritu a
    `price_callbacks._launch_locked_bg`. No se unificó para no tocar precios
    en este cambio; si aparece un tercer caso, conviene subirlo a un helper
    compartido.

    **VERIFICAR EN EL CODESPACE:** que el botón "Recuperar espacio" rechace
    con el aviso de ocupado si hay una corrida del Centro de Datos, y que
    tras un vacuum normal el reporte de espacio siga mostrando los MB
    liberados. El caso (a) solo se reproduce en PostgreSQL.
