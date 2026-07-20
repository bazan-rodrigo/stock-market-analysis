---
slug: historial-de-senales
title: Historial de Señales
chapter: 3. Análisis
order: 380
roles: invitado
page: /historial-senales
---

El [Screener de Señales](/manual/screener-de-senales) te muestra una foto: cómo
está un activo hoy. Esta pantalla muestra la película: **cómo llegó hasta acá
cada una de las señales de un activo**, a lo largo del tiempo y todas juntas en
el mismo gráfico.

Es la pantalla a la que ir cuando el screener te llamó la atención con un
activo y querés saber si ese score es un cambio reciente o algo que viene
sostenido hace meses.

---

## Elegir qué mirar

| Control | Para qué sirve |
|---|---|
| **Activo** | El activo a analizar. Se escribe para buscar; se puede filtrar por símbolo o por nombre. Es el único campo obligatorio. |
| **Estrategia** | Opcional. Si elegís una, la pantalla se limita a las señales que esa estrategia usa para puntuar. Si la dejás vacía (**Todas las señales**), trae todas las señales disponibles para vos: las públicas más las tuyas. |
| **Desde** / **Hasta** | El período del gráfico. Vienen cargadas con el último año. |
| **Ver** | Ejecuta la consulta y dibuja el gráfico. |

Elegir una estrategia acá **no grafica el score de la estrategia**: filtra qué
señales se muestran. Lo que ves son siempre las señales individuales, cada una
por su cuenta. Para seguir el score de una estrategia en el tiempo, esa es otra
pantalla.

Recién después de apretar **Ver** por primera vez aparece un cuarto control,
**Señales a mostrar**, con todas las señales tildadas. Ahí sacás y ponés
señales para despejar el gráfico, y se redibuja al instante sin volver a
apretar Ver.

> **Cambiar las fechas no redibuja solo.** Si movés **Desde** o **Hasta**,
> tenés que apretar **Ver** de nuevo. Lo mismo si cambiás de activo o de
> estrategia. La única cosa que actualiza el gráfico por sí sola es tocar
> **Señales a mostrar**.

Si venís del enlace **hist.** del screener, el activo ya llega seleccionado:
solo hace falta apretar **Ver**.

---

## El gráfico

Una línea por señal, todas en la misma escala de **−100 a +100** —que es la
escala común de todas las señales, por eso pueden convivir en un mismo par de
ejes sin normalizar nada. Cada punto es un día calculado.

El fondo está dividido en tres franjas que te ahorran leer números: la banda
verde superior (**por encima de +20**), la banda roja inferior (**por debajo de
−20**) y la zona neutra del medio. Las líneas punteadas marcan el cero y esos
dos umbrales. Son los mismos cortes de color que usa el screener, así que lo
que veías verde allá se ve en la banda verde acá.

Al pasar el mouse se despliega el valor de **todas las señales de ese día a la
vez**, no solo la que estás tocando. Eso es lo que hace útil la pantalla:
podés ver si las señales están alineadas o si se están contradiciendo entre
sí, día por día.

### Qué mirar

- **Cruces del cero.** El momento en que una señal pasa de negativa a positiva
  suele ser más informativo que su nivel absoluto.
- **Señales que se separan.** Cuando una señal se dispara a +80 y el resto
  sigue en cero, el score agregado de la estrategia se mueve poco. Acá se ve
  quién está empujando y quién está frenando.
- **Cuánto tiempo lleva ahí.** Un +70 de tres días y un +70 sostenido durante
  cuatro meses son situaciones distintas, y el screener no las distingue.
- **Escalones planos.** Si una línea se queda clavada en un valor, puede que la
  señal esté definida por categorías o por tramos y el indicador subyacente se
  esté moviendo dentro del mismo tramo.

Si una señal no tiene ningún dato para ese activo en ese período,
**directamente no se dibuja ni aparece en la tabla** — no verás una línea
vacía. Es normal en señales que dependen de datos que ese activo no tiene, como
las fundamentales en un índice o en un sintético.

---

## La tabla de resumen

Debajo del gráfico, una fila por señal graficada, con el cierre de la película:

| Columna | Qué muestra |
|---|---|
| **Key** | El identificador corto de la señal, el mismo que aparece en la definición de las estrategias. |
| **Señal** | El nombre completo. |
| **Última fecha** | El último día con valor calculado dentro del período elegido. |
| **Último score** | El valor de ese día, con el mismo código de color del gráfico. |

La columna **Última fecha** es más importante de lo que parece: si una señal
quedó con una fecha bastante anterior a las demás, ese activo dejó de tener
dato para esa señal en algún momento. Vale la pena entender por qué antes de
confiar en un score de estrategia que la incluya, porque una señal sin valor no
se computa como cero —se excluye del promedio, y el score que ves está armado
con las señales restantes.

> **El último punto es preliminar.** El día más reciente se calcula con el
> precio en curso y puede cambiar hasta el cierre. Si comparás el gráfico de
> hoy con el de ayer y el último tramo se movió, es esto y es esperado. Está
> explicado en [Cómo se calcula todo](/manual/conceptos-pipeline).

---

## Una advertencia sobre la lectura

Esta pantalla muestra señales **de este activo**, y las señales son
independientes del resto del universo: valen lo mismo hoy que hace un año, sin
importar cómo estén los demás. El score de una estrategia hereda esa propiedad,
pero **el puesto en el ranking no**: es transversal, depende de todos los
activos del día. Que una señal de este activo haya subido no garantiza que haya
subido en el ranking, ni al revés.

Cuando algo no cierra entre lo que ves acá y lo que veías en el screener, esa
suele ser la explicación.
