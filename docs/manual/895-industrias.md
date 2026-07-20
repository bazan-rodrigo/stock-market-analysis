---
slug: industrias
title: Industrias
chapter: 8. Administración
order: 895
roles: admin
page: /admin/industries
---

Catálogo de industrias: el nivel fino de la clasificación económica, por debajo
del sector. Funciona con el patrón común descrito en
[Tablas de referencia](/manual/tablas-de-referencia); acá van solo sus campos.

## Campos

| Campo | Obligatorio | Qué es |
|---|---|---|
| **Nombre** | Sí | El nombre de la industria (por ejemplo `Consumer Electronics`). |
| **Sector** | No | El sector al que pertenece, elegido del catálogo de [Sectores](/manual/sectores). |

## Sector o industria: cuál conviene usar

Las dos son dimensiones de agrupación válidas y las dos generan agregados. La
diferencia es el grano:

| | Sector | Industria |
|---|---|---|
| **Granularidad** | Grueso | Fino |
| **Activos por grupo** | Muchos | Pocos |
| **Agregado** | Estable | Ruidoso si el grupo es chico |
| **Sirve para** | Rotación entre grandes bloques | Distinguir negocios distintos dentro de un mismo sector |

> **El agregado de una industria con pocos activos no significa gran cosa.** Un
> promedio de régimen calculado sobre dos o tres activos se mueve con cualquier
> cosa. En el
> [Mapa de Tendencia de Mercado](/manual/mapa-de-tendencia) la solapa de
> industrias trae una columna con la cantidad de activos de cada grupo:
> mirala siempre antes de sacar conclusiones, y desconfiá de los grupos chicos.

Como criterio general: **empezá por sector** y bajá a industria solo cuando
tengas una razón concreta y el grupo tenga suficientes activos.

## Nota sobre la carga automática

Las industrias suelen crearse solas al dar de alta o importar activos, tomando
el nombre que venga de la fuente externa. Eso hace que esta tabla sea la más
propensa a acumular duplicados y variantes de escritura. Para consolidar nombres
que llegan distintos está el [Mapper de catálogo](/manual/mapper-de-catalogo).
