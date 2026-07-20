---
slug: activos-en-divisa
title: Activos en Divisa
chapter: 5. Activos
order: 530
roles: admin
page: /admin/ars-conversion
---

Genera **de a cientos** los sintéticos que expresan cada activo de una moneda en
otra: por cada activo que cotiza en la moneda elegida, un sintético
`activo / divisor`. Es el caso automatizado del ratio, y por eso no se carga a
mano en [Activos sintéticos](/manual/activos-sinteticos).

El concepto —por qué el sintético hereda los grupos de su activo base, y por qué
solo se generan para activos normales— está en
[Activos, sintéticos y grupos](/manual/activos-y-grupos). Acá va la operación.

## 1. Configurar los divisores

Un **divisor** es un par: una **moneda fuente** y el **activo** por el que se
divide (típicamente el tipo de cambio: CCL, MEP, Blue, etc.).

Elegí la **Moneda fuente**, el **Activo divisor** y apretá **+ Agregar**. El par
queda listado en **Divisores configurados** con su moneda, ticker y nombre.

> El selector de **Activo divisor** solo muestra activos cuyo **tipo de
> instrumento** sea de moneda o criptomoneda. Si el tipo de cambio que querés
> usar no aparece en la lista, el problema está en su tipo de instrumento:
> corregilo en [Gestión de activos](/manual/gestion-de-activos) y volvé.

Podés configurar **más de un divisor por moneda** —dólar oficial y dólar
paralelo, por ejemplo— y cada uno genera su propio juego de sintéticos. Agregar
un par que ya existe no duplica nada.

Por cada par se crean sintéticos con el ticker del activo base y el del divisor
concatenados, y el nombre del base con el divisor entre paréntesis, para
reconocerlos a simple vista en cualquier selector.

## 2. Ver qué falta

El bloque **Sincronizar sintéticos** muestra una línea por moneda configurada:

```
USD: 2 divisor(es) × 150 activos = 300 esperados — 280 existentes, 20 faltantes.
```

- **activos** son los que cotizan en esa moneda y **no** son calculados: los
  sintéticos no generan conversiones propias.
- **esperados** es el total teórico. El divisor no se convierte contra sí mismo,
  así que ese par se descuenta.
- **faltantes** es exactamente lo que va a crear la próxima sincronización.

## 3. Sincronizar

**Sincronizar ahora** crea los sintéticos faltantes y les calcula la serie de
precios completa. Una barra muestra el avance `hechos / total`.

> **Los sintéticos que ya existen no se tocan.** La sincronización solo da de
> alta lo que falta. Si querés recalcular los precios de conversiones que ya
> existen, seleccionalas en
> [Activos sintéticos](/manual/activos-sinteticos) y usá **Calcular Delta** o
> **Calcular Completo**.

Antes de arrancar, si la corrida va a incorporar activos nuevos, la pantalla
**lista las señales y estrategias que van a quedar desactualizadas** en la
historia y te recuerda correr el **Recalcular completo** de Señales y
Estrategias al terminar. No es opcional: los sintéticos nuevos entran a los
agregados de sus grupos, y eso cambia el pasado ya calculado. El porqué está en
[Cómo se calcula todo](/manual/conceptos-pipeline).

> Una primera sincronización sobre una moneda con cientos de activos crea
> cientos de activos con toda su historia de precios e indicadores. **Puede
> tardar largo rato.** Conviene lanzarla cuando no haya otras tareas pesadas
> corriendo.

### Los activos nuevos se sincronizan solos

No hace falta volver acá cada vez que das de alta un activo: al guardarlo en
[Gestión de activos](/manual/gestion-de-activos), si su moneda tiene divisores
configurados, sus conversiones se generan en el momento. **Sincronizar ahora**
es para la puesta a punto inicial y para emparejar después de una importación
masiva.

## Dar de baja un divisor

El botón **Eliminar** de cada fila de la tabla abre una confirmación que te dice
**cuántos sintéticos se van a borrar** con él.

> **Es una operación destructiva y de alto impacto.** No borra solo la
> configuración: elimina todos los activos sintéticos que usan ese divisor,
> **con toda su historia** de precios e indicadores. No se puede deshacer: para
> recuperarlos hay que volver a configurar el divisor y sincronizar de cero.

El borrado corre en segundo plano porque **puede tardar varios minutos**; podés
seguir usando la aplicación. Un aviso bajo la tabla informa el avance por etapas
y el resultado final. Mientras hay un borrado en curso no se puede lanzar otro:
si volvés a apretar Eliminar, no pasa nada — es a propósito.

Quitar sintéticos también es un cambio en el conjunto de activos, así que
también corresponde un **recálculo completo** de señales y estrategias.

## Errores comunes

| Síntoma | Causa habitual |
|---|---|
| Aparecen 0 activos para una moneda | Los activos no tienen esa **Moneda** asignada. Asignásela en lote desde la edición masiva de [Gestión de activos](/manual/gestion-de-activos). |
| El divisor deseado no está en el selector | Su **tipo de instrumento** no es de moneda ni criptomoneda. |
| Se crearon los sintéticos pero no tienen precios | El activo base o el divisor no tienen historia de precios descargada, o no coinciden en ninguna fecha: un sintético solo existe donde cotizaron **ambos**. |
