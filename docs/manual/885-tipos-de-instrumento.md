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
| **Moneda de cotización por defecto** | Sí | La moneda asociada al tipo. Es un dato del catálogo: el alta de un activo no la completa automáticamente. |

## Para qué se usa

**Es una de las cinco dimensiones de agrupación**, así que tiene sus propios
agregados de grupo y sirve como criterio en el filtro de elegibilidad de una
estrategia. Es la dimensión natural para separar universos que no son
comparables entre sí: una estrategia de acciones no debería rankear índices.

**Asocia una moneda de cotización al tipo.** Por ahora es un dato del
catálogo: el alta de un activo no la propone automáticamente — la moneda del
activo la elegís vos o la completa el autocompletado desde la fuente de
precios.

**Determina qué activos pueden ser divisores.** El selector de divisor de la
pantalla de [Activos en Divisa](/manual/activos-en-divisa) solo lista activos
cuyo tipo de instrumento se llame exactamente `CURRENCY` o `cryptoCURRENCY`
(los nombres con que el autocompletado los crea). Si un tipo de cambio que
cargaste no aparece como divisor disponible, revisá acá que su tipo sea uno de
esos dos: es la causa más frecuente. Y ojo con renombrarlos: el selector
dejaría de encontrarlos.

> **Un tipo en uso no se puede eliminar.** Si hay activos de ese tipo, primero
> hay que reasignarlos.
