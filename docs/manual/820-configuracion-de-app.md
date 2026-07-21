---
slug: configuracion-de-app
title: Configuración de la aplicación
chapter: 8. Administración
order: 820
roles: admin
page: /admin/app-settings
---

Ajustes globales del sistema. Hoy tiene uno solo, pero es de los que cambian
quién puede entrar a la aplicación.

## Acceso sin login

Un interruptor: **Habilitado** o **Deshabilitado**.

Con el acceso sin login **habilitado**, cualquiera que llegue a la dirección de
la aplicación puede navegarla sin usuario ni contraseña. Entra como
**invitado** con acceso completo: navega las mismas pantallas y menús que un
administrador, incluida la administración. La única diferencia visible es que,
en lugar del nombre de usuario, arriba a la derecha dice **Invitado** junto a
un enlace para iniciar sesión.

Con el acceso **deshabilitado**, la aplicación pide usuario y contraseña antes
de mostrar cualquier cosa — salvo la página **Acerca de**, que es la
presentación pública del sitio y se ve siempre.

> **Este es un ajuste de seguridad.** Habilitarlo le da a cualquiera que
> conozca la dirección acceso completo al sistema, con los mismos permisos que
> un administrador: no solo ve todos los datos, también puede modificar
> activos, definiciones, usuarios y configuración. Si la aplicación está
> publicada en internet, tenelo muy presente antes de activarlo.

### Qué ve exactamente un invitado

Lo importante es que **el invitado opera con los mismos permisos que un
administrador**: entra a todas las pantallas de configuración y administración,
y puede crear y editar señales, estrategias y carteras. Lo que crea queda sin
dueño: después solo un administrador puede editarlo o borrarlo.

El invitado ve todas las definiciones, incluidas las **privadas** de otros
usuarios: el modo invitado no distingue entre lo público y lo privado. Está
explicado en [Visibilidad y permisos](/manual/visibilidad-y-permisos).

El detalle de qué alcanza cada perfil está en
[Qué es esta aplicación](/manual/introduccion), y lo que ve concretamente el
invitado en [Primeros pasos](/manual/primeros-pasos).

### Cuándo tiene sentido habilitarlo

- La aplicación corre en una red interna donde el control de acceso ya lo
  resuelve otra cosa.
- Querés que un grupo consulte los análisis sin administrar una cuenta para cada
  persona.

Si necesitás distinguir quién hace qué, o que cada quien tenga sus propias
señales y estrategias, dejalo deshabilitado y creá usuarios desde
[Usuarios](/manual/usuarios).

> El cambio tiene efecto de inmediato, sin reiniciar nada.
