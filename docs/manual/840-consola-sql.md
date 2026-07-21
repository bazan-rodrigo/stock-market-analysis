---
slug: consola-sql
title: Consola SQL
chapter: 8. Administración
order: 840
roles: admin
page: /admin/sql
---

Ejecuta consultas directamente contra la base de datos, sin pasar por ninguna
pantalla ni validación de la aplicación.

> **Esta pantalla puede modificar y destruir datos.** No es de solo lectura:
> acepta también sentencias de modificación y borrado. Nada de lo que hagas acá
> pasa por las reglas de negocio del sistema. Si buscás explorar datos sin
> riesgo, usá el [Explorador de datos](/manual/explorador-de-datos).

## Cómo funciona

Escribís la consulta en el editor y apretás **Ejecutar**. Lo que pasa después
depende del tipo de sentencia:

| Tipo de sentencia | Qué pasa |
|---|---|
| **Lectura** (`SELECT`, `SHOW`, `DESC`, y `WITH` o `EXPLAIN` que no envuelvan una escritura) | Se muestran los resultados en una grilla y la operación se cierra sola. |
| **Cualquier otra** (modificación, borrado, alta) | Se ejecuta pero **queda pendiente**: te dice cuántas filas afectó y espera tu decisión. |

Un `WITH` o un `EXPLAIN` que contenga una sentencia de modificación se trata
como modificación: puede ejecutar el cambio de verdad, así que queda pendiente
de tu **Commit** o **Rollback** como cualquier otra.

Cuando hay una modificación pendiente se habilitan dos botones:

- **Commit** — confirma los cambios. A partir de acá son permanentes.
- **Rollback** — los descarta. La base queda como estaba.

Esa confirmación en dos pasos es la única red de seguridad de la pantalla:
**te deja ver cuántas filas tocaste antes de decidir**. Un borrado que dice
"18.000 filas afectadas" cuando esperabas 3 es tu señal para apretar
**Rollback**.

> **Con una modificación pendiente podés seguir ejecutando consultas de
> lectura.** Corren dentro de la misma operación, así que ven el resultado del
> cambio todavía sin confirmar: es la forma de revisar exactamente qué tocaste
> antes de decidir. **Commit** y **Rollback** siguen disponibles mientras tanto.

## La consulta que aparece al entrar

El editor arranca con una consulta ya escrita que muestra **qué se está
ejecutando contra la base en este momento**: quién, desde cuándo y qué
sentencia. Es la herramienta de diagnóstico cuando la aplicación está lenta o
una actualización parece colgada — te dice si hay algo bloqueando.

## Límites y detalles

**Se muestran hasta 5.000 filas.** Si tu consulta devuelve más, ves las
primeras 5.000 y un indicador de que hay más. El resto no se pierde: acotá la
consulta.

**Exportar CSV** vuelve a ejecutar la consulta que está escrita en el editor y
baja el resultado completo (acá sí sin el tope de 5.000 filas). Si editaste el
texto después de ejecutar, el archivo refleja esa nueva consulta, no la grilla
que estás viendo. No está disponible después de una modificación, para no
re-ejecutar el cambio por accidente.

**La sesión se cierra sola a los 30 minutos** de inactividad. Si dejaste algo
pendiente de confirmar y volvés más tarde, esa modificación se descarta.

> **Una consulta de lectura pesada también molesta.** Aunque no modifique nada,
> mantiene la conexión ocupada y puede llegar a bloquear operaciones de
> mantenimiento que corran en paralelo. Evitá dejar consultas largas corriendo
> mientras el sistema está actualizando datos.

## Cuándo usarla

Es la última herramienta, no la primera. Casi todo lo que se necesita mirar
tiene una pantalla propia:

- Para revisar precios de un activo → [Visualizador de precios](/manual/visualizador-de-precios)
- Para explorar tablas con filtros → [Explorador de datos](/manual/explorador-de-datos)
- Para detectar activos con datos incompletos → [Verificación de datos](/manual/verificacion-de-datos)
- Para liberar espacio → [Limpieza de datos](/manual/limpieza-de-datos)

La consola queda para lo que ninguna de esas resuelve: diagnóstico puntual y
correcciones quirúrgicas que sepas justificar.
