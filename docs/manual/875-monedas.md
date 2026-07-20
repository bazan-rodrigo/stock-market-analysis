---
slug: monedas
title: Monedas
chapter: 8. Administración
order: 875
roles: admin
page: /admin/currencies
---

Catálogo de monedas de cotización. Funciona con el patrón común descrito en
[Tablas de referencia](/manual/tablas-de-referencia); acá van solo sus campos.

## Campos

| Campo | Obligatorio | Qué es |
|---|---|---|
| **Nombre** | Sí | El nombre de la moneda (por ejemplo `Dólar Estadounidense`). |
| **Código ISO** | No | El código corto (`USD`, `ARS`). Hasta 10 caracteres. |

## Para qué se usa la moneda

**Indica en qué unidad cotiza cada activo.** Es un dato del activo, no un
mecanismo de conversión: guardar que un activo cotiza en dólares no convierte
nada por sí solo.

**Es el default del tipo de instrumento.** Cada tipo de instrumento puede
declarar una moneda por defecto, que es la que se propone al dar de alta un
activo de ese tipo —ver
[Tipos de instrumento](/manual/tipos-de-instrumento)—.

**Habilita los activos en divisa.** La pantalla de
[Activos en Divisa](/manual/activos-en-divisa) genera, por cada activo en una
moneda, un activo calculado que lo expresa en otra unidad. Ese mecanismo se
apoya en la moneda declarada de cada activo.

> **La moneda NO es una dimensión de agrupación.** A diferencia del sector, el
> mercado, la industria, el país y el tipo de instrumento, no existen agregados
> de grupo por moneda. Sirve para identificar y convertir, no para rankear
> conjuntos de activos.

> **Cambiar la moneda de un activo tiene efectos colaterales.** Al editarlo
> individualmente, sus conversiones de divisa se regeneran; al hacerlo por
> edición masiva, no. Está detallado en
> [Gestión de activos](/manual/gestion-de-activos).
