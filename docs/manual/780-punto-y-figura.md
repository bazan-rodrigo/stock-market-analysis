---
slug: punto-y-figura
title: Punto y Figura — configuración
chapter: 7. Configuración
order: 780
roles: admin
page: /admin/pnf-config
---

## Qué es un gráfico de Punto y Figura

Un gráfico de velas dibuja **una barra por rueda**: si el activo no se movió,
igual ocupa lugar en el eje. El Punto y Figura hace lo contrario: **ignora el
tiempo y solo dibuja movimiento de precio**.

El precio se divide en escalones de tamaño fijo llamados **cajas**. Mientras el
precio sube, se van apilando **X** hacia arriba en la misma columna. Cuando
retrocede lo suficiente, se abre una columna nueva de **O** que baja. Una
columna dura lo que tarde en darse vuelta: puede cubrir tres ruedas o siete
meses, y en el gráfico ocupa exactamente el mismo ancho.

Para qué sirve: filtra el ruido. Los movimientos chicos no dibujan nada, así que
lo que queda a la vista son los tramos con recorrido real, y los soportes y
resistencias aparecen como niveles horizontales tocados por varias columnas.

En el sistema, el P&F se ve desde
[Análisis de Activo](/manual/analisis-de-activo) → **Gráfico Técnico**, con dos
opciones del selector de tipo de gráfico:

- **P&F** — las columnas se dibujan sobre el gráfico principal, respetando el
  eje de tiempo (cada columna queda fechada en la rueda en que marcó su último
  extremo —la X más alta o la O más baja—, no en la que se dio vuelta: si una
  columna hizo su máximo y después estuvo semanas de costado antes de revertir,
  queda dibujada en el día del máximo).
- **P&F X/O** — el clásico, con la grilla de cajas y las X y O dibujadas una por
  una. Sin eje de tiempo: todas las columnas ocupan el mismo ancho, dure lo que
  dure cada una. Abajo aparecen algunas fechas, pero son solo una referencia
  —marcan el arranque de esas columnas—, no una escala temporal.

Esta pantalla define, **para toda la aplicación**, cómo se construyen esas
columnas. No hay configuración por activo ni por usuario: es una sola
configuración global que aplica a todos.

---

## El tamaño de caja

Es la decisión más importante: define cuánto tiene que moverse el precio para
que se dibuje algo. Caja chica = muchas columnas y mucho detalle; caja grande =
pocas columnas, solo los movimientos importantes.

| Método | Cómo se calcula | Cuándo conviene |
|---|---|---|
| **ATR (volatilidad del activo)** | Toma la volatilidad promedio reciente del activo. Un activo nervioso recibe cajas más grandes que uno tranquilo. | El recomendado, y sobre todo si mirás activos muy distintos entre sí: cada uno se autorregula. |
| **Porcentaje del precio** | Un porcentaje del precio del activo. El clásico es 1 %. | Cuando querés el mismo criterio relativo para todos, sin que la volatilidad entre en juego. |
| **Valor fijo** | Un valor absoluto en unidades de precio, igual para todos los activos. | Solo si trabajás con activos de precios comparables. Aplicado a una cartera mixta da resultados sin sentido. |

> Si el método elegido no puede calcularse (por ejemplo, ATR sobre un activo con
> muy poca historia) o da un valor cero o negativo, el sistema cae a un
> **1 % del último precio** en vez de dejar el gráfico vacío.

### La caja es una sola para toda la historia del gráfico

Esto es lo que más sorprende. Cualquiera sea el método, el tamaño de caja se
calcula **una vez, a partir del último precio disponible**, y ese mismo valor
absoluto se usa para toda la serie histórica.

Es decir: **Porcentaje del precio** no es "1 % de cada barra"; es "1 % del
último cierre", convertido a un número fijo. Con ATR pasa lo mismo: se toma la
volatilidad vigente al final de la serie.

La consecuencia práctica: en un activo que multiplicó su precio muchas veces, la
historia vieja queda comprimida (un 1 % de hoy puede ser un 30 % de aquel
entonces, y aquellos movimientos no dibujan casi nada). Si te interesa analizar
un período antiguo, mirá con desconfianza las columnas de esa zona.

Además, las cajas están ancladas al cero: la primera arranca en 0 y de ahí van
en escalones parejos. Los bordes de las cajas no se acomodan al precio del
activo.

---

## La reversión

La **reversión** es cuántas cajas tiene que retroceder el precio, en contra de la
columna actual, para que se abra la columna opuesta. El estándar histórico es 3.

- **Reversión baja (1 o 2)** — el gráfico se da vuelta ante cualquier
  retroceso. Muchas columnas, más ruido, pero reaccionás antes.
- **Reversión alta (4 o más)** — solo cambian de columna los movimientos
  grandes. Gráfico limpio, señales tardías.

Hay dos detalles de la regla que conviene tener claros:

**Extender le gana a revertir.** En cada rueda, el sistema primero intenta
*continuar* la columna vigente. Si el precio hizo un máximo nuevo mientras está
en una columna de X, la columna se extiende — aunque en esa misma rueda también
haya hecho un mínimo lo bastante profundo como para justificar la vuelta. La
reversión se evalúa **solo** cuando la columna no pudo extenderse. Por eso una
rueda de rango enorme suele alargar la columna en vez de darla vuelta.

**La columna nueva arranca una caja más adentro.** Al revertir, la primera caja
de la columna opuesta no es la del extremo anterior sino la siguiente: la X más
alta de la columna previa no se vuelve a pisar con una O. Esto hace que el
recorrido visible de la columna nueva sea una caja menor que el retroceso real.

---

## La fuente de precio

Define qué precio de cada rueda alimenta el cálculo.

| Opción | Qué usa | Efecto |
|---|---|---|
| **Solo cierres** | Únicamente el cierre de cada rueda. | Filtra el ruido intradiario. Menos columnas y menos reversiones falsas por un pico aislado. |
| **Máximos y mínimos** | El máximo y el mínimo de cada rueda. | El método clásico. Captura los extremos: llega antes a los quiebres, pero también genera más vueltas. |

Con **Solo cierres**, una rueda que hizo un máximo espectacular y cerró donde
empezó no deja rastro. Con **Máximos y mínimos**, esa misma rueda puede extender
la columna varias cajas.

---

## Los campos de la pantalla

| Campo | Rango admitido | Notas |
|---|---|---|
| **Método de tamaño de caja** | ATR / Porcentaje / Valor fijo | Define cuál de los tres campos siguientes se usa. |
| **Caja: % del precio** | 0,1 a 20 | Solo con método Porcentaje. Clásico: 1. |
| **Caja: período ATR** | 2 a 100 | Solo con método ATR. Típico: 14. |
| **Caja: valor fijo** | desde 0,0001 | Solo con método Fijo, en unidades de precio. |
| **Reversión (cajas)** | 1 a 10 | Clásico: 3. |
| **Fuente de precio** | Solo cierres / Máximos y mínimos | |

Al guardar se guardan **los cuatro campos de caja**, no solo el del método
activo. Eso es a propósito: podés dejar preparados los valores de los tres
métodos y después alternar entre ellos cambiando un solo desplegable.

> Si dejás algún campo vacío, el guardado no se hace y aparece «Completá todos
> los campos». Es una pantalla de todo o nada: no guarda parcialmente.

Los cambios **no se aplican solos al gráfico que ya tenías abierto**: hay que
volver a cargar el activo en Análisis de Activo para verlos.

---

## Qué no hace esta pantalla

El P&F se dibuja en el momento, a partir de los precios. **No forma parte del
encadenamiento de indicadores, señales y estrategias** descripto en
[Cómo se calcula todo](/manual/conceptos-pipeline): no alimenta ninguna señal ni
ningún ranking. Por eso cambiar esta configuración es barato y reversible —
**no dispara ni requiere ningún recálculo**, ni incremental ni completo, y no
hay nada que se pueda perder o corromper al tocarla.

---

## Detalles del gráfico que dependen de esta configuración

**El P&F X/O siempre usa ruedas diarias.** El selector **D / W / M** de Análisis
de Activo no lo afecta: aunque estés mirando el gráfico en semanal o mensual, al
pasar a **P&F X/O** las columnas se construyen sobre la serie diaria. Tampoco le
llega el selector **Arit / Log** — el clásico se dibuja siempre en escala
aritmética, que además es lo coherente con una grilla de cajas de tamaño
absoluto. La opción **P&F** (la que va sobre el gráfico principal) sí respeta la
frecuencia elegida, pero **con el tamaño de caja calculado sobre la serie
diaria**: la caja no se agranda al pasar a mensual.

**En modo P&F, los indicadores superpuestos se calculan sobre las columnas.** Al
reemplazar las barras por columnas, todo lo que dibujes encima (medias móviles,
RSI, MACD, y demás) se calcula sobre esa serie de columnas, no sobre las ruedas
originales. No son comparables con los mismos indicadores en modo Velas. Por la
misma razón, el panel de **volumen** aparece vacío en modo P&F: una columna no
tiene volumen propio.

**Título y ayudas.** El gráfico clásico muestra en su título el tamaño de caja
efectivo, el método, la reversión y la fuente — es la forma rápida de confirmar
qué configuración está viendo el gráfico. Pasando el mouse por cada X u O se ve
el rango de precios de esa caja y las fechas de inicio y fin de la columna.

Si el activo no tiene historia suficiente como para formar una sola columna, el
**P&F X/O** avisa con «Sin datos suficientes para el P&F». La opción **P&F**
sobre el gráfico principal no muestra ningún aviso: simplemente no dibuja
ninguna columna. Con cajas muy grandes sobre un activo poco volátil, eso puede
pasar aun con años de precios: bajá el tamaño de caja.
