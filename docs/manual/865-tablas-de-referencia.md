---
slug: tablas-de-referencia
title: Tablas de referencia — cómo funcionan
chapter: 8. Administración
order: 865
roles: admin
---

Países, monedas, mercados, tipos de instrumento, sectores e industrias son las
**tablas de referencia**: los catálogos de los que después eligen los activos.
Las seis funcionan exactamente igual, así que el patrón se explica una sola vez
acá y cada sección siguiente solo detalla sus campos propios.

## El patrón común

Todas las pantallas tienen la misma estructura: una tabla con lo cargado y un
botón **+ Nuevo** al lado del título.

| Acción | Cómo |
|---|---|
| **Crear** | **+ Nuevo** abre el formulario vacío. |
| **Editar** | Seleccionás la fila y apretás **Editar**. |
| **Eliminar** | Seleccionás una o más filas y apretás **Eliminar**. Pide confirmación. |
| **Filtrar** | Cada columna tiene su casilla de filtro en el encabezado. |

El borrado admite **varias filas a la vez**, y el mensaje de confirmación te
dice cuántas vas a eliminar. Si alguna no se puede borrar, el resultado te
informa cuántas se eliminaron y muestra los errores de las que fallaron (que
siguen apareciendo en la tabla): el borrado múltiple **no es todo o nada**,
procesa lo que puede.

> **Un elemento en uso no se puede eliminar.** Si hay activos apuntando a ese
> sector, mercado o moneda, el borrado falla con un mensaje de error. Primero
> hay que reasignar esos activos.

## El formulario no se cierra si hay un error

Cuando algo falla al guardar —un nombre repetido, un campo obligatorio vacío—
el mensaje aparece **dentro del formulario y el formulario queda abierto**, con
todo lo que habías cargado intacto. Es deliberado: corregís el campo que estuvo
mal y volvés a guardar, sin retipear el resto.

El formulario se cierra **solamente** cuando el guardado sale bien. Si se
cerró, se guardó.

## Por qué importan estas tablas

No son burocracia: son las dimensiones por las que después se agrupa y filtra
todo el sistema. El sector y el mercado de un activo alimentan los agregados de
grupo que consumen las señales de grupo, y son los criterios que usás en el
filtro de elegibilidad de una estrategia. Está explicado en
[Activos, sintéticos y grupos](/manual/activos-y-grupos).

> **Cambiar la agrupación de un activo cambia el pasado.** Si movés un activo
> de sector, los agregados históricos de ambos sectores dejan de coincidir con
> lo que hay calculado. Para que la historia refleje la nueva agrupación hace
> falta un recálculo completo — ver
> [Cómo se calcula todo](/manual/conceptos-pipeline).

## De dónde salen estos datos

No hace falta cargarlos todos a mano. Cuando se da de alta un activo con
**Autocompletar desde fuente**, o cuando se importa una planilla de activos, los
catálogos que no existen **se crean solos** con el nombre que venga de la
fuente. Ver [Gestión de activos](/manual/gestion-de-activos) e
[Importar activos](/manual/importar-activos).

La consecuencia práctica es que estas tablas tienden a llenarse solas, y el
trabajo real acá suele ser **limpiar duplicados** —el mismo sector escrito de
dos formas distintas— más que dar de alta desde cero. Para consolidar nombres
que llegan distintos desde la fuente está el
[Mapper de catálogo](/manual/mapper-de-catalogo).
