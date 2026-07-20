---
slug: formulas-de-senales
title: Referencia de fórmulas de señales
chapter: Apéndices
order: 910
roles: analista
---

Referencia de consulta de las tres fórmulas que traducen un indicador a un
puntaje. Para aprender cuándo conviene cada una, empezá por
[Señales — crear y editar](/manual/configuracion-senales); esta sección es para
consultar mientras armás una.

Toda señal produce un puntaje en el rango **−100 a +100**.

---

## Mapa discreto

**Para indicadores que devuelven categorías**, no números: régimen de tendencia,
régimen de volatilidad y similares.

Asignás a mano el puntaje de cada categoría posible:

| Categoría | Puntaje |
|---|---|
| `bullish_strong` | 100 |
| `bullish` | 60 |
| `lateral` | 0 |
| `bearish` | −60 |

> **Una categoría sin puntaje asignado no puntúa.** Si el activo cae en una
> categoría que no incluiste en el mapa, la señal no produce valor ese día — y
> una señal sin valor **no cuenta en el promedio** de la estrategia, no cuenta
> como cero.
>
> Es el error más frecuente con esta fórmula: mapear solo las categorías
> "interesantes" y dejar afuera las intermedias hace que la señal quede muda
> justo en los casos ambiguos. Revisá en
> [Indicadores del sistema](/manual/configuracion-indicadores) todas las
> categorías que el indicador puede devolver, y asignales puntaje a todas.

---

## Umbrales (escalones)

**Para indicadores numéricos, cuando querés puntajes por tramos.**

Se define una lista de pares límite → puntaje, y **se evalúa de arriba hacia
abajo: gana el primer límite que el valor supera**. El último tramo, sin límite,
es el "en cualquier otro caso".

Ejemplo con el drawdown:

| Condición | Puntaje |
|---|---|
| mayor a −5% | 100 |
| mayor a −15% | 50 |
| mayor a −30% | 0 |
| en cualquier otro caso | −50 |

Un activo con −10% de drawdown no supera el primer límite pero sí el segundo, y
saca 50.

> **El orden importa y no se corrige solo.** Como gana el primer límite que se
> cumple, una lista mal ordenada produce resultados silenciosamente incorrectos:
> si el tramo más permisivo queda arriba, absorbe todos los casos y los de abajo
> nunca se evalúan. Ordenálos siempre del más exigente al menos exigente.

A diferencia del mapa discreto, **todo valor posible recibe un puntaje**,
gracias al tramo final sin límite. Es la fórmula más segura cuando no querés
huecos.

---

## Rango lineal

**Para indicadores numéricos, cuando querés una escala continua** en vez de
escalones.

Definís dos puntos y el resto se interpola en línea recta:

| Parámetro | Qué es |
|---|---|
| **Mínimo** | El valor del indicador que vale **−100** |
| **Máximo** | El valor del indicador que vale **+100** |
| **Recortar** | Qué hacer con los valores que quedan fuera del rango |

El punto medio entre mínimo y máximo da 0.

Con **Recortar activado**, todo lo que quede fuera del rango se ajusta a ±100
exactos. Con **Recortar desactivado**, un valor más extremo que el rango
**produce un puntaje mayor a 100 o menor a −100**.

> Dejá **Recortar activado** salvo que sepas exactamente por qué lo querés
> apagar. Un puntaje de 340 en un componente distorsiona el promedio ponderado
> de toda la estrategia y hace que el ranking lo domine un solo activo con un
> valor extremo.

Ejemplo: para una distancia medida en desvíos estándar, un rango de **−3 a +3**
con recorte activado cubre prácticamente todos los casos reales.

---

## Elegir la fórmula correcta

| Si el indicador… | Usá |
|---|---|
| Devuelve categorías | Mapa discreto |
| Devuelve números y querés tramos claros | Umbrales |
| Devuelve números y querés una escala continua | Rango lineal |

El tipo de cada indicador está en la columna **Tipo** de
[Indicadores del sistema](/manual/configuracion-indicadores).

## Después de cambiar una fórmula

> Modificar los parámetros de una señal **no recalcula lo ya guardado**. Los
> valores históricos siguen calculados con la definición anterior hasta que
> corras un recálculo completo — ver
> [Cómo se calcula todo](/manual/conceptos-pipeline) y
> [Centro de Datos](/manual/centro-de-datos).
>
> Es especialmente engañoso al hacer backtest: si ajustás una señal y volvés a
> correr el backtest sin recalcular, estás midiendo la versión vieja.
