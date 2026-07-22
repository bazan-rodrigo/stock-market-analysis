---
slug: estado-y-limites-conocidos
title: Estado actual, limites conocidos y deuda tecnica
chapter: Anexo tecnico
order: 1099
roles: admin
---

Este es el mapa de dónde está parado el sistema hoy: qué escala, qué no, qué
quedó a medio camino y qué se descartó a propósito. Es la sección más útil si
te estás incorporando, y también la que envejece más rápido.

Antes de nada, una advertencia de método. **Cuando `docs/notes/` y el código se
contradicen, gana el código.** No es hipotético: la nota del ProcessPool lo
lista como pendiente y está implementado; los "diferidos" de fundamentales y
verificación están hechos; `design_ind_wide_tables.md` da los fundamentales
anchos como "pendiente opcional" y ya existen las migraciones 0081 y 0082; un
bug de `_set_bulk_load_checks` figura como "NO arreglado" y ya no existe.
`CLAUDE.md` dice ~400 tests y hoy son más del doble. Verificá antes de repetir.

## La escala: 500 activos contra un objetivo de 10.000

El universo de prueba son ~500-561 activos y el objetivo declarado es 10.000.
Lo primero que se rompe no es el cómputo sino el **I/O y la memoria del proceso
padre**.

El techo medido es el GIL: paralelizar el **cómputo puro** con threads da apenas
**0,9x** —no acelera, incluso empeora un poco—. Y la reacción intuitiva de sumar
workers también falló midiéndola: llevar `_POOL_WORKERS` de `cores+2` a `cores+6`
empeoró el delta de **3m08s a 3m42s** por contención de disco, no por falta de
paralelismo. El arreglo fue lo contrario, *menos* paralelismo —precalcular
`tail_stats` en una sola sesión antes de lanzar el pool—, y dejó el delta en
**2m11s**, el mejor número de referencia del pipeline diario. La medición
completa está en [Concurrencia](/manual/concurrencia-y-multihilo) y el caché que
lo sostiene, en [Deltas y borrado masivo](/manual/deltas-y-borrado-masivo).

## El ProcessPool está implementado, pero dormido

`app/services/process_pool.py` (con `make_executor` y `spawn_executable_ok`) y
`process_child.py` en la raíz del repo son el harness de procesos, y
`run_asset_batches` en `technical_service.py` es el orquestador compartido que
ya usan indicadores, fase de vigentes, `fundamental_service` y
`verification_service`.

> El pool de procesos **nunca se activa hoy**: `_use_process_pool` exige
> `IND_POOL_MIN_ASSETS = 1500` activos y el universo real es ~560. Todo el
> camino de procesos es código testeado que en producción no se ejercita.

El umbral es deliberado: por debajo, el overhead de spawn más imports supera al
beneficio. `_use_process_pool` además degrada a threads —sin fallar— con
dialecto sqlite (la suite) y cuando `sys.executable` no parece un intérprete de
Python, el caso de Apache con mod_wsgi embebido, donde spawn lanzaría `httpd`
como intérprete y el pool nacería roto. Se usa spawn y no fork porque el padre
está lleno de threads: fork heredaría locks tomados por otros hilos y los
sockets vivos del pool de conexiones. El executor es efímero, uno por corrida,
para que un reciclado de mod_wsgi no deje procesos huérfanos escribiendo.

Consecuencia práctica: el techo de memoria del padre está resuelto **solo en
modo procesos**. `_run_current_and_backfill` ya no carga la tabla de precios
entera cuando corre con procesos, pero en modo threads —la escala de hoy—
sigue cargándola.

## Tablas anchas y motor de base de datos

El refactor a tablas anchas está completo para los 24 indicadores técnicos con
historia y es el default (`use_wide_ind_tables`). La motivación se midió: las
tablas por código gastaban **~94-102 bytes por fila para un payload útil de
~16 bytes**, o sea ~80% estructura y no dato. Las migraciones 0077 (crear),
0078 (poblar) y 0079 (dropear las per-código) cierran el ciclo, y la 0079 es
punto de no retorno. Los fundamentales siguieron el mismo camino con 0081 y
0082. Se descartó acortar la retención de historia: el refactor ancho es
lossless, y esa era la condición. Lo que queda por confirmar en producción es
si el DROP de la 0079 ya se aplicó en Railway —`alembic current` lo dice—:
desde la PC de desarrollo no hay acceso a esa base, así que no lo des por hecho.

El soporte dual MySQL/PostgreSQL tiene las fases 1 a 4 hechas y PostgreSQL ya
es el motor de producción. **La fase 5 —paridad de resultados entre motores con
`scripts/compare_engines.py`— tiene la herramienta lista pero la nota la da
como no ejecutada**, así que la paridad formal quedó atrás del deploy real. Lo
que sí se validó es la equivalencia cadena↔modelos. Las migraciones 0001 a 0075
quedan congeladas como solo-MySQL (`FROZEN_HEAD` en
`tests/test_bootstrap_portability.py`); de la 0076 en adelante la cadena es
única y portable, y hoy hay 85 migraciones.

## El backtest y lo que quedó afuera

Los cuatro niveles están implementados: A Señal (deciles e IC), B Reglas, C
Cartera (`portfolio_sim_engine`) y D Comparar, más el walk-forward de
optimización en `portfolio_backtest_service`. El walk-forward elige la config
por **Sharpe** del train, no por retorno crudo, y compara train contra test
anualizado: sin anualizar no son comparables, porque el train es expansivo y el
test un solo tramo. Fue un fix de revisión, no del diseño original.

Falta una cosa concreta: **no se puede borrar una corrida guardada desde la
UI**. Los runs son inmutables, se acumulan, y la única forma de sacarlos es la
limpieza global, que vacía la base operativa entera.

## Decisiones abiertas

La más importante es **los scores en días sin precio propio**. El pipeline
computa toda fecha en que algún activo tenga precio, y los indicadores se leen
as-of con tope de 45 días, así que un activo que no cotizó igual recibe un
score arrastrado. Peor: ese score no se refresca cuando llega el dato real,
porque el delta de señales es por-fecha global. Hay una incoherencia interna
declarada — `group_scores` ya usa fecha exacta, `signal_value` arrastra.

Hay dos alternativas guardadas en `docs/notes/design_scores_dias_sin_precio.md`
y ninguna elegida:

| | A — Gate | B — Flag preliminar |
|---|---|---|
| Score ficticio | no existe | existe, marcado y refrescado |
| Coherencia con `group_scores` | sí | no |
| Modelo de datos | marcador `min_dirty_date` | columna + JOIN con ventana |
| Semántica | cambia (menos filas) | igual (solo etiqueta) |

La recomendación tentativa es A, pero el usuario no quedó convencido. El
detalle crítico de A: el marcador debe contar dato **genuinamente nuevo**, no
fecha reescrita — el delta siempre reescribe la última fecha, y contar eso haría
que un activo parado se re-dispare en cada corrida.

Mientras tanto el backtest se desbloqueó sin decidir, con un **gate de lectura**
en `backtest_service.py`: un score entra al análisis solo si el activo tiene
precio propio en esa fecha exacta. Es la semántica de A aplicada al leer; si
algún día A se implementa en el pipeline, el filtro queda redundante sin
cambiar resultados.

El lead de performance abierto más claro está en `_panels_for_range`, que no
tiene caché y se llama una vez por combinación de ventana y trailing: con los
defaults del walk-forward son **12 reconstrucciones de paneles** en el train.
Es del tipo "eliminar trabajo", pero también el más invasivo, y corre bajo
demanda, así que para el objetivo de 10.000 activos pesa menos que el pipeline
diario.

## Descartado a propósito

Esta es la parte que casi nunca se escribe y la que más tiempo ahorra.

| Se descartó | Por qué |
|---|---|
| Staging tables (0072-0074) | El merge por anti-joins costaba proporcional al tamaño de los datos, no al cambio: **33min+**, peor que el rebuild completo. Reemplazado por el modo `strategy_only`. |
| Fórmula `composite` de señales | Redundante: combinar señales se hace en la estrategia con componentes ponderados. Removida de punta a punta, con migración 0068. |
| Método "regla dinámica" de carteras | Redundante con "derivada de estrategia", que ya es una cartera filtrada. La 0085 dropea `rule_json`, que nunca se escribió ni se leyó. |
| `_series_checksum` por bytes crudos | Sobre datos reales: 1,19-1,40x en numéricas pero **0,52-0,56x en texto**. Ahorro total 0,7-2,3% de un lote. Revertido. |
| Vectorizar fechas en `_bf_relative_strength_52w` | **2x más lento** (1,58 → 3,33 ms) y las conversiones eran el 7% de la función. `date.toordinal()` ya es un método C barato. Revertido. |
| 8 lectores en el backfill de señales | Sobre-paralelización: 5m10s → 6m50s. Fijado en 3. |
| Popup blanco del DatePicker | Fallaron CSS por clase, wildcard, JS por ID y MutationObserver. react-dates inyecta CSS con `!important` después del propio. **Decisión explícita de dejarlo así.** |
| Lenguaje de fórmulas libre para indicadores de usuario | Riesgo de performance a 10.000 activos. El alcance acordado son plantillas parametrizadas; el seam (`_resolve_backfill_fn`) ya existe. |

Las dos reversiones por medición dejaron la regla más citada del proyecto:
**cProfile infla 3,7x-4,2x en este código**, así que su tabla sirve para saber
dónde mirar, nunca cuánto tarda. Decidir por conteo de llamadas del profiler ya
costó dos vueltas atrás.

## Trampas operativas

> **Editar una tabla `ind_*` a mano desde la consola SQL desincroniza el caché
> de `IndAssetMeta`** (checksum, benchmark_id, min/max/row_count) y el delta va
> a seguir confiando en él. Después de cualquier edición manual hay que forzar
> un rebuild de ese indicador.

> **El `--timeout 1800` de gunicorn es un parche con fecha de vencimiento.**
> Las corridas del Centro de Datos viven adentro del proceso web y la fase de
> indicadores es cálculo puro que no le da señales de vida al árbitro: si tarda
> más que el tiempo de espera, el proceso muere sin aviso y la corrida
> desaparece a mitad de camino. Medido: 113 segundos con 499 activos. Como el
> costo crece con el universo, cerca de los **8.000 activos** el tope vuelve a
> quedar corto, bastante antes del objetivo declarado de 10.000. El arreglo de
> fondo es sacar las corridas al proceso `worker`, y está pendiente.

> **Modificar una definición de señal o estrategia no recalcula lo ya
> guardado**: el delta solo toca la última fecha. Es especialmente engañoso al
> hacer backtest, porque el run se persiste como snapshot inmutable sobre
> historia mezclada —fechas viejas con la definición vieja— y queda comparable
> con otros runs como si fuera válido. Ver
> [Centro de Datos](/manual/centro-de-datos).

También hay que tener presente que el delta de señales es por-fecha **global**,
no por-activo: un activo nuevo no se incorpora a la historia con un delta,
hace falta un recálculo completo, porque el ranking es transversal
([Cómo se calcula todo](/manual/conceptos-pipeline)).

## Los límites de la red de seguridad

No hay CI: el único control automatizado es correr pytest a mano antes de cada
push, sobre un stub sqlite que nunca toca la base real. Y esa suite **no valida
portabilidad de SQL crudo**: ya pasó que un `DELETE FROM "tabla"` con comillas
dobles —válido en PostgreSQL y sqlite, rechazado por MariaDB— atravesara la
suite entera sin que nadie lo notara. Lo que protege contra eso es
`tests/test_bootstrap_portability.py` y `tests/test_db_compat.py`, no la suite
general.

---

**Esta sección hay que mantenerla al día.** Es la primera que se desactualiza y
la que más daño hace cuando miente, porque alguien que llega la va a leer como
si fuera el estado real. Si tocás algo que figura acá, actualizalo en el mismo
commit. El detalle vivo, sesión por sesión, está en `CLAUDE.md` y en
`docs/notes/`, con su índice en `docs/notes/MEMORY.md` — teniendo en cuenta que
ese índice también envejece, y hoy es de lo más atrasado del repo.
