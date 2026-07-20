---
slug: paises
title: Países
chapter: 8. Administración
order: 870
roles: admin
page: /admin/countries
---

Catálogo de países. Funciona con el patrón común descrito en
[Tablas de referencia](/manual/tablas-de-referencia); acá van solo sus campos.

## Campos

| Campo | Obligatorio | Qué es |
|---|---|---|
| **Nombre** | Sí | El nombre del país tal como querés verlo en toda la aplicación (por ejemplo `Argentina`). |
| **Código ISO** | No | El código de 2 o 3 letras (`AR`, `USA`). Máximo 3 caracteres. |

## Para qué se usa el país

**Es una de las cinco dimensiones de agrupación** de los activos, así que puede
alimentar agregados de grupo y servir de criterio en el filtro de elegibilidad
de una estrategia.

**Le da alcance a los mercados.** Cada mercado pertenece a un país, y el activo
hereda ese país a través de su mercado.

**Delimita los eventos de mercado.** Un evento cargado con alcance de país se
muestra sobre los gráficos de los activos de ese país y no sobre los demás —
ver [Eventos de mercado](/manual/eventos-de-mercado).

> **El código ISO no se usa para hacer coincidir nada al importar.** La
> importación de activos resuelve el país **por nombre** (o por una equivalencia
> registrada en el mapper), no por su código. Si en una planilla ponés `US`
> donde el catálogo dice `Estados Unidos`, y no hay una equivalencia cargada, se
> crea un país nuevo llamado `US`. Ver
> [Mapper de catálogo](/manual/mapper-de-catalogo).
