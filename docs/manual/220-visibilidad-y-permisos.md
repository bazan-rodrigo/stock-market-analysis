---
slug: visibilidad-y-permisos
title: Visibilidad y permisos
chapter: 2. Conceptos centrales
order: 220
roles: analista
---

Cuando varios analistas trabajan sobre la misma base, hace falta poder probar
ideas sin ensuciarle las pantallas a los demás, y a la vez compartir lo que ya
está maduro. Eso lo resuelven dos atributos que tienen **las señales, las
estrategias y las carteras**: quién es su dueño y si es pública o privada.

Son dos cosas independientes y conviene no confundirlas:

- **La visibilidad** (pública / privada) decide **quién la ve**.
- **El dueño** decide **quién la puede modificar**.

Publicar algo no cambia su dueño: sigue siendo tuyo, solo que ahora lo ven todos.

> El resto de las definiciones del sistema —activos, indicadores, tablas de
> referencia, configuración— **no tiene dueño ni visibilidad**: son de
> administración y las gestiona un administrador. Este modelo aplica únicamente a
> las tres cosas que un analista crea.

## Quién ve qué, quién edita qué

| | Pública | Privada |
|---|---|---|
| **Su dueño** | Ve y edita | Ve y edita |
| **Otro analista** | Ve, no edita | **No la ve** |
| **Administrador** | Ve y edita | Ve y edita |

Editar incluye las tres operaciones que modifican la definición: **modificarla,
borrarla y publicarla o despublicarla**. Si no la podés editar, la pantalla te la
muestra en modo lectura.

Hay un caso particular: las definiciones **sin dueño**. Son las que se importaron
o se crearon antes de que existiera este modelo. Las ve cualquiera si son
públicas, pero **solo un administrador puede editarlas**.

Lo que creás nace **privado** salvo que marques lo contrario, y la importación
sigue la misma regla: los paquetes traen la visibilidad indicada en el propio
archivo y, si no la indican, las definiciones entran como **privadas**. Publicar
es siempre un paso explícito — con la columna del archivo o desde la pantalla.

## La regla de las referencias

Esta es la parte sutil, y la que más sorprende la primera vez.

Una estrategia no vive sola: **referencia señales**, tanto en sus componentes
ponderados como en los operandos de su filtro de elegibilidad. Y una cartera
derivada de una estrategia **referencia esa estrategia**. Ahí aparece un
riesgo: si una estrategia pública pudiera usar una señal privada, cualquiera que
abriera esa estrategia estaría viendo —indirectamente— una definición que su
dueño decidió no compartir.

Por eso rige esta regla:

| Si la estrategia es… | Puede referenciar… |
|---|---|
| **Pública** | Solo señales **públicas**. |
| **Privada** | Señales públicas **más las privadas propias**. |

En ningún caso podés usar la señal privada de otro usuario: no la ves, así que no
existe para vos.

La consecuencia práctica es directa: **para publicar una estrategia, antes tenés
que publicar todas las señales que usa**. Si intentás publicarla con una señal
privada adentro, el sistema no te deja y te dice cuál es.

La misma regla corre un nivel más arriba: **una cartera pública no puede derivar
de una estrategia privada** — cualquiera que la viera podría inferir la
composición de una estrategia que su dueño no compartió. Si intentás crearla
pública, o publicarla después, el sistema te pide publicar la estrategia
primero, o dejar la cartera privada.

### Y al revés: no siempre podés despublicar

La misma regla se aplica en sentido inverso. Si una señal tuya ya es pública y la
está usando una estrategia pública, o una estrategia de otro usuario,
**despublicarla los dejaría apuntando a algo que sus dueños ya no ven**. El
sistema lo impide y te lista qué la está usando, para que primero la saques de
ahí.

Sí podés despublicar sin problema si lo único que la usa son definiciones
**privadas tuyas**: ahí no se rompe nada, porque el único que las ve sos vos.

> Tampoco se puede **borrar** una señal que alguna estrategia esté usando, sea de
> quien sea. Primero hay que quitarla de esa estrategia.

## Lo privado no se deja de calcular

Este es el punto que más confusión genera, así que conviene decirlo sin vueltas:

**El cálculo diario procesa TODAS las definiciones, sin mirar la visibilidad.**
Las señales privadas se calculan igual que las públicas, y las estrategias
privadas generan su ranking todas las noches como cualquier otra.

Lo privado es **la definición y la pantalla**, no los valores calculados. Es
decir: lo que otro usuario no ve es la fórmula, los parámetros y la fila en las
pantallas de configuración. El cómputo ocurre igual.

De ahí salen dos conclusiones prácticas:

- **Marcar algo como privado no ahorra tiempo de cálculo.** Si una señal ya no te
  sirve, no la hagas privada: borrala.
- **Cuando lo publiques, ya va a tener toda su historia calculada.** No hay que
  esperar ni recalcular nada por el solo hecho de publicar: publicar no cambia
  ninguna definición, y el
  [recálculo completo](/manual/conceptos-pipeline) solo hace falta cuando
  cambiaste la fórmula.

## Nota sobre el administrador y el acceso público

Un **administrador** ve y edita todo, sin importar dueño ni visibilidad. Es el
único que puede tocar las definiciones sin dueño.

Si la instalación tiene habilitado el **acceso público** —el perfil invitado
descrito en [Qué es esta aplicación](/manual/introduccion)—, ese visitante opera
con permisos de administrador pero **no tiene un usuario propio**. La consecuencia
es que puede ver y editar todo, pero **lo que crea queda sin dueño**, y por lo
tanto después solo lo puede editar un administrador. Si vas a crear señales o
estrategias que después quieras seguir manteniendo, entrá con tu usuario.
