---
slug: tipos-de-instrumento
title: Tipos de instrumento
chapter: 8. Administración
order: 885
roles: admin
page: /admin/instrument-types
---

Catálogo de tipos de instrumento: acción, índice, ETF, moneda, criptomoneda, y
los que necesites. Funciona con el patrón común descrito en
[Tablas de referencia](/manual/tablas-de-referencia); acá van solo sus campos.

## Campos

| Campo | Obligatorio | Qué es |
|---|---|---|
| **Nombre** | Sí | El nombre del tipo (por ejemplo `Acción`). |
| **Moneda de cotización por defecto** | No | La moneda que se propone al dar de alta un activo de este tipo. |

## Para qué se usa

**Es una de las cinco dimensiones de agrupación**, así que tiene sus propios
agregados de grupo y sirve como criterio en el filtro de elegibilidad de una
estrategia. Es la dimensión natural para separar universos que no son
comparables entre sí: una estrategia de acciones no debería rankear índices.

**Propone la moneda al dar de alta un activo.** Si el tipo declara una moneda
por defecto, el alta la sugiere. Es solo un default: se puede cambiar activo por
activo.

**Determina qué activos pueden ser divisores.** El selector de divisor de la
pantalla de [Activos en Divisa](/manual/activos-en-divisa) solo lista activos
cuyo tipo de instrumento sea de moneda o criptomoneda. Si un tipo de cambio que
cargaste no aparece como divisor disponible, revisá su tipo de instrumento
acá: es la causa más frecuente.

> **Un tipo en uso no se puede eliminar.** Si hay activos de ese tipo, primero
> hay que reasignarlos.
