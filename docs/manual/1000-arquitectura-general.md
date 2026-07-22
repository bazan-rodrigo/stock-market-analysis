---
slug: arquitectura-general
title: Arquitectura en una pagina
chapter: Anexo tecnico
order: 1000
roles: admin
---

Este anexo está escrito para alguien que se incorpora al proyecto y necesita
entender cómo está resuelto el sistema por dentro. El resto del manual describe
pantallas; acá se describen decisiones, con sus razones, sus mediciones y lo que
se resignó al tomarlas.

Si tenés que quedarte con una sola idea, que sea esta: **todo el pipeline
analítico se pre-calcula y se persiste, y pintar una pantalla es un SELECT
indexado, nunca un cálculo**. Casi todo lo demás —las tablas dinámicas, la
asimetría entre deltas, el diseño de concurrencia— se deriva de ahí.

## Los procesos que corren

En producción hay dos tipos de proceso, definidos en `Procfile`:

```text
web:    gunicorn wsgi:application --bind 0.0.0.0:$PORT --workers 1 --timeout 1800
worker: python worker.py
```

El `--workers 1` no es una economía: **refuerza el modelo de proceso único que
asume todo el diseño de concurrencia**.

El `--timeout 1800` es alto a propósito. Las corridas que se lanzan desde el
Centro de Datos no viven en el pedido web: siguen en segundo plano dentro del
mismo proceso mientras la pantalla muestra la barra de progreso. Ese trabajo es
de cálculo puro y por ratos no le deja lugar a nada más en el proceso; si
gunicorn no recibe señales de vida durante el tiempo de espera configurado, da
por colgado al proceso y **lo mata sin aviso** — la corrida desaparece sin dejar
error, a mitad de camino. Con el valor viejo de 120 segundos eso pasaba al
recalcular indicadores sobre universos grandes. Bajarlo tampoco protege de
mucho: con un solo proceso, matarlo es apagar la aplicación entera.

El segundo proceso existe por una razón puntual. Si APScheduler arrancara dentro
de cada web worker, el job diario se dispararía N veces; el lock persistido lo
deduplicaría, pero serían N schedulers y N misfires. `worker.py` no sirve HTTP:
fuerza `RUN_SCHEDULER=1`, llama a `create_app()` y bloquea el hilo principal con
`threading.Event().wait()`. El orden importa y está comentado en el código — el
override del entorno va **antes** de importar `create_app`, porque la clase
`Config` de `app/config.py` lee `os.environ` al importarse.

Los tres entry points llaman a la misma `create_app()` de `app/__init__.py`:
`wsgi.py` (expone `application`, lo usan gunicorn y mod_wsgi), `run.py` (servidor
de desarrollo en el 8050) y `worker.py`. Lo único que cambia entre entornos son
las variables de entorno, nunca el código.

## Las capas y quién llama a quién

```text
app/pages/       layout puro                    46 modulos
     |
     v
app/callbacks/   wiring: eventos -> servicios   46 modulos
     |
     v
app/services/    logica de negocio + BD         47 servicios
     |
     v
app/models/      ORM y tablas dinamicas         41 modulos
```

Las flechas van solo hacia abajo, y eso es verificable: **ningún módulo de
`app/services/` ni de `app/models/` importa `app.pages` o `app.callbacks`, y
ningún servicio importa `dash`**. Esa es la propiedad que hace testeables los
servicios sin levantar la UI.

El reparto de responsabilidades se ve en los imports: solo 6 de las 46 páginas
importan algo de `app/services/`, mientras que 40 de los 46 módulos de callbacks
lo hacen. Las páginas son layout; los callbacks traen los datos.

> La direccionalidad es una **convención sostenida, no una barrera**: no hay
> ninguna regla escrita que la imponga, y de hecho 7 módulos de callbacks
> importan de `app/pages/` para reusar helpers de layout y constantes definidos
> en las páginas. Está derivada de los imports reales, no de un documento.

Hay dos bordes deliberados. `app/services/visibility.py` importa
`flask_login.current_user`, pero adentro de una función, para que la lógica pura
(`can_view`, `can_edit`, `can_reference`) quede testeable sin contexto Flask. Y
`app/models/signal_store.py` importa `quote_ident` de `db_compat`, también dentro
de una función, porque `signal` es palabra reservada en MariaDB.

## El recorrido de un dato

```text
Yahoo Finance / Ambito / Calculado     (app/sources/registry.py)
  |
  v
prices
  |
  v
indicadores         por activo, independientes entre si
  |                 ind_daily / weekly / monthly
  |                 + current_indicator_values
  v
group_scores        agregado por sector, mercado,
  |                 industria, pais y tipo
  v
senales             sig_{id} y group_signal_value
  |
  v
ranking             strat_res_{id} (score, pct)
  |
  v
pantalla            SELECT indexado
```

La fuente de precios es un registry extensible (`app/sources/registry.py`) de
clases que implementan la ABC `PriceSourceBase`, con `validate_ticker` y
`download_history`. Hay tres registradas: `YahooFinanceSource`, `AmbitoSource`
(riesgo país argentino, un solo ticker) y `CalculatedSource` (sintéticos, no
descarga nada), más un registry análogo para fundamentales.

> `CLAUDE.md` y las notas del proyecto siguen diciendo "solo Yahoo Finance,
> arquitectura extensible". El código muestra que la extensibilidad **ya se
> ejerció dos veces**. Es drift documental: ante la duda, gana el código.

La orquestación real está en `price_service.update_all_active_assets()`, que
descarga precios con un `ThreadPoolExecutor` de 6 workers y después encadena
`technical_service.update_indicator_history()`,
`fundamental_service.update_all_fundamentals()` y `_refresh_group_scores()`.

> El nombre engaña: cada worker de descarga corre con `skip_indicators=True`. Los
> indicadores **no** se calculan activo por activo dentro del worker, sino en una
> sola pasada después de que están todos los precios. Es deliberado: así se reusa
> el delta con sus compuertas de checksum y detección de huecos ya validadas.

Dentro del tramo de indicadores el orden está blindado: primero los vigentes,
después el backfill histórico, porque `dist_optimal_sma_*` lee `best_sma_*` desde
`current_indicator_values`. Estuvo invertido y fue un bug real; hoy
`tests/test_indicator_pipeline_order.py` mockea ambas fases y verifica solo el
orden de las llamadas.

El segundo tramo corre por fecha, en `signal_service`, y tampoco es negociable
porque cada paso consume lo que el anterior persistió:
`group_score_service.run_daily(d)` → `compute_signal_values(d)` →
`compute_group_signal_values(d)` → `compute_strategy_results(...)`. La fecha
objetivo nunca es `date.today()` sino `get_default_target_date()` —la última
fecha con precios—, porque con `today()` el pipeline se quedaría sin datos los
fines de semana y feriados.

El ranking cierra el circuito y es **cross-sectional**: `rank_strategy_assets`
filtra elegibilidad con `evaluate_tree_bulk`, calcula el score ponderado y ordena
sobre todos los activos de esa fecha. Esa es la razón estructural de la asimetría
de los deltas — precios e indicadores tienen delta por activo, señales y
estrategias por fecha global.

## Por qué se pre-calcula todo

La decisión está datada y motivada por un número: con 200 a 1000 activos, el
cálculo on-the-fly implicaba **~200.000 filas por carga de pantalla**. El
objetivo declarado es 10.000 activos contra los ~500 de prueba de hoy, un factor
20x. A esa escala, calcular al pintar no es una opción.

El principio se aplica hasta el final. El percentil del ranking se persiste en la
columna `pct` en vez de derivarse al leer: derivarlo exige la cross-section
completa de cada fecha para dibujar la serie de un solo activo, y medido costaba
62 s en la ventana `PERCENT_RANK` del overlay del gráfico. En el pipeline, en
cambio, la cross-section ya está en memoria. Por la misma lógica los resultados
no viven en dos tablas grandes: cada señal tiene su `sig_{id}` y cada estrategia
su `strat_res_{id}`, porque recalcular una unidad es TRUNCATE + insertar en
vacío, contra borrar-e-insertar dentro de una tabla poblada, **medido 3-5× más
caro** y con contención entre unidades.

Lo que se resigna es evidente: **los cambios de definición no se ven hasta que
corrés un recálculo**, y el almacenamiento crece. La versión para el usuario de
este mismo pipeline está en
[Cómo se calcula todo](/manual/conceptos-pipeline).

Las excepciones son tres y están acotadas a propósito:

- **El gráfico técnico.** Python devuelve solo `raw_daily` al cambiar de activo;
  todos los indicadores (medias, Bollinger, RSI, MACD, estocástico, ATR,
  drawdown, punto y figura) se calculan en JavaScript en el navegador, en el
  namespace `window._lwc` de `app/callbacks/chart_callbacks.py`. Es
  interactividad sobre un activo, no análisis transversal: mover el período de
  una media no justifica un round-trip.
- **El simulador de trades.** Su semántica vive duplicada a propósito entre
  `app/services/trade_simulator.py` (el contrato, Python puro y sin BD) y su
  espejo JS. La duplicación se sostiene con una regla de proceso y un contrato
  ejecutable en `tests/fixtures/trade_simulator_cases.json`.
- **El backtest.** Calcula al vuelo leyendo `strat_res_{id}`, pero persiste cada
  corrida como snapshot inmutable: la historia de rankings se reescribe con cada
  recálculo completo, así que un run nunca se recalcula, se corre uno nuevo y se
  comparan.

## Dónde mirar según qué quieras entender

- Qué pieza hace qué y qué restricción impone cada una:
  [Stack tecnológico](/manual/stack-tecnologico).
- Dónde vive cada dato, y por qué no existen tablas `signal_value` ni
  `strategy_result`: [Modelo de datos](/manual/modelo-de-datos).
- Cómo se calculan indicadores, señales y rankings:
  [El motor de cálculo](/manual/motor-de-calculo).
- Por qué un DELETE masivo se hace por ventanas:
  [Deltas y borrado masivo](/manual/deltas-y-borrado-masivo).
- Hilos, GIL y el pool de indicadores:
  [Concurrencia](/manual/concurrencia-y-multihilo).
- Cómo se sostiene MySQL y PostgreSQL sin ramas sueltas:
  [Soporte dual](/manual/soporte-dual-de-base-de-datos).
- La regla de homologación Python↔JS:
  [El simulador de trades](/manual/simulador-de-trades).
- Registro manual de pantallas, auth y permisos:
  [La capa web](/manual/capa-web-y-registro).
- Entornos, variables y tareas programadas:
  [Despliegue y configuración](/manual/despliegue-y-configuracion).
- Qué cubre la suite y cómo se mide performance:
  [Pruebas y medición](/manual/pruebas-y-medicion).
- Lo pendiente y lo que se sabe que no escala:
  [Estado y límites conocidos](/manual/estado-y-limites-conocidos).
