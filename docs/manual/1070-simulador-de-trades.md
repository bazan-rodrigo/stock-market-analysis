---
slug: simulador-de-trades
title: El simulador de trades y su espejo en JavaScript
chapter: Anexo tecnico
order: 1070
roles: admin
---

En todo el repositorio hay un solo lugar donde una regla de negocio vive
duplicada **a propósito**, en dos lenguajes. Es el simulador de trades: la misma
máquina de estados está escrita en `app/services/trade_simulator.py` (Python
puro, sin base de datos) y replicada en JavaScript como
`window._lwc.simulateTrades`, un string embebido en
`app/callbacks/chart_callbacks.py`. Si vas a tocar alguno, leé esto antes:
romper la homologación no rompe ningún test.

## Por qué se duplicó y qué se resignó

El panel de estrategia del gráfico tiene 27 controles. El usuario mueve un
checkbox y los trades se redibujan al instante, porque el callback que rearma la
spec y re-renderiza es un `clientside_callback`: corre en el navegador. **Un
callback de servidor habría metido un viaje al servidor por cada tecleo**, y la
exploración interactiva de parámetros —el uso real de esa pantalla— dejaría de
ser fluida.

Lo que se resignó es concreto: **el lado JavaScript no tiene ni un solo test**.
No hay `package.json` ni runner de JS en el repo, y ningún test de pytest
ejecuta ni parsea `simulateTrades`. La paridad se sostiene por disciplina, y por
eso la regla está escrita en `CLAUDE.md`, en el docstring del contrato Python y
—en espejo— en un comentario del propio JS: el que edita el JS no va a leer el
docstring de Python. En la práctica se cumplió: de los 8 commits que tocaron
`trade_simulator.py`, los 8 tocaron también `chart_callbacks.py` y 6 tocaron
además el fixture (los otros dos cambiaban métricas, no la máquina de estados).

## El contrato ejecutable

`tests/fixtures/trade_simulator_cases.json` es el único archivo de
`tests/fixtures/` (15.225 bytes) y tiene **35 casos**. Cada uno es
`{name, closes, scores, percentiles, spec, expected}`, con `expected` reducido a
`(entry_idx, exit_idx, reason)`: solo índices y motivo, ni precios ni retornos.
Esos los verifica `tests/test_trade_simulator.py` como invariantes derivadas, así
el contrato queda mínimo. El test parametriza los casos —el `name` es el id de
pytest— y colecta 40 tests. El JSON lleva la advertencia de proceso adentro, en
el `_comment`: es el artefacto que alguien va a editar primero.

## La asimetría AND/OR

Las **entradas son filtros**: deben cumplirse todas las activas. Las **salidas
son gatillos**: cierra la primera que dispare. La asimetría es deliberada —
entrar es "cumplo todos los requisitos", salir es "se rompió alguna cosa". Con
un operador único, agregar una salida volvería el sistema más conservador o más
laxo según cuál fuera, que es lo contrario de lo intuitivo.

> Sin condiciones de entrada la simulación devuelve **cero** trades, no "siempre
> comprado": `_entry_ok` retorna `False` con la lista vacía. Sin condiciones de
> salida, en cambio, sí es buy & hold del filtro.

Los tipos están fijados en constantes del módulo y validados al entrar: 2
entradas (`score`, `pct`), 6 salidas por score (`absolute`, `absolute_above`,
`delta_entry`, `trailing_score`, `score_ma`, `percentile`) y 4 caps
(`max_bars`, `stop_loss`, `trailing_stop`, `take_profit`). Un tipo desconocido
levanta `ValueError` en vez de no disparar nunca en silencio. Ojo con el nombre
`caps`: engloba precio **y** tiempo, no es "límite superior".

## La precedencia dentro de una posición abierta

Por barra se evalúan tres niveles, en orden fijo:

```
  1. filtro       barra sin score -> cierre forzado, reason "filter"
  2. caps         salidas por PRECIO/TIEMPO, orden de la lista
  3. score_exits  salidas por SENAL, orden de la lista
```

Primero manda la elegibilidad: si el activo dejó de calificar, cualquier otra
razón de salida es discutible. Y un stop de precio es un hecho consumado
—el precio ya pasó el nivel— mientras que una salida por señal es una opinión.

> El `reason` depende del **orden de las listas**, no solo de las condiciones:
> caps y score_exits son OR y gana la primera. Reordenar los controles de la UI
> cambiaría el desglose de salidas por motivo sin cambiar un solo parámetro.

Tres detalles del contrato, del tipo que diverge en silencio: en la barra de
entrada no se evalúa ninguna salida (el loop hace `continue`); los máximos de
trailing se actualizan **incluyendo la barra actual**; y la media móvil de
`score_ma` se acumula sobre toda la serie observada, haya o no posición, porque
es una propiedad de la serie y no del trade.

> La cola sin score **no** cierra por filtro: el bucle termina en `last_scored`
> porque más allá no hay veredicto de elegibilidad, y cerrar ahí sería un
> artefacto del pipeline. Pero el retorno del trade abierto se mide contra
> `closes[-1]`, que puede estar después. Una regla decide el cierre, la otra la
> valuación.

> `rearm` puede bloquear la re-entrada **para siempre**: si tras la salida la
> condición de entrada nunca vuelve a fallar en una barra con score, no hay
> segunda entrada nunca más. Lo fija el caso
> `rearm_bloquea_sin_cruce_para_siempre` — es deseado, no un bug.

## El tercer espejo: armar la spec

Hay un espejo más, del armado de la spec desde los controles:
`window._lwc.buildSpec` (JS) y `trade_optimizer.spec_from_controls` (Python). El
optimizador corre server-side pero tiene que producir la misma spec que el
gráfico, o su top-10 no sería aplicable al panel. Su contrato es el **orden
posicional de 27 controles**, y son 27 en los tres lados: `_SIM_CONTROL_IDS`, la
firma de `buildSpec` y la tupla que desempaqueta `spec_from_controls`. Un
desfasaje de un solo control corre todos los siguientes y produce una spec
plausible pero equivocada —el stop loss leído como take profit— sin ningún error
visible. `tests/test_trade_optimizer.py` (16 tests) fija ese orden; el JS sigue
sin cubrir.

## Quién más consume el motor

El motor Python es el que usa el [backtest](/manual/backtest): el nivel de
Reglas hace fan-out de `simulate_trades`/`summarize_trades` sobre todo el
universo (`app/services/rules_backtest_service.py`), y el de Cartera lo corre por
activo para derivar la elegibilidad que alimenta la simulación, walk-forward
incluido (`app/services/portfolio_backtest_service.py`). El principio del
rediseño es explícito: **no tocar el contrato homologado**. Los costos en bps se
aplican en el agregador, no en el motor — meterlos adentro obligaría a
replicarlos en JS y a re-fixturear los casos.

## Deuda técnica conocida

- **No hay test de paridad JS↔Python**, aunque el patrón existe en el repo:
  `test_paridad_grafico.py` y sus pares reimplementan el JS de los indicadores
  como funciones `_ref_*` en Python. Al simulador nunca se le aplicó. La única
  verificación fue manual: en una corrida real los trades del optimizador
  cuadraron con los del gráfico, 122 + 15 = 137.
- **Divergencia real entre los espejos:** Python valida los tipos y lanza
  `ValueError`; el JS no valida nada y un tipo desconocido no dispara. En el
  navegador la spec siempre la construye `buildSpec`, así que la validación
  sería código muerto — pero es una asimetría a tener presente.
- **Hay cinco lugares que arman una spec, no dos.** Además de `buildSpec` y
  `spec_from_controls`, `app/callbacks/rules_backtest_callbacks.py` y
  `app/callbacks/portfolio_backtest_callbacks.py` tienen cada uno un
  `_build_spec` idéntico byte a byte al otro salvo el docstring. Son versiones
  reducidas —solo `absolute` como salida por score, activación por presencia de
  valor en vez de checkbox— y por eso no reusaron `spec_from_controls`.
- **La semántica también está en prosa** en el popover de ayuda de
  `app/pages/asset_analysis.py`, que el propio código marca como no-autoritativo:
  "la semántica real vive en `trade_simulator.py`".
