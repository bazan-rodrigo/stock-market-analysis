---
slug: actualizacion-de-precios
title: Actualización de precios
chapter: 6. Datos de Mercado
order: 610
roles: admin
page: /prices
---

Dos cosas en una pantalla: el **registro de cómo le fue a cada activo** en su
última descarga de precios, y los botones para **forzar** una actualización
sobre los activos que elijas.

> **La actualización diaria corre sola.** Si el programador de tareas está
> encendido, todas las noches se descargan los precios de todos los activos, se
> recalculan indicadores y ratios, y se corre el pipeline de señales y
> estrategias. Esta pantalla **no reemplaza** ese proceso: sirve para arreglar
> lo que quedó mal y para no esperar hasta la noche cuando necesitás un activo
> puntual al día.

## Cuándo entrar acá

- Un activo aparece atrasado en el
  [Visualizador de precios](/manual/visualizador-de-precios).
- Acabás de dar de alta un activo y querés su historia ya, sin esperar.
- Corregiste un ticker mal escrito y hay que reintentar la descarga.
- La fuente corrigió retroactivamente una serie (un split, un dividendo
  reajustado) y los precios viejos guardados quedaron mal.

---

## La tabla

Una fila por activo, siempre presente aunque nunca se lo haya intentado
descargar (en ese caso los campos muestran «—»).

| Columna | Qué dice |
|---|---|
| **Ticker** / **Nombre** | El activo. |
| **Último intento** | Cuándo se intentó descargar por última vez. |
| **Resultado** | **Éxito** en verde, **Error** en rojo. |
| **Detalle error** | El motivo exacto de la falla. Es lo primero que hay que leer: casi siempre es un ticker que la fuente no reconoce — los errores típicos de cada fuente están en [Fuentes de datos](/manual/fuentes-de-datos). |
| **Último indicador** / **Resultado indicador** / **Detalle error indicador** | Lo mismo, pero para el recálculo de indicadores que sigue a la descarga. Un activo puede tener el precio bien y los indicadores mal. |

Las columnas se ordenan y filtran como en el resto del sistema. Filtrar
**Resultado** por `Error` es la forma rápida de ver el daño acumulado.

A la izquierda de cada fila hay una casilla de selección: tres de los cuatro
botones necesitan que marques al menos un activo, y hasta entonces están
deshabilitados.

---

## Los botones

| Botón | Qué hace exactamente | Cuánto tarda |
|---|---|---|
| **Actualizar seleccionados** | Actualización **incremental** de los activos marcados: descarga desde el último día que ya tenía y recalcula los indicadores y ratios vigentes de ese activo. Si el activo no tenía ningún precio, baja la historia completa y además reconstruye toda su historia de indicadores. | Segundos por activo. **No muestra barra de progreso**: la pantalla queda esperando hasta que termina, así que conviene usarlo con pocos activos por vez. |
| **Recalcular seleccionados (completo)** | **No descarga nada.** Rehace desde cero los indicadores técnicos de los activos marcados —valores vigentes e historia completa— a partir de los precios ya guardados. | Muestra barra de progreso. Depende de cuánta historia tenga cada activo. |
| **Reintentar fallidos** | Reintenta la actualización incremental de **todos** los activos cuyo resultado sea *Error*, sin importar qué tengas seleccionado. Es el botón de después de arreglar tickers. | Barra de progreso. Proporcional a la cantidad de fallidos. |
| **Redescargar completo (seleccionados)** | Borra la historia de precios de los activos marcados, la baja entera de nuevo desde la fuente y rehace por completo sus indicadores técnicos **y** sus ratios fundamentales. Pide confirmación en un cartel. | Barra de progreso. Es **la operación más pesada de la pantalla** y puede llevar varios minutos aun con pocos activos. |
| **Limpiar log** | Vacía el registro de la tabla. **No borra ningún precio.** | Instantáneo. |

### Cuál usar

- El precio de un activo está desactualizado → **Actualizar seleccionados**.
- El precio está bien pero el indicador quedó mal o incompleto → **Recalcular
  seleccionados (completo)**, sin volver a descargar.
- La fuente corrigió la serie histórica hacia atrás → **Redescargar completo**,
  que es el único que no confía en nada de lo guardado.

> **«Redescargar completo» borra antes de bajar.** El borrado ocurre junto con
> la descarga, así que si la fuente falla no perdés lo que tenías. Aun así, es
> una operación destructiva y larga: usala sobre una selección chica y puntual,
> nunca como forma habitual de actualizar.

---

## Dos corridas a la vez

El sistema admite **una sola operación pesada por vez**, y esa restricción es
compartida entre esta pantalla, el Centro de Datos y la corrida nocturna
automática. Si lanzás algo mientras otra cosa está corriendo, la pantalla te
avisa con *«Hay otra operación pesada en curso. Esperá a que termine antes de
lanzar esta»* y **no arranca nada** — no hay riesgo de que dos procesos se
pisen escribiendo los mismos datos.

Al revés también vale: si dejás corriendo una redescarga larga acá, la
actualización nocturna de esa noche se saltea. Conviene lanzar las operaciones
grandes con margen respecto del horario programado.

---

## Qué hacer después

Actualizar precios **no actualiza señales ni estrategias**. Los indicadores del
activo sí se recalculan solos, pero el ranking depende de todos los activos de
cada fecha a la vez, así que se maneja aparte:

- Actualizaste precios de activos que **ya estaban** en el sistema: no hace
  falta nada más, la corrida nocturna incorpora el cambio.
- Incorporaste un activo **nuevo** y querés que aparezca en la historia de
  señales y rankings: hace falta un **recálculo completo** de señales y
  estrategias desde el [Centro de Datos](/manual/centro-de-datos). Una
  actualización incremental no alcanza — el motivo está en
  [Cómo se calcula todo](/manual/conceptos-pipeline).

> **«Limpiar log» tiene un efecto secundario.** Al vaciar el registro, los
> activos pierden la marca de «ya descargado alguna vez». La opción *Solo
> activos nuevos* del Centro de Datos los va a tratar a todos como nuevos y
> les descargará la historia completa. Limpialo solo cuando la tabla esté tan
> sucia que no se pueda leer.
