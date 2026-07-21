---
slug: solucion-de-problemas
title: Solución de problemas
chapter: Apéndices
order: 930
roles: invitado
---

Síntomas frecuentes, su causa más probable y qué hacer. Cada entrada enlaza a la
sección que lo explica en detalle.

---

## Un activo no aparece en el ranking

**Causa más probable: no pasa el filtro de elegibilidad de la estrategia.**

El filtro decide quién participa. Un activo que no lo pasa **no aparece con
puntaje bajo: no aparece en absoluto**. Y un dato faltante nunca cumple una
condición, así que un activo con historia corta queda afuera aunque "debería"
calificar.

Qué hacer: revisá las condiciones del filtro en
[Estrategias — crear y editar](/manual/configuracion-estrategias) y verificá que
el activo tenga calculados los indicadores que el filtro consulta. La referencia
de las reglas está en
[Operadores del filtro](/manual/operadores-del-filtro).

---

## Un activo nuevo no tiene historia de señales

**Es el comportamiento esperado, no una falla.**

Cuando agregás un activo, sus indicadores se completan solos, pero la historia
de señales y rankings **no**: el ranking depende de todos los activos de cada
fecha, así que incorporarlo al pasado obliga a recalcular esas fechas enteras.

Qué hacer: un **recálculo completo** desde el
[Centro de Datos](/manual/centro-de-datos). Está explicado en
[Cómo se calcula todo](/manual/conceptos-pipeline).

---

## Los datos no se actualizan hace días

**Causa más probable: el programador de tareas está apagado.**

Qué hacer: revisá [Scheduler](/manual/scheduler). Si está encendido y
aun así faltan días, mirá el registro de
[Actualización de precios](/manual/actualizacion-de-precios), que muestra,
activo por activo, cómo le fue en el último intento.

---

## El valor de ayer cambió respecto de lo que había visto

**Es intencional.** El precio del día en curso puede cambiar hasta el cierre,
así que toda actualización **recalcula siempre la última fecha** además de
completar los huecos.

Si el cambio es de una fecha vieja, ahí sí hay algo raro: corré
[Verificación de datos](/manual/verificacion-de-datos).

---

## Cambié una señal y los resultados no cambiaron

**Modificar una definición no recalcula lo ya guardado.** Todo lo histórico
sigue calculado con la definición anterior hasta que corras un recálculo
completo.

Es especialmente engañoso al hacer backtest: si ajustás una señal y volvés a
correr el backtest sin recalcular, **estás midiendo la versión vieja**.

Qué hacer: recálculo completo desde el
[Centro de Datos](/manual/centro-de-datos).

---

## El backtest devuelve vacío

Tres causas posibles, en orden de frecuencia:

1. **La estrategia no tiene resultados calculados** en el rango de fechas
   pedido. Verificá en
   [Evolución de Estrategia](/manual/evolucion-de-estrategia) desde cuándo hay
   datos.
2. **El filtro deja afuera a casi todos.** Con muy pocos activos elegibles por
   fecha no se pueden formar los grupos de comparación.
3. **El rango de fechas es más corto que lo que la configuración necesita.**

---

## Un indicador tiene valor en un día que el activo no cotizó

Los indicadores se leen **"al último valor disponible en esa fecha o antes"**.
Eso permite que un indicador semanal o mensual sirva para cualquier día, pero
también hace que un activo que no cotizó arrastre el valor del día anterior.

Para el backtest esto está contemplado: solo se leen fechas con precio propio
del activo. Ver [Backtest de Estrategia](/manual/backtest).

---

## Aparece un ⚠️ al lado de un activo

Significa que la verificación de datos encontró un problema en ese activo. **No
dice cuál.**

Qué hacer: entrá a [Verificación de datos](/manual/verificacion-de-datos) y
mirá el detalle.

> Al revés no vale: **la ausencia de la marca no garantiza que los datos estén
> bien**: puede significar que en la última verificación ese activo salió sin
> hallazgos — o que nadie lo verificó todavía (la verificación no corre sola
> salvo que esté habilitada la corrida semanal).

---

## Los agregados de un sector o industria se ven erráticos

**Causa más probable: el grupo tiene pocos activos.** Un promedio sobre dos o
tres se mueve con cualquier cosa.

Qué hacer: en el [Mapa de Tendencia](/manual/mapa-de-tendencia), mirá la columna
con la cantidad de activos del grupo antes de sacar conclusiones. Como criterio
general, [Sectores](/manual/sectores) da agregados más estables que
[Industrias](/manual/industrias).

---

## No puedo editar una señal o estrategia que veo

**Ver y editar son permisos distintos.** Podés ver todo lo público, pero editar
solo lo propio (o cualquier cosa, si sos administrador).

Ver [Visibilidad y permisos](/manual/visibilidad-y-permisos).

---

## No puedo hacer pública una estrategia

**Una definición pública solo puede referenciar señales públicas.** Si tu
estrategia usa alguna señal privada, primero tenés que publicar esas señales.

Ver [Visibilidad y permisos](/manual/visibilidad-y-permisos).

---

## "Hay otra operación en curso" / "Hay otra operación pesada en curso"

Las operaciones pesadas admiten **una sola a la vez en todo el sistema**, no una
por usuario. Puede estar corriendo otra persona, o la actualización automática.

Qué hacer: esperá y reintentá. Si sospechás que quedó trabada, la consulta
inicial de la [Consola SQL](/manual/consola-sql) muestra qué se está ejecutando
contra la base en este momento.

---

## La aplicación quedó lenta

Revisá, en este orden:

1. **Si hay una operación pesada corriendo** — [Centro de Datos](/manual/centro-de-datos).
2. **Si el disco creció mucho** — [Limpieza de datos](/manual/limpieza-de-datos)
   mide el espacio, y **Recuperar espacio** suele resolverlo sin borrar nada.
3. **Qué se está ejecutando contra la base** — [Consola SQL](/manual/consola-sql).
