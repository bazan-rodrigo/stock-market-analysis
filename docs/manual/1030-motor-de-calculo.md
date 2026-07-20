---
slug: motor-de-calculo
title: El motor de calculo: indicadores, senales y estrategias
chapter: Anexo tecnico
order: 1030
roles: admin
---

El motor es un pipeline de cuatro etapas y **todas persisten su salida: nada se
calcula on-the-fly**. Esa decisión condiciona el resto del diseño, y la razón es
simple: un ranking transversal sobre miles de activos no se puede armar por
request. Se escribe una vez y las pantallas solo leen.

El manual de usuario cuenta el mismo encadenamiento desde la pantalla en
[Cómo se calcula todo](/manual/conceptos-pipeline). Acá va el lado de adentro:
qué lee y qué escribe cada etapa, qué se midió y qué se resignó.

```
 prices          →  ind_daily / ind_weekly / ind_monthly
 (+ fundamental)    ind_fundamental_*  +  current_indicator_values
                              │
                              ├──→ group_scores      (5 dimensiones)
                              │         │
                              ↓         ↓
                        sig_{id}   group_signal_value
                              └────┬────┘
                                   ↓
                            strat_res_{id}
                          (score + pct, cross-section)
```

## 1. Indicadores: por activo, independientes

`app/services/technical_service.py` mantiene dos registros: `_BACKFILL_FNS`, con
los 24 códigos técnicos que guardan historia, y `_CURRENT_ONLY_CODES`, con los 12 que solo
tienen valor vigente (`best_sma_*`, `best_ema_*`, `drawdown_*`, `resistance_pct`,
`support_pct`). Entran precios, salen las tablas anchas por cadencia (`ind_daily`
con 14 columnas, `ind_weekly` y `ind_monthly` con 5, `ind_fundamental_daily` con
4, `ind_fundamental_quarterly` con 8), más `current_indicator_values` y el caché
`ind_asset_meta`.

Son independientes entre sí y la unidad de trabajo del pool es **un lote de
activos × todos los códigos**. La única dependencia entre códigos salió cara:
`dist_optimal_sma_*` necesita `best_sma_*`, que es solo-vigente, así que la fase
de vigentes debe correr antes del backfill. `rebuild_indicator_history` tuvo el
orden invertido y usaba el valor de la corrida anterior; hoy
`tests/test_indicator_pipeline_order.py` mockea ambas fases y verifica
únicamente el orden.

## 2. group_scores: solo los grupos que alguien consume

`compute_group_scores`, en `app/services/group_score_service.py`, lee las tres
tablas de tendencia con fecha **exacta** y agrega por cinco dimensiones: sector,
market, industry, country e instrument_type. Traduce el régimen categórico a
número con un mapa fijo de 10 entradas (`bullish_strong` = 100 hasta
`bearish_strong` = −100) y promedia. La agregación en sí, `aggregate_group_scores`,
es lógica pura sin base, a propósito: la comparten el camino por-fecha y el modo
rango.

En modo rango solo se escriben los grupos que alguna estrategia consume, vía
`_derive_needed_groups`. El motivo fue un bug reportado: se escribía la agregación
de unos 200 grupos por fecha aunque el usuario tuviera **cero** señales de grupo
que la leyeran, y la tabla se llenaba de millones de filas muertas que enlentecían
las sentencias del tramo denso. La derivación, en `restricted_attribute_ids`
(`app/services/strategy_filter.py`), es deliberadamente conservadora: ante
cualquier ambigüedad devuelve `None`, o sea calculá todos. Acotar de más solo
cuesta CPU; acotar de menos daría scores faltantes silenciosos. Además mira
**todas** las estrategias, no las del alcance de la corrida — si no, recalcular la
de Argentina borraría los grupos que necesita la de Brasil sobre la misma señal.

> Si no hay ninguna señal `source=group`, la historia de `group_scores` queda casi
> vacía y **eso es correcto**. Solo se escribe la última fecha completa, porque el
> mapa de mercado la lee.

## 3. Señales: un motor puro y una optimización medida

`app/services/signal_engine.py` importa `json` y `logging`, y nada más. Tres
fórmulas: `evaluate_discrete_map` (string a score vía dict), `evaluate_threshold`
(primer límite que el valor supera, con el par `[null, score]` como default) y
`evaluate_range` (mapeo lineal de `[min, max]` a `[-100, 100]`). Los scores viven
en ese rango, con una excepción deliberada: `range` con `clamp=False` puede
pasarse de ±100.

El campo `source` distingue dos orígenes: las señales de activo leen las `ind_*`,
las de grupo leen `group_scores` y solo aceptan tres `indicator_key`
(`regime_score_d/w/m`). Una señal de grupo mal configurada se descarta una sola
vez en `_prepare_signals`, con un único warning, en lugar de al evaluar: en un
backfill de 25.000 fechas, un warning por (grupo × fecha) inundaría el log.
`validate_params` existe por una razón parecida.

> Un `params` sintácticamente válido pero con la forma equivocada — un `map` en
> una señal `threshold` — **no rompe nada**. `evaluate` devuelve `None` en
> silencio y la señal no puntúa nunca. Solo protege a quien la llama:
> `save_signal` e `import_signals_excel`. Una fila escrita directo en la base
> queda muda para siempre.

La optimización interesante es `compile_evaluator`. El perfilado con
`scripts/profile_signal_pipeline.py` (cómputo puro, sin base, 500 activos × 250
fechas) mostró que **~75% del costo era despacho**: decidir el `formula_type` y
re-extraer con `params.get()` los mismos parámetros, 750.000 veces, 5,6 millones
de `dict.get`. La solución fue compilar cada señal a una closure con los
parámetros ya horneados, una vez por corrida, dejando en el loop caliente solo la
matemática. Medido: señales de 6,69 a 3,58 ms por fecha (1,9x), pipeline completo
de 8,92 a 5,71 ms (1,6x), un "Recalcular completo" de 2500 fechas de ~22 a ~14
segundos de CPU, y la proyección a 10.000 activos de ~7,5 a ~4,8 minutos.

Una optimización así solo sirve si es exactamente equivalente, y eso lo defiende
`tests/test_signal_engine_compile.py`: cuatro tests de propiedad con Hypothesis
que exigen igualdad **exacta** de floats, incluyendo `None` y la semántica de
`max`/`min` ante NaN — cualquier divergencia sería un bug de datos silencioso en
toda la historia. Además degrada con gracia: ante params ausentes, con forma
inesperada o un `formula_type` desconocido devuelve un wrapper de `evaluate()`,
misma conducta sin la aceleración.

La fórmula `composite` (promedio ponderado de otras señales) **se removió** de
punta a punta, con migración `0068_drop_composite_signals.py`, por redundante:
combinar señales ya se hace en la estrategia con componentes ponderados. La
migración borra las huérfanas y falla a propósito si alguna está referenciada por
un componente. La prueba de que sobraba: `alineacion_timeframes` se reprodujo
exacta poniendo `tendencia_d/w/m` como tres componentes de peso 2/3.

## 4. Estrategias: filtro, score ponderado y ranking transversal

Dos piezas separadas. El filtro de elegibilidad (`app/services/strategy_filter.py`)
es un árbol AND/OR que corre **antes** del scoring: el activo que no cumple no
aparece con puntaje bajo, no aparece. Dato faltante es condición no cumplida y
tipos incompatibles dan falso — dejar pasar lo que no se pudo evaluar sería una
trampa silenciosa. `evaluate_tree` es la implementación de referencia, recursiva y
por activo; producción usa `evaluate_tree_bulk`, que recorre el árbol una vez por
**nodo** en vez de una por activo, con corto circuito equivalente (AND estrecha
sobre los que vienen pasando, OR solo sobre los que aún no pasaron).

La segunda pieza es `_compute_asset_score` en `app/services/strategy_service.py`:
suma ponderada de componentes, con tres scopes (señal de activo directo,
`own_group` según el `group_type` del componente, y `specific_group` con un grupo
fijo), y de ahí a `percent_ranks` y al orden descendente, hacia `strat_res_{id}`.

> El score se **renormaliza** sobre los componentes que puntuaron: uno cuya señal
> no tiene valor se saltea y su peso no entra al denominador. Un activo con 1 de 5
> señales disponibles queda con el score de esa única señal, indistinguible de uno
> con las 5. `tests/test_composites_y_estrategias.py` lo fija: pesos 1 y 9, solo
> puntúa la de peso 1 con score 80 → el resultado es 80. Si ningún componente
> puntúa, el activo se descarta y no ocupa fila.

`percent_ranks` replica la semántica de `PERCENT_RANK()` de SQL —
(rank−1)/(n−1)×100, con `RANK()` para empates, y n=1 → 0.0. Se persiste en la
columna `pct` (migración 0071) porque derivarlo al leer costaba 60s+ con historia
densa: la serie de un activo necesita la cross-section completa de cada fecha,
mientras que al escribir ya está en memoria.

Y acá está el punto del que se deriva medio sistema: **el ranking es
cross-sectional**. El percentil de un activo en una fecha no existe sin los demás
activos de esa fecha. De ahí sale la asimetría de los deltas — indicadores y
precios tienen delta por-activo (un activo nuevo se llena solo), pero señales y
estrategias tienen delta por-fecha global, así que incorporar un activo nuevo a la
historia exige "Recalcular completo".
`signals_and_strategies_affected_by_new_assets` materializa eso: lista qué queda
desactualizado al agregar activos, y de ahí sale el aviso del
[Centro de Datos](/manual/centro-de-datos). Ver
[Deltas, recalculos y borrado masivo](/manual/deltas-y-borrado-masivo).

## La lectura as-of y su efecto colateral

Los indicadores se leen con `query_values_asof` (`app/models/indicator_store.py`):
última fila `<= target_date` por activo, con tope `ASOF_MAX_LOOKBACK_DAYS = 45`.
Los semanales y mensuales se guardan con fechas de fin de período — el resample
etiqueta las semanas en domingo — así que el match exacto los dejaba en cero
scores casi cualquier día: fue un bug real de `tendencia_w/m` y `volatilidad_w/m`.
El tope de 45 días evita el extremo opuesto, levantar valores zombie de activos
que dejaron de cotizar, y cubre etiquetas mensuales más feriados largos.

> El as-of arrastra. Un activo que **no** cotizó el día D igual recibe score en D
> con su último valor, si otro activo (una cripto el fin de semana, un índice, un
> sintético) hizo de D una fecha computable. Y esos scores no se refrescan cuando
> llega el dato real, porque el delta solo reprocesa huecos más la última fecha.

Peor: `group_scores` usa fecha exacta y las señales por-activo usan as-of, así que
**dos capas del mismo pipeline son hoy incoherentes entre sí**. Está reconocido y
sin resolver (`docs/notes/design_scores_dias_sin_precio.md` guarda dos
alternativas evaluadas). El backtest lo tapa al leer, no al escribir:
`app/services/backtest_service.py` solo admite un score si el activo tiene precio
propio en esa fecha exacta, lo que permitió cerrar el MVP sin decidir la semántica
del pipeline.

Dos omisiones más, del mismo orden. Las señales sobre indicadores sin historia
solo puntúan en la fecha vigente; para fechas pasadas se omiten con un log, porque
usar el valor vigente sería sesgo de anticipación silencioso. Y una condición del
filtro puede pedir `resolution='current'`, que lee `CurrentIndicatorValue` para
cualquier fecha: eso **sí** es sesgo de anticipación, aceptado a propósito para
diagnóstico in-sample de indicadores full-sample tipo `best_sma`.
`uses_current_resolution` lo detecta y la UI lo marca con un badge, pero la fila
en `strat_res_{id}` no lleva ninguna marca.

## El modo rango: segundo camino, misma matemática

El pipeline por-fecha está diseñado para **una** fecha, el uso diario del
scheduler. Llamarlo 25.000 veces repite queries que son constantes (definiciones,
grupos de activos) o incrementales (el as-of). Por eso existe
`app/services/signal_backfill_range.py`, que se activa con 30 fechas o más a
computar (`_RANGE_MODE_MIN_DATES`). Hace un barrido cronológico por chunks de 250
fechas: cada tabla `ind_*` se carga una vez por chunk, en una ventana que arranca
45 días antes del inicio — justamente para que el as-of de los primeros días sea
correcto — y un puntero por código (`_Sweep`) avanza fecha a fecha. **El as-of
pasa a salir de memoria en O(1) amortizado**, con la misma semántica que
`query_values_asof`.

Lo importante es lo que **no** se duplica. El módulo invoca las mismas funciones
puras del camino por-fecha: `_evaluate_asset_signal_scores`,
`_evaluate_group_signal_scores`, `aggregate_group_scores`, `rank_strategy_assets`
y `percent_ranks`. Lo único propio es la orquestación de I/O, y esa es la
condición para que la paridad sea estructural en vez de una coincidencia.
`tests/test_signal_range_parity.py` corre ambos caminos sobre el mismo dataset y
exige igualdad exacta de las cuatro tablas de salida; usa 40 fechas a propósito,
para superar el umbral de 30 y ejercitar el rango de verdad.

Hay dos divergencias deliberadas, que no son regresiones: el DELETE por fecha
elimina filas obsoletas que el upsert por-fecha dejaría zombies, y el alcance de
grupos ya mencionado. Existe además el modo `strategy_only`, que el usuario elige
cuando no cambiaron ni señales ni indicadores: los scores de señal se **leen** de
`sig_{id}` y `group_signal_value` en vez de re-evaluarse, los barridos de
indicadores se reducen a lo que el filtro necesita, y solo se reconstruye
`strat_res_{id}` — el costo pasa a ser proporcional a la estrategia y no a la
historia de sus señales. La concurrencia del módulo (tres lectores paralelos, un
escritor asíncrono con cola de backpressure) se trata en
[Concurrencia: hilos, procesos y exclusion mutua](/manual/concurrencia-y-multihilo).

## Qué lo sostiene, y qué no

De la suite, 109 tests tocan directamente este motor — 35 del filtro, 23 de
`signal_engine`, 18 de la derivación de grupos, 11 del scoring, 6 de paridad de
rango, 5 de `percent_ranks`, 4 de compilación, 4 de activos nuevos y 3 del ciclo
de vida de las tablas dinámicas. Con un hueco conocido: el docstring de
`evaluate_tree_bulk` afirma que su paridad con `evaluate_tree` está cubierta por
tests, y **no la hay**. `tests/test_strategy_filter.py` importa solo
`evaluate_tree` y ningún test menciona `evaluate_tree_bulk`; la cobertura es
indirecta, porque los tests de paridad de rango usan `bulk` en ambos caminos. Más
en [Estado actual, limites conocidos y deuda tecnica](/manual/estado-y-limites-conocidos).
