---
slug: primeros-pasos
title: Primeros pasos
chapter: 1. Introducción
order: 110
roles: invitado
---

## Iniciar sesión

La aplicación pide usuario y contraseña antes de mostrar cualquier cosa, con
una excepción: la página **Acerca de**, que es pública — la pantalla de inicio
de sesión tiene un enlace para verla. No hay registro abierto: las cuentas las
crea un administrador.

**El nombre de usuario no distingue mayúsculas de minúsculas** — `Ana`, `ana` y
`ANA` entran a la misma cuenta. La contraseña sí las distingue.

Si algo falla, el mensaje te dice exactamente qué pasó:

| Mensaje | Qué significa |
|---|---|
| *Ingresá usuario y contraseña* | Quedó un campo vacío. |
| *Usuario o contraseña incorrectos* | Alguno de los dos está mal. No se aclara cuál, a propósito. |
| *Usuario inactivo* | La cuenta existe pero fue desactivada. Pedile a un administrador que la reactive. |
| *No se pudo conectar a la base de datos* | Problema del servidor, no tuyo. Esperá unos segundos y reintentá; si persiste, avisale a un administrador. |

Al entrar caés directamente en [Análisis de Activo](/manual/analisis-de-activo),
que es la pantalla principal.

## Cambiar tu contraseña

**Las contraseñas las cambia un administrador**, desde la pantalla de Usuarios.
No hay una opción de "cambiar mi contraseña" en tu propio menú.

Si necesitás cambiar la tuya, pedísela a un administrador. Si vos sos el
administrador, lo hacés desde **Administración → Usuarios**: editás el usuario
y escribís la contraseña nueva. Dejar ese campo vacío conserva la que ya tenía,
así que podés editar el rol o el estado de una cuenta sin tocarle la clave.

> **En una instalación nueva** existe un único usuario administrador con
> contraseña por defecto. Cambiala apenas entres por primera vez: mientras siga
> siendo la de fábrica, cualquiera que conozca el sistema puede entrar.

## Cerrar sesión

Desde el menú con tu nombre de usuario, arriba a la derecha. La sesión no se
recuerda entre visitas: cerrar el navegador también te desloguea.

## Qué hacer los primeros días

1. **Recorré [Análisis de Activo](/manual/analisis-de-activo)** con un activo
   que conozcas bien. Es la pantalla donde más tiempo vas a pasar y la que
   mejor te va a mostrar qué datos tiene el sistema.
2. **Leé [Cómo se calcula todo](/manual/conceptos-pipeline)**. Son diez minutos
   y sin eso varias pantallas parecen arbitrarias.
3. **Mirá el [Screener de Señales](/manual/screener-de-senales)** con alguna
   estrategia ya cargada, para ver el ranking en acción.
4. Recién después conviene meterse a crear señales y estrategias propias.

> **Si los datos se ven desactualizados**, no es algo que arregles vos: la
> actualización de precios y fundamentales corre automáticamente todos los
> días. Si notás que faltan días, avisale a un administrador.
