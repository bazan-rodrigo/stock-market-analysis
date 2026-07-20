---
slug: analisis-de-activo
title: Análisis de Activo
chapter: 3. Análisis
order: 310
roles: invitado
page: /activo
---

Es la pantalla principal del sistema y donde se pasa la mayor parte del tiempo:
todo lo que sabe la aplicación sobre **un** activo, en cuatro solapas.

Arriba de todo, el selector de activo y tres controles que definen **cómo se ve
el gráfico** (no son indicadores):

- **D / W / M** — frecuencia de las barras: diaria, semanal o mensual.
- **Velas / Línea / P&F / P&F X-O** — tipo de gráfico. Las dos últimas son
  Punto y Figura: la primera respeta el eje de tiempo, la clásica no.
- **Arit / Log** — escala del eje de precios. En escala logarítmica un mismo
  porcentaje ocupa la misma distancia visual en cualquier nivel de precio, que
  es lo que querés cuando mirás varios años de historia.

---

## Solapa «Gráfico Técnico»

El gráfico de precios con todo lo que se le puede superponer. Cada indicador se
prende con su botón; al prenderlo aparecen sus parámetros al lado, y al apagarlo
se ocultan.

### Superpuestos al precio

| Control | Qué dibuja |
|---|---|
| **SMA 1/2/3** | Medias móviles simples. La etiqueta muestra la distancia % del precio a la media. |
| **EMA 1/2/3** | Medias móviles exponenciales — como la SMA pero con más peso a lo reciente. |
| **Bollinger** | Media de N ruedas ± D desvíos estándar. Mide qué tan lejos está el precio de su media en términos de volatilidad. |
| **Drawdowns** | Marca los pisos de las caídas detectadas, con la profundidad % de cada una. |
| **Soporte / Resistencia** | Niveles por pivotes, con la cantidad de toques de cada uno y la distancia % al más cercano. |
| **Régimen** | Colorea la EMA de referencia según el régimen de tendencia detectado (alcista / lateral / bajista y matices). |
| **Volatilidad** | Sombrea el fondo según el régimen de volatilidad ATR (extrema / alta / normal / baja). |
| **Eventos** | Marca los eventos de mercado cargados en el sistema (crisis, elecciones, anuncios). |

### En paneles propios, debajo del precio

**Volumen**, **RSI** (0-100; clásicamente >70 sobrecompra, <30 sobreventa),
**MACD** (EMA rápida − EMA lenta, con línea de señal e histograma),
**Estocástico** (posición del cierre dentro del rango de las últimas N ruedas),
**ATR** (volatilidad absoluta promedio, en precio) y **Drawdown** (caída %
desde el máximo histórico previo).

---

## Simulación de estrategias

Es la parte más densa de la pantalla y merece leerse con calma. Al activarla y
elegir una estrategia, se agrega un panel con el **score de esa estrategia** a
lo largo del tiempo y se **simulan trades** sobre la historia visible según las
condiciones que configures.

Todas las condiciones se manejan igual: una tilde para activarla y un valor al
lado. Están agrupadas en tres bloques, y **la regla de combinación es distinta
en cada uno**:

### Entrada — se exigen TODAS las activas (Y)

- **Score ≥** — el score de la estrategia supera el umbral.
- **Percentil ≥** — el activo está sobre ese percentil del ranking del día
  (100 = el mejor). Combinada con la anterior: "score alto **Y** entre los
  mejores del día".

### Re-entrada — frenos que se exigen ADEMÁS de lo anterior

- **Cruce** — tras una salida, la condición de entrada debe *dejar de
  cumplirse* antes de poder volver a entrar. Evita re-entrar al día siguiente
  de haber salido.
- **Enfriamiento** — tras una salida, espera N ruedas antes de permitir otra
  entrada.

### Salida por score — dispara la PRIMERA que se cumpla (O)

| Condición | Qué hace |
|---|---|
| **Abs <** | El score cae bajo un nivel fijo. Tiene sentido si tus señales cruzan el 0. |
| **Abs >** | El score *supera* un nivel — take profit del score, lógica contrarian. Conviene validarla con el backtest antes de usarla. |
| **Ent−Δ** | El score cae Δ puntos por debajo del que tenía al entrar (stop loss del score). |
| **Máx−Δ** | El score cae Δ puntos desde el máximo alcanzado en el trade (trailing stop del score). |
| **Media k** | El score cae bajo su media móvil de k ruedas: el impulso se dio vuelta. |
| **Percentil <** | El activo cae bajo ese percentil del ranking. Clásico de rotación: entra con Percentil ≥ 90, sale con Percentil < 70. |

### Salida por precio / tiempo — dispara la PRIMERA que se cumpla (O)

**Ruedas** (duración máxima), **SL%** (stop loss desde la entrada), **TS%**
(trailing stop desde el máximo del precio) y **TP%** (take profit). A
diferencia de las anteriores, estas miran el **precio real** del trade: cubren
el caso "el score sigue alto pero el precio se está cayendo".

### Siempre activo

Si el activo **deja de ser elegible** para la estrategia (no pasa el filtro), el
trade se cierra y se marca con «S filtro». Si no activás ninguna condición de
salida, el trade se mantiene mientras el activo siga siendo elegible — un buy &
hold del filtro.

> **Precedencia cuando varias salidas caen en la misma barra:**
> filtro → precio/tiempo → score.

### ¿Cuál conviene usar?

- **Para medir la señal en sí**: solo **Score ≥** y **Ruedas**. Eso da el
  retorno posterior puro, que es lo mismo que mide el backtest.
- **Para simular operatoria real**: **Percentil ≥** en la entrada con
  **Percentil <** en la salida, o **Máx−Δ**, más **SL%** como red de seguridad.
- **Para aislar el efecto de una condición**: activá una sola y compará
  corridas cambiando un parámetro por vez.

---

## Solapa «Fundamentales»

Los datos de balance y los ratios derivados del activo. Solo tiene contenido
para activos que los tengan cargados: las acciones sí, los índices y la mayoría
de los sintéticos no.

## Solapa «Panel de Indicadores»

El valor **vigente** de todos los indicadores calculados para el activo, en una
tabla. Es la vista rápida para responder "¿cómo está hoy?" sin leer el gráfico.

## Solapa «Posicionamiento Histórico»

Responde una pregunta distinta a la del gráfico: **¿el valor de hoy es alto o
bajo comparado con su propia historia?**

Elegís un indicador y la pantalla dibuja el histograma de todos sus valores
históricos, marcando dónde cae el valor actual. El **ancho de bin** controla
qué tan fina es la agrupación. Un RSI de 65 puede ser altísimo para un activo y
perfectamente normal para otro; esta solapa es la que lo dice.
