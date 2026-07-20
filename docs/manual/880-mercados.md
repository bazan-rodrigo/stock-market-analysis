---
slug: mercados
title: Mercados / Bolsas
chapter: 8. Administración
order: 880
roles: admin
page: /admin/markets
---

Catálogo de mercados o bolsas donde cotizan los activos. Funciona con el patrón
común descrito en [Tablas de referencia](/manual/tablas-de-referencia); acá van
solo sus campos.

## Campos

| Campo | Obligatorio | Qué es |
|---|---|---|
| **Nombre** | Sí | El nombre del mercado (por ejemplo `NYSE`). |
| **País** | No | El país al que pertenece, elegido del catálogo de [Países](/manual/paises). |
| **Benchmark** | No | Un activo del sistema que sirve de referencia para todo el mercado. |

## El benchmark del mercado

Es el campo que hace a esta tabla distinta de las otras. Un activo puede no
tener benchmark propio, y en ese caso **hereda el de su mercado**. Así, en vez
de asignarle el índice de referencia a cada acción una por una, lo cargás una
vez en el mercado y todas lo toman.

Ese benchmark heredado es el que se usa por defecto en las pantallas que
comparan un activo contra su referencia: la
[Rotación Relativa](/manual/rotacion-relativa) y la
[Evolución Relativa](/manual/evolucion).

> **El benchmark no participa del cálculo de señales ni del ranking.** Es una
> referencia de comparación para las pantallas de análisis. Que un activo le
> gane o le pierda a su benchmark no entra en su score.

> **Un activo usado como benchmark no se puede eliminar** mientras algún
> mercado o activo lo esté referenciando. Primero hay que sacarle esa función.

## Para qué se usa el mercado

Es una de las cinco dimensiones de agrupación, así que alimenta agregados de
grupo y sirve de criterio en el filtro de elegibilidad de una estrategia —ver
[Activos, sintéticos y grupos](/manual/activos-y-grupos)—. Además, el activo
toma su país a través del mercado.
