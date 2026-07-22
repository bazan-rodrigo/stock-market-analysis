---
slug: usuarios
title: Usuarios
chapter: 8. Administración
order: 800
roles: admin
page: /admin/users
---

Acá se crean las cuentas, se les asigna rol, se activan o desactivan y se les
cambia la contraseña. Es la única pantalla desde donde se administran usuarios:
no hay registro público ni autogestión de contraseña (ver
[Primeros pasos](/manual/primeros-pasos)).

Solo un administrador puede abrirla. A un analista le muestra «Acceso denegado».

## La tabla

| Columna | Qué muestra |
|---|---|
| **Usuario** | El nombre con el que inicia sesión. |
| **Rol** | `admin` o `analyst`. |
| **Activo** | **Sí** / **No**. Un **No** no puede iniciar sesión. |
| **Creado** | Fecha de alta de la cuenta. |

La tabla se ordena y se filtra desde los encabezados. Los botones **Editar** y
**Eliminar** trabajan sobre lo que tengas tildado: **Editar** se habilita con
una sola fila seleccionada; **Eliminar**, con una o más. **Sel. todos** /
**Desel. todos** son atajos de selección.

## Los dos roles

Todo el control de acceso del sistema se reduce a estos dos roles: no hay
permisos por pantalla ni grupos intermedios.

| Rol | Qué puede hacer |
|---|---|
| **Admin** | Todo. Los menús **Activos** y **Administración** aparecen solo en el suyo, y **Datos de Mercado** y **Configuración** los ve completos. Además puede editar señales, estrategias y carteras de cualquier persona. |
| **Analista** | Consulta de análisis y datos de mercado, y creación de **señales, estrategias y carteras propias**: su menú **Configuración** se reduce a esas tres entradas, y **Datos de Mercado**, a un enlace directo al Visualizador de precios. No ve **Activos** ni **Administración**. |

Un analista ve las definiciones **públicas** más las **propias**, y solo edita
las propias. El detalle de esa mecánica está en
[Visibilidad y permisos](/manual/visibilidad-y-permisos).

> **Cambiar el rol no requiere volver a iniciar sesión: el permiso cambia en el
> acto.** Si degradás a alguien de admin a analista mientras está trabajando,
> las pantallas de administración le pasan a mostrar «Acceso denegado»
> enseguida. El **menú**, en cambio, se arma al cargar la página y le queda
> como estaba: los enlaces viejos siguen ahí hasta que recargue el navegador o
> vuelva a iniciar sesión, aunque ya no lo lleven a ningún lado.

## Alta de un usuario

**+ Nuevo** abre el formulario.

| Campo | Detalle |
|---|---|
| **Usuario** | Obligatorio. Se le quitan los espacios de los extremos. |
| **Rol** | Viene preseleccionado en **Analista**. |
| **Contraseña (dejar vacío para no cambiar)** | **Obligatoria en el alta.** En la edición, vacío = no se toca. |
| **Activo** | Ver la advertencia de abajo. |

> **En el alta, el interruptor Activo no tiene efecto: la cuenta nace siempre
> activa.** Si querés dejarla creada pero todavía sin acceso, creala y
> después editala para desactivarla.

El nombre de usuario no se puede repetir. Si ya existe, el guardado falla y el
error aparece **dentro del formulario, que queda abierto** con todo lo que
cargaste — no perdés nada, corregís el nombre y volvés a guardar.

> **Dos nombres que difieran solo en mayúsculas cuentan como el mismo**
> (`Ana` y `ana`). El inicio de sesión no distingue mayúsculas de minúsculas,
> así que ese par sería ambiguo desde la pantalla de login: el sistema lo
> rechaza al guardar y te avisa. Sí podés corregirle las mayúsculas al nombre
> de un usuario existente (`ana` → `Ana`): ahí no hay dos cuentas, hay una.

El sistema no exige longitud mínima ni complejidad de contraseña: el criterio
lo ponés vos.

## Cambiar una contraseña

Seleccionás la fila, **Editar**, escribís la contraseña nueva y guardás. La
persona la usa en su próximo inicio de sesión; no hay aviso automático, así que
avisale vos.

> **El campo Contraseña siempre se abre vacío**, incluso en cuentas que
> obviamente tienen una. Eso no significa que no tenga: las contraseñas no se
> pueden leer, ni siquiera desde acá. **Dejarlo vacío conserva la contraseña
> actual.**

Esa es justamente la razón por la que podés entrar a editar el rol o el estado
de una cuenta sin tocarle la clave: mientras no escribas nada en ese campo, la
contraseña queda intacta. Y al revés: no existe forma de "recuperar" una
contraseña olvidada, solo de reemplazarla por una nueva.

## Activar y desactivar

El interruptor **Activo** en la edición es la forma prevista de sacarle el
acceso a alguien sin borrar nada. Al intentar entrar recibe *Usuario inactivo.
Contactá al administrador*, y reactivarla lo devuelve todo tal cual estaba:
mismas señales, estrategias y carteras, misma contraseña.

Es lo que conviene usar para una licencia, una baja temporal o una salida cuyo
trabajo querés conservar.

> **Desactivar no expulsa a quien ya está adentro.** El control corre al
> iniciar sesión: una persona con la sesión abierta sigue navegando hasta que
> la cierre o cierre el navegador. Si necesitás cortar el acceso de inmediato,
> desactivala y cambiale la contraseña, y verificá que haya cerrado sesión.

## Eliminar

**Eliminar** pide confirmación mostrándote a quién vas a borrar (los nombres,
si son cinco o menos). Podés borrar varios de una vez; si alguno falla, el
mensaje te dice cuántos se eliminaron y qué error dio el resto.

> **Es irreversible, y arrastra consecuencias sobre el trabajo de esa persona.**
> Sus señales, estrategias, carteras y corridas de backtest **no se borran**,
> pero **quedan sin dueño**. En la práctica eso significa que pasan a ser
> editables solo por administradores, y que las que eran privadas dejan de
> tener quien las vea además del admin. Es un cambio que no se deshace
> volviendo a crear un usuario con el mismo nombre: sería una cuenta nueva.

Por eso, ante la duda, **desactivar es casi siempre mejor que eliminar**.
Dejá el borrado para cuentas de prueba o creadas por error.

> **El último administrador activo está protegido.** La pantalla no deja
> desactivarlo, pasarlo a analista ni eliminarlo: el guardado falla con el
> aviso de que el sistema quedaría sin ninguna cuenta que pueda administrar.
> Para tocar esa cuenta, primero activá o promové a otro administrador. Ojo:
> un admin **desactivado no cuenta** como respaldo — tiene que haber otro
> admin **activo**. Y la protección no sabe de contraseñas: que quede un
> admin activo cuya clave nadie recuerda te deja igual de afuera.
