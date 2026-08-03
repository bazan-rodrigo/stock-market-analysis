---
slug: catalogo-de-senales
title: El catálogo de señales — con qué criterio puntúa cada una
chapter: 7. Configuración
order: 725
---

Esta sección explica **por qué cada señal puntúa como puntúa**. No es la
referencia de las fórmulas —eso está en
[Referencia de fórmulas](/manual/formulas-de-senales)— ni el instructivo de la
pantalla, que está en [Señales](/manual/configuracion-senales). Es el criterio
de análisis: lo que hay que entender antes de armar una estrategia, para no
pedirle a una señal lo contrario de lo que mide.

## Las dos reglas del catálogo

**Una sola señal por indicador.** No hay dos versiones del RSI con umbrales
distintos. Si las hubiera, comparar dos estrategias dejaría de significar algo:
no sabrías si difieren en la idea o en cómo mide cada una.

**Todas apuntan para el mismo lado: +100 son las mejores condiciones para
comprar** —esperando estar largo mientras el precio sube— y −100 las peores.
Sin esa regla, sumar señales con pesos no querría decir nada.

De las dos sale una consecuencia que conviene tener a mano: para usar una señal
**al revés** no hace falta pedir una nueva. El peso de un componente de
estrategia admite **signo negativo**, y con eso el activo puntúa alto donde la
señal puntúa bajo. Una estrategia bajista, o una que quiera *"momentum alto pero
volatilidad baja"*, se arma así — ver
[Estrategias](/manual/configuracion-estrategias).

## Régimen y entrada: la división que explica casi todo

Dos familias miran lo mismo (dónde está el precio respecto de su media) y
puntúan al revés a propósito, porque contestan preguntas distintas:

- **Las medias fijas de 20, 50 y 200 ruedas miden salud.** Por encima de la
  media puntúa mejor. Es el régimen: la pregunta es *¿este activo está bien?*
- **La distancia a la media óptima —medida en desvíos— mide estiramiento.** El
  retroceso hacia la media puntúa mejor. Es la entrada: la pregunta es *¿este es
  buen momento para comprarlo?*

El RSI juega en el segundo equipo: puntúa la **sobreventa**, no la fuerza. Es
la señal donde más gente espera lo contrario, así que vale repetirlo — si tu
estrategia es de momentum puro, el RSI va con peso negativo.

## Qué premia cada familia

| Familia | Puntúa +100 cuando… | Por qué |
|---|---|---|
| Tendencia (diaria, semanal, mensual) | el régimen es alcista fuerte | Lectura directa. |
| Volatilidad, ATR % y compresión | el activo está en calma | La calma es mejor telón de fondo para estar largo. Dentro de cada nivel, la duración modula: una calma instalada suma, una turbulencia instalada resta. |
| Fuerza de tendencia (ADX) | la tendencia empuja fuerte | **No dice dirección**: un derrumbe ordenado también da ADX alto. Nunca se usa sola. |
| RSI y distancia en desvíos | el precio retrocedió | Miden el punto de entrada. |
| Distancia a las medias de 20 / 50 / 200 | el precio está por encima | Miden la salud de la tendencia. |
| Retornos (día, mes, trimestre, año, 52 semanas) | el activo viene subiendo | Momentum, sin excepciones dentro de la familia. |
| Caída desde el máximo y posición en el rango anual | el precio está cerca de máximos | Fortaleza, no ganga. |
| Peores caídas históricas | las caídas fueron poco profundas | Miden fragilidad. |
| Volumen relativo | opera más que lo habitual | El volumen confirma el movimiento. |
| Soporte y resistencia | el soporte está cerca y la resistencia lejos | El riesgo se acota contra el piso y el recorrido libre está arriba. |
| Múltiplos: P/E, P/B, P/S y cambio del P/E | el activo está barato | Con una salvedad importante, abajo. |
| Márgenes, crecimiento y ROIC | los números son mejores | Calidad y crecimiento se leen de frente. |

## Tres cosas que sorprenden y son deliberadas

**Perder plata no es estar barato.** En los múltiplos, una empresa con pérdidas
o con patrimonio negativo cae en el **peor** tramo, no en el mejor. Si se
puntuara el número crudo, la empresa que más pierde sería la mejor rankeada del
sistema.

**Una señal puede premiar el retroceso y castigar el derrumbe a la vez.** La
distancia a la media óptima da su mejor puntaje en el retroceso sano y vuelve a
puntuar mal cuando el precio se aleja demasiado hacia abajo, porque eso ya no es
un retroceso sino una ruptura. Es la única señal del catálogo que no crece ni
decrece de forma pareja, y tiene una consecuencia: **usarla con peso negativo no
da momentum**, premia los dos extremos a la vez.

**Los retornos del mes, del trimestre y del año se reinician.** Miden desde el
1º del período calendario, así que a principio de mes casi no distinguen entre
activos. Si tu estrategia se apoya en ellos, tenelo en cuenta al leer el ranking
los primeros días.

## La trampa de la cobertura

Una señal sin valor **no castiga al activo**: el promedio de la estrategia se
calcula solo con los componentes que puntuaron y los pesos se reparten entre
ellos. El resultado es contraintuitivo — **al activo al que le falta el dato le
va sistemáticamente mejor** que a uno que sí lo tiene y puntúa mal.

En este catálogo eso toca dos grupos:

- El **volumen relativo**: los activos sintéticos y las conversiones de moneda
  no tienen volumen propio, porque un cociente entre dos precios no lo tiene.
- Los **doce indicadores fundamentales**: solo puntúan en activos que tengan
  fundamentales cargados.

Si tu estrategia usa alguno de ésos, pedí el dato **también en el filtro de
elegibilidad**: ahí el faltante sí deja al activo afuera, que es lo que querés.

## Las señales sin historia

Seis señales salen de indicadores que solo guardan el valor de hoy: la caída
actual desde el máximo, las tres peores caídas históricas y las distancias al
soporte y a la resistencia. Sirven para rankear hoy, pero **no para
backtestear**: no hay historia que reconstruir. Cada una lo aclara en su
descripción.

## De dónde salen los umbrales

Los cortes de cada señal —dónde empieza a puntuar +100, dónde −100— son
**puntos de partida de manual**: valores razonables de la literatura, no
percentiles medidos sobre los activos de esta instalación. Sirven para arrancar
y para comparar estrategias entre sí, pero no son óptimos ni recomendación de
inversión.

Ajustarlos con datos es un trabajo aparte: hay que mirar cómo se reparte cada
indicador entre los activos y correr un [backtest](/manual/backtest) antes de
tomar el cambio por bueno. Y cuidado con una cosa: **cambiar los parámetros de
una señal no recalcula lo ya guardado**. La historia sigue con la definición
anterior hasta que corras un recálculo completo desde el
[Centro de Datos](/manual/centro-de-datos), y hasta entonces un backtest estaría
midiendo la versión vieja.
