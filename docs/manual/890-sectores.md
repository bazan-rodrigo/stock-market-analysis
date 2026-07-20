---
slug: sectores
title: Sectores
chapter: 8. Administración
order: 890
roles: admin
page: /admin/sectors
---

Catálogo de sectores económicos. Funciona con el patrón común descrito en
[Tablas de referencia](/manual/tablas-de-referencia); acá va solo lo propio.

## Campos

| Campo | Obligatorio | Qué es |
|---|---|---|
| **Nombre** | Sí | El nombre del sector (por ejemplo `Technology`). |

Es la tabla más simple del sistema: un solo campo. Toda su importancia está en
lo que cuelga de ella.

## Por qué el sector es la agrupación más usada

De las cinco dimensiones de agrupación, el sector suele ser la más útil, por dos
razones.

**Alimenta los agregados de tendencia.** El promedio de régimen de los activos
de un sector es lo que se ve en el
[Mapa de Tendencia de Mercado](/manual/mapa-de-tendencia) y lo que consumen las
señales de grupo. Una señal puede preguntar "¿el sector de este activo viene
bien?" y eso sale de acá.

**Es el criterio de rotación por excelencia.** Las estrategias que rotan entre
sectores usan esta dimensión en su filtro de elegibilidad y en sus componentes
de grupo.

## La jerarquía sector → industria

Cada industria pertenece a un sector, así que las dos tablas forman una
jerarquía de dos niveles: el sector es el nivel grueso y la industria el fino.
Ver [Industrias](/manual/industrias).

Como regla práctica, **el sector suele dar agregados más confiables que la
industria**, simplemente porque agrupa más activos. Un promedio sobre tres
activos se mueve por ruido.

> **Cuidado al consolidar duplicados.** Si el mismo sector quedó cargado con dos
> nombres distintos y unificás, los activos que reasignes cambian de grupo, y
> los agregados históricos de ambos sectores dejan de reflejar la agrupación
> actual hasta que se haga un recálculo completo — ver
> [Cómo se calcula todo](/manual/conceptos-pipeline).
