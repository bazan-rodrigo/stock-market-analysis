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
**invitado**: ve las pantallas de análisis y los datos de mercado, y el menú de
administración le queda oculto.

Con el acceso **deshabilitado**, la aplicación pide usuario y contraseña antes
de mostrar cualquier cosa.

> **Este es un ajuste de seguridad.** Habilitarlo hace que todos los datos de
> análisis del sistema queden visibles para cualquiera que conozca la
> dirección. Si la aplicación está publicada en internet, tenelo presente antes
> de activarlo.

### Qué ve exactamente un invitado

Lo importante es que **el menú de administración se oculta, pero eso es una
decisión de la interfaz, no un permiso sobre los datos**. El invitado tampoco
puede crear señales, estrategias ni carteras, porque no tiene un usuario propio
al que atribuirle esas definiciones.

Las definiciones **privadas** de otros usuarios no se le muestran: ve
únicamente lo público. Está explicado en
[Visibilidad y permisos](/manual/visibilidad-y-permisos).

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
