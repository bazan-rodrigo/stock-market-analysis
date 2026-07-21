---
slug: gestion-de-activos
title: Gestión de activos
chapter: 5. Activos
order: 500
roles: admin
page: /assets
---

El padrón de activos del sistema: el listado completo, el alta, la edición
—individual y masiva— y la baja. Todo lo demás (precios, indicadores, señales,
ranking, carteras) cuelga de lo que se cargue acá.

Qué es un activo, qué significan sus cinco grupos y por qué la moneda no es un
grupo está explicado en [Activos, sintéticos y grupos](/manual/activos-y-grupos).
Esta página es el **cómo se opera**.

## El listado

La tabla muestra **Ticker**, **Nombre**, **País**, **Mercado**, **Tipo**,
**Moneda**, **Sector**, **Benchmark**, **Fuente precios** y **Fuente fund.**
Cada columna tiene su propio casillero de filtro y se puede ordenar haciendo
clic en el encabezado; con eso resolvés casi cualquier búsqueda sin salir de la
pantalla.

Cuando un dato de catálogo llegó de la fuente externa con un nombre distinto al
que usa el sistema, la celda lo muestra como `Nombre nativo (Canónico: nombre
del sistema)`. Es informativo: el activo está asignado al valor canónico.

Los botones **Sel. todos** / **Desel. todos** operan sobre **todas** las filas
cargadas, no solo sobre la página visible. Tenelo presente antes de aplicar una
acción masiva.

## Alta de un activo

**+ Nuevo activo** abre el formulario. Solo dos campos son obligatorios:

| Campo | Obligatorio | Notas |
|---|---|---|
| **Ticker** | Sí | Se guarda siempre en mayúsculas y no se puede repetir. |
| **Fuente de precios** | Sí | De dónde se descargan las cotizaciones. Elegí **Calculado** si el activo va a ser un [sintético](/manual/activos-sinteticos). |
| **Nombre** | No | Si lo dejás vacío se usa el ticker. |
| **Moneda** | No | Define si al activo le corresponden [conversiones a otra divisa](/manual/activos-en-divisa). |
| **País**, **Mercado**, **Tipo de instrumento**, **Sector**, **Industria** | No | Los grupos. |
| **Benchmark** | No | Buscador por ticker y nombre sobre el resto de los activos. |
| **Fuente de fundamentales** | No | Solo tiene sentido en activos con balances. |

### Autocompletar desde fuente

Con el **Ticker** y la **Fuente de precios** cargados, el botón
**Autocompletar desde fuente** consulta al proveedor y completa nombre, país,
moneda, mercado, tipo de instrumento, sector e industria. Si el ticker no existe
en la fuente, avisa y no completa nada — sirve además como validación previa.

> **El autocompletado escribe en los catálogos en el momento de apretarlo**, sin
> esperar a que guardes. Si el país, mercado, sector o industria que devuelve la
> fuente no existían, los crea y te los lista en el mensaje. Si después cancelás
> el formulario, esos catálogos nuevos quedan igual. Revisá el mensaje: es la
> forma más común de terminar con dos sectores casi iguales.

### Qué pasa al guardar

Al crear un activo nuevo el sistema **arranca la descarga de precios en segundo
plano** (y de fundamentales, si le asignaste fuente). El formulario se cierra
enseguida; la descarga sigue corriendo sola. Además, si el activo tiene moneda y
esa moneda tiene divisores configurados, se le generan las conversiones
correspondientes.

Si el guardado falla, el formulario **queda abierto** con el error arriba, para
que no pierdas lo cargado.

## Editar

Seleccioná **una sola** fila y usá **Editar**. Es el mismo formulario, con los
valores actuales.

> **Cambiar la moneda de un activo borra sus conversiones a divisa y las vuelve
> a generar** con los divisores de la moneda nueva. Es una operación cara si el
> activo tenía varias.

## Edición masiva

Al seleccionar una o más filas aparece la barra de edición masiva: elegís un
**Campo**, un **Nuevo valor**, y **Aplicar a seleccionados**. **Limpiar campo**
hace lo mismo pero dejando el campo vacío en todos los seleccionados.

Los campos habilitados son **Benchmark**, **Mercado**, **País**, **Tipo de
instrumento**, **Moneda**, **Sector**, **Industria** y **Fuente de
fundamentales**. Es la forma rápida de asignar sector a cincuenta activos
recién importados.

> La edición masiva **no** regenera las conversiones a divisa. Si cambiás la
> **Moneda** por esta vía, andá después a
> [Activos en Divisa](/manual/activos-en-divisa) y sincronizá.

## Eliminar

Seleccioná una o más filas y usá **Eliminar**. Aparece una confirmación que
nombra los activos (o la cantidad, si son muchos).

> **Es irreversible y se lleva toda la historia**: precios, indicadores y
> fundamentales del activo, más los sintéticos de conversión que lo tengan como
> base o como divisor. Borrar muchos activos puede tardar varios minutos.

Un activo que está configurado como **benchmark** de otros activos o de un
mercado **no se puede borrar**: el sistema rechaza la operación y te dice quién
lo está usando. Reasigná ese benchmark primero. Si borrás varios de una y alguno
falla, el resto sí se borra y el mensaje detalla cuáles fallaron.

Tampoco se puede borrar un activo que es **componente de un sintético** — un
ratio, un promedio, un índice. Igual que con el benchmark, el sistema rechaza
la operación **antes de tocar nada** y el mensaje nombra qué sintéticos lo
usan: eliminá esos sintéticos, o quitá el componente de la fórmula desde
[Activos sintéticos](/manual/activos-sinteticos), y reintentá. Las
**conversiones de moneda** no cuentan: esas se borran solas junto con su base.
Sí está permitido borrar el componente y su sintético **en la misma
selección**.

## Después de dar de alta, reagrupar o eliminar

Los indicadores de un activo nuevo se completan solos. Las **señales de grupo**,
en cambio, y los **rankings de estrategia** son transversales: incorporar
activos nuevos, cambiarles el sector o el mercado, **o eliminar un activo que
participaba**, desactualiza la historia ya calculada — los rankings de fechas
pasadas se calcularon contándolo. Para que quede consistente hace falta un
**recálculo completo** desde el [Centro de Datos](/manual/centro-de-datos) —
el porqué está en [Cómo se calcula todo](/manual/conceptos-pipeline), y el
detalle de por qué un borrado grande tarda minutos, en
[Deltas, recálculos y borrado masivo](/manual/deltas-y-borrado-masivo).

Para cargar muchos activos de una sola vez, usá
[Importar activos](/manual/importar-activos).
