---
slug: analisis-de-pares
title: Análisis de Pares
chapter: 3. Análisis
order: 350
roles: invitado
page: /par
---

Mientras [Evolución Relativa](/manual/evolucion) compara muchos activos a la
vez, esta pantalla se concentra en **dos** y los mira con lupa desde tres
ángulos distintos. Es la herramienta para preguntas del tipo "¿estos dos se
mueven juntos?", "¿cuándo conviene estar en uno y cuándo en el otro?" o
"¿la relación entre ambos se corrió de lo habitual?".

## Controles comunes

| Control | Para qué |
|---|---|
| **Activo 1** / **Activo 2** | Las dos puntas del par. El orden importa: define quién va arriba en el ratio y quién en cada eje del gráfico de correlación. |
| **⇄** | Intercambia los dos activos. Da vuelta el ratio y permuta los ejes. |
| **Fecha desde** / **Fecha hasta** | Recortan el período a analizar. |
| **Logarítmica** | Escala del eje de precios en las solapas **Comparación** y **Ratio**. En logarítmica un mismo porcentaje ocupa siempre la misma distancia visual, que es lo que querés cuando el período es largo. |
| **Analizar** | Dispara el cálculo. |

Los dos activos tienen que ser distintos, y ambos tienen que tener precios
dentro del período; si a uno le falta historia ahí, el sistema te lo dice por
ticker en vez de dibujar un gráfico vacío.

> **Comparación** y **Ratio** solo se actualizan cuando apretás **Analizar**.
> Cambiar las fechas o la escala y quedarte mirando el gráfico viejo es el error
> más común de esta pantalla: lo que ves sigue siendo la corrida anterior hasta
> que volvés a apretar el botón.

## Solapa «Comparación»

Los dos precios en el mismo gráfico, cada uno con **su propio eje vertical** —
el del Activo 1 a la izquierda, el del Activo 2 a la derecha, cada uno con el
color de su línea.

El doble eje es lo que permite comparar un activo de 5 pesos con uno de 20.000
sin que uno quede aplastado contra el piso. Pero trae una trampa que hay que
tener siempre presente: **cada eje se escala solo, así que los cruces entre las
dos líneas no significan nada**. Que una curva pase por encima de la otra es un
accidente de la escala, no un evento de mercado. Lo único legítimamente
interpretable acá es **la forma de cada curva y si los movimientos coinciden en
el tiempo**: subidas simultáneas, caídas desfasadas, una que se aplana mientras
la otra sigue.

Si lo que querés es comparar rendimientos, esta solapa no es la indicada — usá
[Evolución Relativa](/manual/evolucion), que lleva ambos a base 100 y ahí sí las
distancias entre líneas se leen como diferencia de rendimiento.

## Solapa «Ratio»

Dibuja el cociente **Activo 1 ÷ Activo 2** día por día, sobre las fechas en que
ambos cotizaron, más una **regresión lineal** punteada que resume la pendiente
del período.

### Qué mide realmente el ratio

El ratio mide **fuerza relativa**: cuando sube, el Activo 1 le está ganando al
Activo 2; cuando baja, es al revés. Nada más que eso. Y ese "ganar" es
relativo, no absoluto — **un ratio que sube es perfectamente compatible con que
los dos activos estén cayendo**, si el de arriba cae menos. Es justamente para
lo que sirve: aísla el desempeño de uno contra otro y saca de la ecuación al
mercado que ambos comparten.

### Qué NO significa

Acá se malinterpreta siempre, así que vale la pena ser explícito:

- **El nivel del ratio no significa nada por sí solo.** Que valga 0,3 o 47
  depende de las unidades y de la moneda de cada precio, no de si algo está
  caro o barato. El ratio **solo se lee contra su propia historia**: alto o bajo
  *respecto del rango en que se movió antes*.
- **No es un spread ni un z-score.** No hay bandas de desvío ni medida de
  "cuántos desvíos está fuera de lo normal". La única referencia que se dibuja
  es la recta de regresión.
- **La recta no predice.** Se ajusta sobre el período que vos elegiste y usa
  todos sus puntos, incluidos los últimos. Si cambiás las fechas, cambia la
  recta — y con ella la sensación de "está por encima" o "por debajo de la
  tendencia". No la trates como un nivel objetivo.
- **Un ratio que vuelve a su promedio no es una ley.** Que históricamente haya
  oscilado alrededor de un valor no obliga a que vuelva. Los pares se
  desacoplan de verdad cuando algo estructural cambia en uno de los dos.

> Si los dos activos cotizan en **monedas distintas**, el ratio mezcla el
> desempeño relativo con el movimiento del tipo de cambio, y no se puede separar
> mirando el gráfico. Para comparar en igualdad de condiciones conviene usar los
> sintéticos de conversión de moneda que el sistema genera, elegibles como
> cualquier otro activo en los selectores.

## Solapa «Correlación»

Un punto por cada día en que ambos cotizaron: el precio del **Activo 1 en el eje
horizontal**, el del **Activo 2 en el vertical**. Los puntos están **coloreados
por el paso del tiempo** (la barra lateral indica la primera y la última fecha)
y el **último día aparece destacado en rojo y con su fecha**, para que sepas
dónde está parado el par hoy dentro de la nube.

Esa nube dice cosas que las series temporales esconden: una nube alargada y
angosta es un par que se mueve en bloque; una nube dispersa es un par que
comparte poco; y cuando los colores forman **dos brazos separados**, la
relación cambió en algún momento del período — el par de hace tres años no es
el mismo que el de ahora.

| Control | Qué hace |
|---|---|
| **Línea de tendencia** | Ajusta una curva a la nube: **Lineal**, **Logarítmica**, **Polinómica** o **Exponencial**. Se muestra su ecuación y el **R²**. |
| **Grado** | Solo para la polinómica (de 2 a 10). Grados altos siguen la nube casi punto por punto, lo cual **no es una mejor descripción de la relación** sino un ajuste al ruido. |
| **Eventos de mercado** | Marca con estrellas los eventos globales y los propios de alguno de los dos activos, ubicados en el punto del día más cercano al centro del evento. |
| **Ambos ejes** | Pasa los dos ejes a escala logarítmica. |

Debajo del gráfico queda la línea de resumen: cuántos puntos entraron, el rango
de fechas y el **coeficiente de correlación** del par.

### Cómo leer el coeficiente

El **coeficiente de correlación** se calcula sobre los **retornos diarios** de
los dos activos, no sobre sus niveles de precio. Es la medida de si se mueven
juntos día a día: +1 en la misma dirección, −1 en sentidos opuestos, 0 sin
relación. Respeta el rango de fechas y el botón **Analizar** igual que las otras
dos solapas.

> **La nube es de precios; el coeficiente es de retornos.** Miran cosas
> distintas a propósito. La nube muestra si los precios recorrieron caminos
> parecidos; el número, si las variaciones diarias van de la mano. Por eso una
> nube que sube prolija —dos activos que simplemente subieron durante años—
> puede venir con una correlación baja: comparten la tendencia, no el
> comportamiento diario, y es este último el que importa para cubrirse o
> diversificar.

> **Correlación no es causalidad.** Que se muevan juntos no dice cuál mueve a
> cuál, ni descarta un tercer factor detrás de ambos. Un coeficiente alto es un
> punto de partida para investigar, no una conclusión.

El **R²** de la línea de tendencia, en cambio, se calcula sobre la nube (los
precios): mide qué tan bien la curva describe esa relación de niveles. Un R²
alto dice sobre todo que ambos recorrieron caminos parecidos en el período —
útil para elegir pares candidatos, flojo para decidir una posición.
