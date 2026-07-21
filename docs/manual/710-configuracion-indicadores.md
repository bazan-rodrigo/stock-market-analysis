---
slug: configuracion-indicadores
title: Indicadores del sistema
chapter: 7. Configuración
order: 710
roles: admin
page: /admin/indicators
---

El catálogo de todos los indicadores que el sistema calcula. Son la materia
prima de las señales: cada señal traduce **un** indicador a un puntaje, así que
esta pantalla dice qué materia prima hay disponible.

> **Es una pantalla de consulta, no de edición.** No se pueden crear indicadores
> nuevos ni modificar los existentes desde acá. El catálogo viene definido con el
> sistema; lo que sí se configura es el comportamiento de algunos de ellos, en
> las pantallas de configuración que se listan más abajo.

## Las columnas

| Columna | Qué dice |
|---|---|
| **Código** | El identificador corto del indicador. Es el que vas a elegir al crear una señal. |
| **Nombre** | El nombre legible. |
| **Categoría** | La familia a la que pertenece (Trend, Momentum, Volatility…). Sirve para orientarse en una lista larga. |
| **Tipo** | Si el indicador da un **número** (aparece como `num`) o una **categoría** (aparece como `str`). Es la columna más importante — ver abajo. |
| **Escala** | El rango o la unidad en la que se mueve, cuando aplica. |
| **Guarda histórico** | Si se conserva la serie completa o solo el valor vigente. |
| **Descripción** | Qué mide. |

Cada columna tiene su casilla de filtro en el encabezado, que es la forma
práctica de encontrar algo en una lista larga.

## Tipo: la columna que decide qué fórmula podés usar

Es el dato que más te va a servir, porque **determina qué fórmula de señal
podés aplicarle**:

| Si el tipo es… | La fórmula que corresponde |
|---|---|
| **Categoría** (`str`: bullish, lateral, bearish…) | Mapa discreto: asignás un puntaje a cada categoría posible. |
| **Número** | Umbrales o rango lineal, según quieras tramos o una escala continua. |

Elegir una fórmula que no corresponde al tipo del indicador es el error más
común al crear una señal. Está explicado en
[Señales — crear y editar](/manual/configuracion-senales), y la referencia
completa de las fórmulas en
[Referencia de fórmulas de señales](/manual/formulas-de-senales).

## Guarda histórico: por qué importa

Un indicador que **guarda histórico** tiene la serie completa día por día. Uno
que no, solo tiene el valor de hoy.

La diferencia se nota en tres lugares:

- **En el gráfico técnico**, solo se puede dibujar la evolución de un indicador
  con historia.
- **En el [Explorador de datos](/manual/explorador-de-datos)**, el selector de
  indicadores solo lista los que la tienen.
- **En el backtest**, una señal construida sobre un indicador sin historia no se
  puede evaluar hacia atrás.

## Dónde se configura el comportamiento

Varios indicadores tienen parámetros propios, y esos sí se editan — cada uno en
su pantalla:

| Indicador | Pantalla |
|---|---|
| Régimen de tendencia | [Régimen de Tendencia](/manual/regimen-de-tendencia) |
| Régimen de volatilidad | [Volatilidad ATR](/manual/volatilidad-atr) |
| Drawdowns | [Drawdowns](/manual/drawdowns) |
| Soportes y resistencias | [Soporte / Resistencia](/manual/soporte-resistencia) |

El [Punto y Figura](/manual/punto-y-figura) también tiene su pantalla de
configuración en este menú, pero lo que configura es un tipo de gráfico del
Análisis de Activo, no un indicador de este catálogo.

> **Cambiar cualquiera de esas configuraciones invalida lo ya calculado.** Los
> valores históricos quedaron computados con los parámetros anteriores, y solo
> un recálculo completo los pone al día. Ver
> [Cómo se calcula todo](/manual/conceptos-pipeline) y
> [Centro de Datos](/manual/centro-de-datos).

Para una descripción de qué mide cada indicador, con sus parámetros y cómo se
lee, está el [Glosario de indicadores](/manual/glosario-de-indicadores).
