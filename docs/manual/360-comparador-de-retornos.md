---
slug: comparador-de-retornos
title: Comparador de Retornos
chapter: 3. Análisis
order: 360
roles: invitado
page: /retornos
---

Responde una pregunta simple y muy usada: **¿quién rindió más y quién menos en
un lapso determinado?** Elegís un período, elegís un conjunto de activos, y la
pantalla devuelve un gráfico de barras con el retorno porcentual de cada uno,
ordenado de mejor a peor.

Es la pantalla para el "¿cómo viene el sector energía este mes?" o "¿le ganamos
al índice en lo que va del año?". No calcula señales ni scores: mide retorno
puro de precio.

---

## Período

Los botones definen la ventana de medición. Todos terminan **hoy**, salvo el
rango personalizado.

| Botón | Desde cuándo mide |
|---|---|
| **1D** | 1 día atrás — el retorno de la última rueda. |
| **1S** | 7 días atrás. |
| **1M** | 30 días atrás. |
| **3M** | 91 días atrás. |
| **6M** | 182 días atrás. |
| **YTD** | Desde el 1° de enero del año en curso. |
| **1A** | 365 días atrás. |
| **rng** | Rango personalizado: habilita los campos **Desde** y **Hasta**. |

El conteo es en **días corridos**, no en ruedas. Eso importa porque la fecha de
inicio suele caer en un día sin cotización (un domingo, un feriado): el sistema
no la descarta ni la interpola, sino que toma **el último cierre disponible en
o antes de esa fecha**. Lo mismo hace con la fecha de fin. En la práctica la
ventana real puede arrancar unos días antes de la nominal, y por eso el detalle
del gráfico muestra siempre las **fechas efectivas** que se usaron.

El retorno es la cuenta directa entre esos dos cierres: cuánto subió o bajó el
precio final respecto del inicial, expresado en porcentaje con dos decimales.
No hay ponderación, ni anualización, ni ajuste por el largo real de la ventana
— un **1A** que arrancó cuatro días antes de lo nominal se informa igual como
retorno del período, no como retorno anualizado.

---

## Activos

Cuatro modos de armar el conjunto a comparar. Cambiar de modo cambia el
selector de abajo; solo se usa el modo activo.

| Modo | Qué compara |
|---|---|
| **Individual** | Los activos que elijas a mano, uno por uno. Es el modo para comparaciones puntuales. |
| **Grupo** | Todos los activos de una categoría: elegís la dimensión (**Sector**, **Industria**, **País**, **Mercado**, **Tipo de Instrumento**) y después el valor concreto. |
| **Benchmark** | Elegís un índice de referencia y se comparan **los activos que lo tienen como benchmark** — los que lo declaran directamente y los que lo heredan de su mercado. |
| **Sintético** | Elegís un activo calculado y se comparan **los componentes de su fórmula**, no el sintético en sí. Sirve para ver qué pata de un ratio explica su movimiento. |

En los modos **Benchmark** y **Sintético** el activo que elegís no aparece en el
gráfico: se usa como puerta de entrada al conjunto que lo referencia o que lo
compone. Si un benchmark no tiene ningún activo asociado, entonces sí se grafica
el benchmark solo.

> En el selector **Individual**, un activo con **⚠️** delante del ticker tiene
> discrepancias de cálculo o posibles errores en los datos de origen detectados
> por la verificación. Su retorno puede no ser confiable.

---

## El gráfico

Apretás **Calcular retornos** y aparece el resultado. Las barras vienen
**ordenadas de mayor a menor retorno**, verdes las positivas y rojas las
negativas, con el porcentaje escrito sobre cada una. Cuando hay más de una
docena de activos las etiquetas del eje se inclinan para que sigan siendo
legibles.

Pasando el mouse por una barra se abre el detalle completo: ticker y nombre,
retorno, y las dos puntas de la medición — fecha y precio de cierre inicial,
fecha y precio de cierre final. Ese detalle es la forma de confirmar qué
ventana se usó realmente para ese activo en particular.

### Activos que quedan afuera

No todos los activos seleccionados llegan al gráfico. Se excluyen en silencio
los que no se pueden medir:

- Los que **no tenían ningún precio anterior a la fecha de inicio** — típicamente
  activos que empezaron a cotizar después. No hay punto de partida contra el cual
  comparar.
- Los que tienen **un solo cierre disponible** para toda la ventana, porque el
  precio inicial y el final serían el mismo dato.
- Los que tienen precio inicial cero o vacío.

Cuando pasa, un aviso arriba del gráfico informa **cuántos activos se
excluyeron**. Es un dato a mirar: si pediste un sector de 40 activos y el
gráfico muestra 12, el aviso te está diciendo que la ventana elegida es
demasiado larga para la historia disponible de la mayoría.

> Si **ningún** activo tiene datos para el período, no se dibuja nada y aparece
> el mensaje correspondiente. Lo mismo si no seleccionaste activos, o si en el
> rango personalizado la fecha de inicio no es anterior a la de fin.

---

## Cuándo usar esta pantalla y cuándo no

Sirve para comparar **rendimiento realizado** entre activos comparables entre
sí. Donde conviene tener cuidado es al mezclar activos de mercados o monedas
distintas: dos acciones cotizadas en monedas diferentes no son comparables
directamente, y para eso están los sintéticos de conversión descriptos en
[Cómo se calcula todo](/manual/conceptos-pipeline).

Y si lo que buscás no es "cuánto rindió" sino "cómo se movió uno respecto del
otro a lo largo del tiempo", la pantalla adecuada es
[Análisis de Activo](/manual/analisis-de-activo) para el detalle de uno solo, o
la de correlación para la relación entre dos.
