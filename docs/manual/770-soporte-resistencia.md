---
slug: soporte-resistencia
title: Soporte / Resistencia — configuración
chapter: 7. Configuración
order: 770
roles: admin
page: /admin/sr-config
---

Acá se define **cómo detecta el sistema los niveles de soporte y resistencia**
que ves dibujados en el gráfico de [Análisis de Activo](/manual/analisis-de-activo)
y que alimentan los indicadores de distancia a soporte y a resistencia.

Es una configuración **global y única**: no hay parámetros por activo ni por
grupo. Lo que guardes acá cambia los niveles de todos los activos a la vez.

## Cómo se construye un nivel

El proceso tiene tres pasos, y cada parámetro de la pantalla actúa sobre uno.

**1. Se recortan las ruedas a analizar.** Se toman las últimas N ruedas
disponibles del activo (**Lookback**). Son ruedas efectivamente cotizadas, no
días de calendario: 252 ruedas es aproximadamente un año de operatoria.

**2. Se buscan los extremos locales (pivotes).** Una rueda es un pivote de
resistencia si su **máximo** es el más alto de todo su entorno, contando
**Ventana** barras a cada lado. El pivote de soporte es lo mismo con el
**mínimo** más bajo. Con ventana 5, el máximo de esa rueda tiene que ser el más
alto entre las 5 anteriores, ella misma y las 5 posteriores: 11 barras en total.

**3. Se agrupan los pivotes cercanos en zonas.** Dos pivotes separados por hasta
**Agrupamiento %** de distancia —el valor exacto incluido— se fusionan en un solo
nivel, cuyo precio es el promedio de los pivotes que lo componen. Las zonas que no llegan a **Mín.
toques** se descartan y no se dibujan.

## Los parámetros

| Campo | Rango | Qué controla |
|---|---|---|
| **Lookback (días)** | 50 a 1000 | Cuántas ruedas hacia atrás se analizan. Más historia trae niveles antiguos, que pueden ser relevantes o pura arqueología. |
| **Ventana (barras)** | 2 a 30 | Cuán exigente es la definición de extremo local. Más alto = menos pivotes, pero más significativos. |
| **Agrupamiento (%)** | 0.1 a 5.0 | Ancho de la tolerancia con la que dos pivotes se consideran "el mismo nivel". Bajo = zonas precisas y numerosas; alto = zonas anchas y pocas. |
| **Mín. toques** | 1 a 10 | Cuántos pivotes tiene que juntar una zona para mostrarse. |

---

## Qué significa realmente "toques"

Este es el punto que más se malinterpreta. **El número de toques no es la
cantidad de veces que el precio pasó por el nivel**: es la cantidad de *pivotes
detectados* que quedaron agrupados en esa zona. Un precio que atraviesa el nivel
de largo, sin hacer un máximo o mínimo local ahí, no suma ningún toque.

De eso se desprenden dos consecuencias prácticas:

- **Con Mín. toques en 2 o más, un extremo único desaparece por completo.** El
  máximo histórico del activo, si el precio estuvo ahí una sola vez, no genera
  ninguna línea. Suele ser justo el nivel que un analista dibujaría a mano. Si
  querés verlo, tenés que bajar el mínimo a 1, y aceptar a cambio mucho más ruido.
- **Una meseta suma toques sola.** Si dos ruedas consecutivas comparten
  exactamente el mismo máximo, y ambas son el techo de su entorno, cuentan como
  dos pivotes distintos. Una zona puede llegar a 2 toques por un único evento de
  precio en dos barras.

En el gráfico, cada línea se etiqueta con su tipo y su cantidad de toques —
`R3` es una resistencia de tres toques, `S2` un soporte de dos — y las zonas de
**3 toques o más se dibujan con línea más gruesa**, para que la jerarquía se lea
de un vistazo.

---

## La sutileza del agrupamiento: se ancla, no se encadena

El agrupamiento no funciona como una cadena. Cada zona se abre con el pivote más
bajo y **todos los demás se comparan contra ese primero**, no contra el último
que entró. Con **Agrupamiento** en 0.5 %:

- Pivotes en 100 y 100.40 → misma zona (están a 0.4 %).
- Se agrega uno en 100.80 → **abre una zona nueva**, aunque esté a solo 0.4 % de
  100.40, porque contra el ancla de 100 la distancia es 0.8 %.

Esto es deliberado y evita que una sucesión de niveles apenas separados termine
formando una zona enorme por arrastre. Pero explica un resultado que sorprende:
dos niveles visualmente pegados pueden aparecer como líneas separadas, y subir un
poquito el agrupamiento a veces fusiona muchas más zonas de las esperadas.

---

## Otras conductas que conviene conocer

**Los bordes nunca son pivotes.** Las primeras y las últimas **Ventana** barras
del período analizado no pueden calificar, porque no tienen entorno completo de
los dos lados. Con ventana 5, **un máximo recién hecho tarda 5 ruedas en
aparecer como resistencia**. Es el costo de la confirmación: el nivel se dibuja
cuando ya se sabe que fue un techo, no mientras se está formando.

**Resistencia y soporte se clasifican por tipo de pivote, no por su posición
respecto del precio.** Una resistencia formada hace meses puede haber quedado
por debajo del precio actual: se sigue dibujando en rojo, como nivel quebrado.
Sin embargo, **la distancia porcentual solo mira hacia el lado correcto**: toma
la resistencia más cercana *por encima* del último cierre y el soporte más
cercano *por debajo*. Si el activo está en máximos y no hay ninguna resistencia
arriba, esa distancia queda vacía — no es un error.

**Los niveles siempre salen de las ruedas diarias**, aunque estés mirando el
gráfico en frecuencia semanal o mensual.

**Activos con poca historia no muestran nada.** Hace falta un mínimo de ruedas
en relación con la ventana elegida (con ventana 5, al menos 12 ruedas). Por
debajo de eso no se dibuja ningún nivel y las distancias quedan vacías.

---

## Guardar: qué se actualiza y qué no

> **Guardar los parámetros no recalcula nada por sí solo.** El gráfico de
> Análisis de Activo calcula los niveles en el momento, así que refleja los
> valores nuevos apenas lo abrís. En cambio, los indicadores de distancia a
> soporte y a resistencia que consumen el screener y las señales quedan con los
> parámetros viejos hasta el **próximo recálculo de indicadores**: el que
> disparás a mano desde **Actualización de Precios**, o el que corre solo cada
> vez que se actualizan los precios de un activo. Hasta entonces vas a ver el
> gráfico y el screener en desacuerdo — el propio mensaje de guardado te lo
> recuerda.

> **El lookback muy largo no se traslada entero al indicador.** El valor vigente
> que usan screener y señales se calcula sobre una ventana acotada a
> aproximadamente el último año de ruedas. Subir el **Lookback** muy por encima
> de eso agrega niveles al gráfico, pero no necesariamente cambia el indicador.

Además, estos dos indicadores **no guardan serie histórica**: solo existe su
valor vigente. Por eso no aparecen en las pantallas que trabajan sobre la
historia de un indicador, como la solapa de posicionamiento histórico. Repasá la
diferencia entre valor vigente y serie en
[Cómo se calcula todo](/manual/conceptos-pipeline).

---

## Cómo calibrarlo

Movés **un parámetro por vez** y mirás el resultado en un activo que conozcas bien.

- **Demasiadas líneas, gráfico ilegible** → subí **Ventana** (exige extremos más
  marcados) o subí **Mín. toques**.
- **Casi ninguna línea** → bajá **Mín. toques** a 1, o subí **Agrupamiento**
  para que pivotes dispersos se junten y alcancen el mínimo.
- **Zonas que deberían ser una sola aparecen partidas** → subí **Agrupamiento**,
  recordando el efecto de ancla explicado más arriba.
- **Para operatoria de corto plazo** conviene menos lookback y ventana chica;
  **para niveles estructurales**, más lookback, ventana grande y 3 toques mínimos.
