---
slug: actualizacion-de-fundamentales
title: Actualización de fundamentales
chapter: 6. Datos de Mercado
order: 620
roles: admin
page: /admin/fundamental-update
---

El equivalente de [Actualización de precios](/manual/actualizacion-de-precios),
pero para los **datos de balance**: ingresos, ganancia bruta, resultado
operativo, resultado neto, deuda, patrimonio, acciones en circulación. De ahí
salen el P/E, el P/B, los márgenes, el ROIC y el resto de los ratios que usan
las señales fundamentales.

La diferencia central con los precios está en el ritmo: **los balances se
publican una vez por trimestre**. No tiene sentido salir a buscarlos todos los
días, así que el sistema los considera vigentes durante un tiempo largo y solo
los vuelve a descargar cuando se vencen.

## Cuándo entrar acá

- Una empresa **acaba de publicar** su balance y no querés esperar al próximo
  ciclo de refresco.
- Un activo muestra ratios en blanco en la solapa «Fundamentales» de
  [Análisis de Activo](/manual/analisis-de-activo).
- Un ratio quedó en un valor absurdo y sospechás que la fuente entregó datos
  incompletos.
- Configuraste recién la fuente de fundamentales de un activo.

> **Solo aparecen los activos con fuente de fundamentales configurada.** Los
> índices, los sintéticos y las conversiones de moneda no tienen balance, así
> que no figuran en esta lista y ningún botón de esta pantalla los toca.

---

## Cada cuánto se refresca solo

La actualización global —la que corre de noche junto con los precios y la que
se lanza desde el Centro de Datos— **no descarga todo cada vez**. Solo va a
buscar el balance de un activo si:

- nunca se le descargó nada, o
- el último intento terminó en error, o
- pasaron más de **90 días** desde la última descarga exitosa.

Los demás se dan por vigentes y se saltean. Ese es exactamente el hueco que
llena esta pantalla: **todos sus botones fuerzan la descarga**, esté vencida o
no. Si una empresa presentó resultados ayer y su último refresco fue hace un
mes, la corrida automática no la va a tocar durante dos meses más — acá la
actualizás en el momento.

---

## La tabla

| Columna | Qué dice |
|---|---|
| **Ticker** / **Nombre** | El activo. |
| **Último intento** | Cuándo se intentó descargar por última vez. Con el criterio de los 90 días, esta fecha te dice cuánto le falta para vencerse. |
| **Resultado** | **Éxito** en verde, **Error** en rojo, **—** en gris si nunca se intentó. |
| **Detalle error** | El motivo de la falla. Lo más común es que la fuente no publique trimestrales para ese ticker. |
| **Último indicador** / **Resultado indicador** / **Detalle error indicador** | Cómo salió el recálculo de ratios posterior a la descarga. Puede fallar aunque la descarga haya andado bien. |

Se ordena y filtra como el resto de las tablas del sistema. Los dos botones que
operan sobre una selección quedan deshabilitados hasta que marques al menos una
fila.

---

## Los botones

| Botón | Qué hace exactamente | Cuánto tarda |
|---|---|---|
| **Actualizar seleccionados** | Descarga los trimestrales de los activos marcados **ignorando el criterio de vigencia** y recalcula sus ratios actuales. | Segundos por activo. **Sin barra de progreso**: la pantalla espera hasta terminar, así que conviene ir de a pocos activos. |
| **Reintentar fallidos** | Reintenta **todos** los activos cuyo resultado sea *Error*, sin importar la selección. El botón de después de corregir un ticker o una fuente. | Barra de progreso. Proporcional a la cantidad de fallidos. |
| **Redescargar completo (seleccionados)** | Borra el historial trimestral de los activos marcados, lo baja entero de nuevo y **reconstruye desde cero toda la historia de ratios** de esos activos. Pide confirmación. | Barra de progreso. Es **la operación más pesada de la pantalla**. |
| **Limpiar log** | Vacía el registro de la tabla. **No borra ningún dato de balance.** | Instantáneo. |

### Cuál usar

- Salió un balance nuevo → **Actualizar seleccionados**.
- Arreglaste tickers o fuentes mal configuradas → **Reintentar fallidos**.
- Los trimestres guardados están corruptos o incompletos, o la fuente corrigió
  hacia atrás una cifra vieja → **Redescargar completo**, el único que no
  reutiliza nada de lo que ya estaba.

> **«Redescargar completo» reemplaza el historial trimestral.** El borrado
> ocurre junto con la descarga, así que un fallo de la fuente no te deja sin
> datos. Aun así es destructivo y lento: usalo sobre una selección chica y
> puntual, nunca como rutina.

---

## Dos corridas a la vez

La pantalla **impide lanzar dos veces «Reintentar fallidos»**: si ya hay una
corrida en marcha te avisa con *«Ya hay una actualización en curso»* y no
arranca otra.

> **La protección va más allá de esta pantalla.** Los tres botones de
> actualización comparten un candado con las demás operaciones pesadas del
> sistema: los botones de precios, el Centro de Datos y la corrida nocturna
> automática. Si alguna de ellas ya está en marcha, la actualización no
> arranca y te avisa con *«Hay otra actualización pesada en curso (precios,
> fundamentales o Centro de Datos). Esperá a que termine»*. Como todas
> escriben sobre los mismos ratios, una sola corre a la vez.

---

## Qué hacer después

Los ratios del activo se recalculan solos como parte de la descarga: apenas
termina, la solapa «Fundamentales» de
[Análisis de Activo](/manual/analisis-de-activo) ya muestra los valores nuevos.

Lo que **no** se actualiza son las señales y las estrategias que usan esos
ratios. Si tus señales fundamentales alimentan un ranking, hace falta correr el
pipeline de señales y estrategias desde el Centro de Datos para que el cambio
se refleje en el
[Screener de señales](/manual/screener-de-senales). El día a día lo resuelve la
corrida nocturna; si necesitás verlo ya, lanzalo a mano. La distinción entre
actualización incremental y recálculo completo está explicada en
[Cómo se calcula todo](/manual/conceptos-pipeline).

> **«Limpiar log» tiene un efecto secundario.** Al vaciar el registro, los
> activos pierden la marca de «descargado hace poco» y quedan tratados como
> vencidos: la próxima corrida global va a redescargar los balances de todos.
> No rompe nada, pero convierte un refresco rápido en uno largo.
