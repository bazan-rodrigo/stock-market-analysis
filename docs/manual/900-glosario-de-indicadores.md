---
slug: glosario-de-indicadores
title: Glosario de indicadores
chapter: Apéndices
order: 900
roles: invitado
---

Material de consulta: qué mide cada indicador que calcula el sistema y cómo se
lee. El listado vivo, con el tipo y la escala de cada uno, está en
[Indicadores del sistema](/manual/configuracion-indicadores).

Casi todos vienen en tres versiones —**diaria**, **semanal** y **mensual**—, que
miden lo mismo sobre barras de distinta duración. La diaria reacciona rápido y
tiene más ruido; la mensual es estructural y se mueve poco.

---

## Tendencia

### Régimen de tendencia

**Es categórico, no numérico**: devuelve una etiqueta. Se calcula comparando el
precio contra la media móvil que mejor se ajusta a ese activo.

Los valores posibles son diez, no cinco:

| Familia | Valores |
|---|---|
| Alcista | `bullish_strong`, `bullish`, `bullish_nascent_strong`, `bullish_nascent` |
| Lateral | `lateral`, `lateral_nascent` |
| Bajista | `bearish_nascent`, `bearish_nascent_strong`, `bearish`, `bearish_strong` |

Los valores **`nascent`** ("naciente") marcan un régimen que recién se está
formando: la tendencia dio vuelta hace poco y todavía no se consolidó.

> Al armar una señal de mapa discreto sobre este indicador, **asigná puntaje a
> las diez categorías**. Las que dejes afuera hacen que la señal no puntúe ese
> día. Ver [Referencia de fórmulas de señales](/manual/formulas-de-senales).

Se configura en [Régimen de Tendencia](/manual/regimen-de-tendencia).

### Distancia a la media móvil

Qué tan lejos está el precio de su media, en porcentaje. Hay versiones para las
medias de 20, 50 y 200 ruedas.

Positivo = el precio está por encima de la media. Es una medida de *extensión*:
un valor muy alto dice que el activo se alejó mucho de su media, no que sea
buena o mala compra.

### Distancia a la media óptima (en desvíos)

La misma idea, pero contra la media que mejor describe a ese activo en
particular, y medida en **desvíos estándar** en vez de porcentaje.

Es la versión comparable entre activos: un 5% significa cosas distintas en un
activo tranquilo y en uno volátil, pero "dos desvíos" significa lo mismo en los
dos. **Si vas a comparar activos entre sí, usá esta.**

### Mejor media móvil

Qué período de media móvil describe mejor la tendencia de ese activo, calculado
por separado para simple y exponencial, y para cada frecuencia.

> **Este indicador mira toda la historia disponible para decidir cuál es la
> mejor.** Eso lo hace útil para describir un activo hoy, pero problemático en
> un backtest: al evaluar una fecha del pasado estarías usando información que
> en ese momento no existía. Tenelo presente antes de construir una señal sobre
> él.

---

## Momento

### RSI

Índice de fuerza relativa, de 0 a 100. Compara la magnitud de las subidas
recientes contra la de las bajadas.

La lectura clásica es: por encima de 70, sobrecomprado; por debajo de 30,
sobrevendido. En la práctica, un activo en tendencia fuerte puede quedarse
semanas por encima de 70 sin corregir, así que conviene comprobar contra la
historia del propio activo antes de fijar umbrales — para eso está la solapa
**Posicionamiento Histórico** de
[Análisis de Activo](/manual/analisis-de-activo).

---

## Volatilidad

### Régimen de volatilidad

**Categórico.** Combina dos cosas: qué tan alta es la volatilidad y hace cuánto
que está así.

| Componente | Valores |
|---|---|
| Nivel | `baja`, `normal`, `alta`, `extrema` |
| Duración | `corta`, `media`, `larga` |

Se combinan en etiquetas como `alta_larga` (volatilidad alta sostenida) o
`extrema_corta` (un pico reciente). La distinción importa: un pico puntual y un
régimen alto sostenido son situaciones distintas aunque el nivel coincida.

Se configura en [Volatilidad ATR](/manual/volatilidad-atr).

### Percentil de ATR

Dónde cae la volatilidad actual dentro de la historia del propio activo, de 0 a
100. Un valor de 90 significa que solo el 10% de los días de su historia fueron
más volátiles.

Es directamente comparable entre activos, porque cada uno se mide contra sí
mismo.

---

## Drawdown

### Drawdown actual

Cuánto cayó el precio desde su máximo previo, en porcentaje. Siempre negativo o
cero. Cero significa que el activo está en su máximo.

### Drawdowns máximos

Las tres caídas más profundas registradas en la historia del activo. Sirven de
referencia para dimensionar la caída actual: un −15% es poco en un activo cuyo
peor drawdown fue −70%, y mucho en uno que nunca cayó más de −20%.

Se configura en [Drawdowns](/manual/drawdowns).

---

## Retornos

Variación porcentual del precio en distintas ventanas: **diaria**, **mensual**,
**trimestral**, **anual** y **52 semanas**.

### Fuerza relativa a 52 semanas

El retorno del activo comparado con el de su referencia en el mismo período. Es
la medida de si le está ganando o perdiendo al mercado, que es una pregunta
distinta a si subió o bajó.

Un activo puede tener retorno negativo y buena fuerza relativa: cayó, pero menos
que todo lo demás.

---

## Soportes y resistencias

Distancia porcentual al soporte y a la resistencia más cercanos, detectados por
pivotes. Se configuran en
[Soporte / Resistencia](/manual/soporte-resistencia).

---

## Fundamentales

Solo tienen valor para activos con datos fundamentales cargados: las acciones
sí, los índices y la mayoría de los sintéticos no.

| Indicador | Qué mide |
|---|---|
| **P/E TTM** | Precio sobre ganancias de los últimos doce meses. |
| **P/B** | Precio sobre valor libro. |
| **P/S TTM** | Precio sobre ventas de los últimos doce meses. |
| **Margen neto / bruto / operativo** | Qué porcentaje de las ventas queda como ganancia en cada nivel. |
| **Deuda / Patrimonio** | Cuánto se apalanca la empresa. |
| **Crecimiento de ingresos, de ganancia por acción, de ganancia neta (interanual)** | Variación contra el mismo período del año anterior. |
| **Variación del P/E (interanual)** | Si la empresa se abarató o encareció en términos de múltiplo. |

> **Los fundamentales se actualizan por trimestre, no todos los días.** El valor
> de hoy suele ser el del último balance publicado. Un cambio brusco no
> significa que la empresa cambió hoy: significa que se publicó un balance
> nuevo. Ver
> [Actualización de fundamentales](/manual/actualizacion-de-fundamentales).
