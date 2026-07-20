---
slug: evolucion
title: Evolución Relativa
chapter: 3. Análisis
order: 340
roles: invitado
page: /evolucion
---

Esta pantalla responde una sola pregunta, pero la responde bien: **¿quién le
ganó a quién, y desde cuándo?**

Todas las series se llevan a **base 100** en una misma fecha de arranque, así
que lo que ves no son precios sino **rendimiento acumulado comparable**. Un
activo en 130 subió 30 % desde el arranque; uno en 85 perdió 15 %. Como todos
parten del mismo punto, la comparación es visual e inmediata, sin importar que
uno cotice a 3 pesos y el otro a 40.000.

## Armar la lista de series

Arriba elegís el **Modo de selección**, y según cuál marques cambia el panel de
carga que aparece debajo. Los cuatro modos escriben en la misma lista: podés
mezclarlos libremente (dos activos sueltos + un sector entero, por ejemplo).

| Modo | Qué agrega | Cuándo te sirve |
|---|---|---|
| **Por activo** | Un activo por vez, buscándolo por ticker o nombre. | Comparaciones puntuales: tres papeles que estás mirando. |
| **Por benchmark** | De un saque, **todos los activos que referencian a ese benchmark** — sea porque lo tienen asignado directamente o porque pertenecen a un mercado que lo usa. | Ver cómo le fue a todo el panel de un índice. |
| **Por sintético** | Un activo calculado (ratio, índice, conversión de moneda). | Sumar un ratio ya definido a la comparación en vez de recalcularlo mentalmente. |
| **Por grupos** | Todos los activos que cumplan los filtros de **País**, **Moneda**, **Tipo**, **Sector**, **Industria** y **Mercado**. | Comparar un sector completo, o todo lo que cotiza en una moneda. |

En **Por grupos** los seis filtros son de selección múltiple y **se combinan
exigiendo todos** los que hayas cargado: si elegís sector Energía y país
Argentina, entran los que cumplen las dos cosas. Dentro de un mismo filtro, en
cambio, varias opciones suman. Hay que cargar al menos un filtro para que el
botón haga algo.

> Ojo con **Por grupos** y **Por benchmark**: pueden agregar decenas de series
> de un click. El gráfico las dibuja todas, pero deja de leerse. Si te pasó,
> usá **Limpiar todo** y volvé a armar la lista más chica.

### El aviso de activos relacionados

Cuando agregás un activo **sintético** o un activo que **es benchmark de
otros**, aparece un aviso que te ofrece sumar también los relacionados: los
componentes de la fórmula en el primer caso, los activos que lo usan como
benchmark en el segundo. Es un atajo pensado para el caso típico: si vas a
mirar un ratio, casi siempre querés ver al lado las dos puntas que lo forman.

Elegís **Sí, agregar relacionados** o **Solo el activo**. Los sintéticos de
conversión de moneda no disparan este aviso, porque sus componentes no aportan
nada a la lectura.

### La lista de series

Debajo de los controles queda una fila de etiquetas, una por serie, con su
color. Cada una tiene un **ojo** para mostrarla u ocultarla y una **cruz** para
sacarla. Las que entraron por benchmark o por grupo aparecen marcadas con
`[grp]`, y las que entraron como relacionadas con `[rel]`, para que sepas de
dónde salió cada cosa cuando la lista creció.

El selector de activos marca con **⚠️** los que tienen observaciones abiertas de
la verificación de datos. No los excluye: te avisa que esa curva puede estar
apoyada en precios sospechosos.

## Fechas, base y fechas comunes

Acá está la sutileza que más confunde, y conviene entenderla una vez:

**El gráfico solo usa las fechas en que cotizaron *todas* las series visibles.**
Se cruzan los calendarios de todos los activos elegidos y se conserva la
intersección. Es la única forma de que la comparación sea honesta — si un activo
no operó un día, no hay nada que comparar ese día.

Esto tiene dos consecuencias prácticas:

- Mezclar activos de **plazas con feriados distintos** recorta el calendario:
  comparar un papel local con uno de Wall Street deja afuera los feriados de
  cada uno. Es correcto, pero explica por qué la curva puede verse con menos
  puntos de los que esperabas.
- **Ocultar una serie con el ojo no es solo cosmético.** La serie oculta sale
  del cálculo, el calendario común se vuelve a armar sin ella y *las demás
  curvas pueden cambiar de forma*. Si una serie con historia corta te estaba
  recortando todo, ocultarla ensancha el período de golpe.

Sobre la **Fecha desde**: es la base del rebase, pero el sistema no exige que
exista exactamente. Toma la **última fecha común igual o anterior** a la que
pediste; si ninguna serie cotizó antes, usa la primera fecha común disponible.
Por eso el título del gráfico aclara siempre con qué fecha se armó la base 100 —
mirala cuando el resultado te sorprenda, especialmente si metiste un activo que
empezó a cotizar hace poco y arrastró el arranque de todos hacia adelante.

La **Fecha hasta** solo recorta el final; no cambia la base.

## Leer el gráfico

Cada serie es una línea con su ticker escrito al final, así que no hace falta
cruzar referencias con una leyenda. La **línea punteada en 100** es el punto de
partida: por encima, el activo ganó desde la base; por debajo, perdió. Lo que
importa no es tanto el nivel de cada línea como **la distancia entre ellas**:
esa brecha es la diferencia de rendimiento acumulada en el período.

El switch **Mostrar eventos** sombrea de fondo las franjas de los eventos de
mercado cargados en el sistema — globales, los del país de alguno de los activos
elegidos y los específicos de esos activos —, filtrando los que no se solapan
con el período visible. Sirve para lo que siempre se sospecha y rara vez se
verifica: ¿la brecha se abrió sola o se abrió en la crisis?

> Cambiar la **Fecha desde** cambia el ganador. Es lo esperable, no un error:
> el rendimiento relativo siempre se mide contra un arranque. Antes de concluir
> "este le gana a aquel", probá dos o tres fechas de base distintas y fijate si
> la conclusión aguanta.

Para el detalle de un activo puntual —indicadores, fundamentales, simulación—
está la pantalla de [Análisis de Activo](/manual/analisis-de-activo). Esta
pantalla mira precios crudos: no interviene el pipeline de indicadores ni de
señales que se describe en [Cómo se calcula todo](/manual/conceptos-pipeline).
