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

**Le da alcance a los mercados.** Cada mercado puede tener un país asignado.
Es un dato propio del mercado: el activo tiene su **propio** campo País, que se
carga en su alta o en la importación, independiente del país del mercado.

**Delimita los eventos de mercado.** Un evento cargado con alcance de país se
muestra sobre los gráficos de los activos de ese país y no sobre los demás —
ver [Eventos de mercado](/manual/eventos-de-mercado).

> **El código ISO también sirve para hacer coincidir al importar.** La
> importación de activos primero busca el país por su **código ISO** y, si no
> hay coincidencia, lo resuelve **por nombre** (o por una equivalencia
> registrada en el mapper). Así, una planilla exportada —que trae el código—
> se reimporta sin crear duplicados. Un texto que no coincide ni como código ni
> como nombre crea un país nuevo con ese texto; para consolidar variantes está
> el [Mapper de catálogo](/manual/mapper-de-catalogo).
