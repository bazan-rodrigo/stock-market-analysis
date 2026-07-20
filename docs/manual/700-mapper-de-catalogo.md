---
slug: mapper-de-catalogo
title: Mapper de catálogo
chapter: 7. Configuración
order: 700
roles: admin
page: /admin/catalog-mapper
---

Los datos que llegan desde la fuente externa traen el país, el mercado, el tipo
de instrumento, el sector y la industria **escritos como los escribe la fuente**,
no como los tenés en tu catálogo. La misma bolsa puede venir un día como *NYSE* y
otro como *New York Stock Exchange*; el mismo sector puede venir en inglés en un
activo y en castellano en otro. Esta pantalla es donde se resuelve ese desajuste
de una vez y para siempre.

## Cómo entra un nombre nuevo al catálogo

Cada vez que autocompletás un activo desde la fuente o importás un lote de
activos, el sistema tiene que convertir cada texto que recibe en una entrada de
tu catálogo. Lo hace en tres pasos, y se queda con el primero que funcione:

| Paso | Qué busca | Resultado |
|---|---|---|
| 1 | Un **alias** ya registrado para ese texto exacto | Usa la entidad a la que el alias apunta. Nada nuevo se crea. |
| 2 | Una entidad del catálogo que se llame **igual** | La usa, y de paso registra el alias para la próxima vez. |
| 3 | Nada de lo anterior | **Crea una entidad nueva** con ese texto como nombre, y registra el alias. |

El paso 2 ignora mayúsculas y minúsculas: *Technology* y *technology* se
consideran el mismo nombre. Pero **solo** eso. Cualquier otra diferencia —una
traducción, una abreviatura, un punto de más— cae en el paso 3.

## Qué pasa con un alias sin mapear

Que el sistema no falla ni te avisa: crea una entidad nueva y sigue. El costo no
se ve en el momento, se ve después. Terminás con *Technology* y *Tecnología* como
dos sectores distintos, cada uno con la mitad de los activos. Y como los
agregados de grupo del [pipeline](/manual/conceptos-pipeline) se calculan por
sector, mercado, industria, país y tipo de instrumento, un catálogo partido
produce **grupos partidos**: dos series de tendencia sectorial flacas en lugar de
una robusta, y filtros de estrategia que dejan afuera medio universo sin que se
note.

Mapear alias es, entonces, mantener limpio el insumo de todo lo que agrupa.

## La pantalla

Arriba, una solapa por cada tipo de entidad que admite alias: **País**,
**Mercado**, **Tipo de instrumento**, **Sector** e **Industria**. Cada solapa es
un mundo aparte: el texto *Energy* como sector y el texto *Energy* como industria
son dos alias independientes y no se pisan.

Debajo, el catálogo completo de esa solapa aparece **dos veces**:

| Columna | Para qué |
|---|---|
| **Origen — arrastrá** | La entidad que querés eliminar. Es la que agarrás. |
| **Destino — soltá aquí** | La entidad que querés conservar. Es la canónica. |

En la columna de destino, algunas entidades muestran un globito con un número:
es la **cantidad de alias acumulados** que hoy apuntan a esa entidad. Un número
alto es buena señal — significa que esa entrada ya absorbió varias formas de
escribir lo mismo.

## Fusionar dos entidades

Arrastrás la entidad duplicada desde la columna izquierda y la soltás sobre la
correcta en la derecha. Aparece un cartel de confirmación con los dos nombres;
recién al confirmar se ejecuta. Soltar una entidad sobre sí misma no hace nada.

La fusión hace tres cosas en un solo paso:

1. **Reasigna** todo lo que dependía de la entidad de origen.
2. **Registra el nombre de la entidad de origen como alias** de la de destino,
   para que la próxima vez que la fuente mande ese texto se resuelva sola.
3. **Elimina** la entidad de origen del catálogo.

Qué se reasigna en cada caso:

| Solapa | Qué se mueve al destino |
|---|---|
| **País** | Los activos de ese país **y los mercados** que lo tenían asignado. |
| **Mercado** | Los activos de ese mercado. |
| **Tipo de instrumento** | Los activos de ese tipo. |
| **Sector** | Los activos de ese sector **y las industrias** que colgaban de él. |
| **Industria** | Los activos de esa industria. |

Si algo falla, la pantalla muestra un aviso rojo con el motivo y no se fusiona
nada.

> **La fusión no se puede deshacer.** La entidad de origen se elimina y sus
> activos quedan mezclados con los del destino: el sistema ya no sabe cuál venía
> de dónde. Fijate bien la dirección antes de soltar — **la izquierda muere, la
> derecha sobrevive**.

## La trampa: los alias del que desaparece no viajan

Esta es la sutileza que más sorprende. La fusión registra **un** alias nuevo: el
nombre de la entidad eliminada. Pero si esa entidad ya tenía alias acumulados
—los del globito—, esos alias **no se trasladan** al destino: quedan huérfanos,
apuntando a algo que ya no existe.

¿Qué se ve después? Que el número del globito no se sumó como esperabas. Y, más
adelante, que la próxima importación que traiga uno de esos nombres viejos
**vuelve a crear el duplicado**, porque el alias huérfano no resuelve y el
sistema cae otra vez en el paso 3.

De ahí la regla práctica: **fusioná siempre en el sentido que conserva la entidad
con el número más alto**. Si igual reaparece un duplicado por un nombre viejo,
fusionalo de nuevo — a la segunda vuelta ese nombre ya queda registrado contra la
entidad correcta.

## Después de fusionar

> **Revisá los filtros de estrategia que mencionen la entidad eliminada.** Un
> filtro del tipo "sector = *Tecnología*" apunta a una entrada puntual del
> catálogo; si esa entrada fue la que se eliminó, el filtro deja de seleccionar
> activos y la estrategia se queda sin universo. Reapuntalo a la entidad que
> sobrevivió.

> **La historia ya calculada no se rehace sola.** Los agregados de grupo y los
> rankings guardados se calcularon con la agrupación anterior. Para que la
> historia refleje el catálogo fusionado hace falta un **recálculo completo**;
> una actualización incremental solo arregla las fechas nuevas. El detalle de la
> diferencia está en [Cómo se calcula todo](/manual/conceptos-pipeline).

El momento natural para pasar por esta pantalla es **después de importar un lote
de activos nuevos** y antes de pedir el recálculo completo que de todos modos ese
lote necesita: así una sola corrida deja el catálogo y la historia consistentes.
