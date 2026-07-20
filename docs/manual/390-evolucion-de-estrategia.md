---
slug: evolucion-de-estrategia
title: Evolución de Estrategia
chapter: 3. Análisis
order: 390
roles: invitado
page: /evolucion-estrategia
---

El [Screener de Señales](/manual/screener-de-senales) te muestra el ranking de
una estrategia **en un día**. Esta pantalla responde la pregunta siguiente:
**¿cómo venían esos activos antes de hoy?** Elegís una estrategia, un puñado de
activos y un período, y obtenés el score de cada uno a lo largo del tiempo, uno
al lado del otro en el mismo gráfico. Es la vista para distinguir un activo que
**acaba de** entrar al podio de uno que viene sostenido hace meses: dos activos
con score 70 hoy son cosas muy distintas si uno venía de 20 y el otro de 85.

---

## Cómo se usa

Son dos pasos, en este orden:

1. Elegís la **estrategia** y el rango de fechas, y tocás **Cargar activos**: la
   pantalla te trae los mejores activos de esa estrategia como sugerencia.
2. Ajustás la lista de **Activos a mostrar** y tocás **Ver**. Recién ahí se
   dibuja el gráfico.

| Control | Para qué sirve |
|---|---|
| **Estrategia** | La estrategia cuyo score se va a graficar. Aparecen las públicas y las tuyas (si sos admin, todas). |
| **Desde** / **Hasta** | Período del gráfico. Vienen con el último año cargado por defecto. |
| **Cargar activos** | Busca los mejores activos de la estrategia y llena el selector de abajo. Hasta que no lo toques, el selector no aparece. |
| **Activos a mostrar** | Selección múltiple. Sacá y agregá los que quieras comparar. |
| **Ver** | Dibuja el gráfico con la selección actual. |

### La lista de activos sugeridos

**Cargar activos** no trae todos los activos del sistema: trae los **30 mejores
por score** de esa estrategia, con el score al lado de cada ticker, y deja los
**10 primeros ya tildados** para que puedas ver algo de entrada.

La fecha de referencia de ese top 30 es la de **Hasta**. Si en esa fecha no hay
resultados calculados (un feriado, un fin de semana, o una fecha fuera del
período calculado), el sistema usa **la fecha calculada más cercana**, que
incluso puede ser posterior: el top que ves puede no ser exactamente el del día
que pediste. Y si querés comparar un activo que **no está** entre esos 30, esta
pantalla no te lo va a ofrecer —no hay buscador libre de activos acá—; para
seguir uno puntual conviene el panel de score de
[Análisis de Activo](/manual/analisis-de-activo).

> **Si cambiás de estrategia, volvé a tocar «Cargar activos».** Al cambiar de
> estrategia el selector se vacía y se vuelve a esconder solo —justamente para
> que no mezcles los activos elegidos por una estrategia con los scores de
> otra—, así que yendo directo a **Ver** no se dibuja nada: aparece
> «Seleccioná una estrategia y activos». Cambiar solo las fechas, en cambio,
> sí se resuelve tocando **Ver** de nuevo.

---

## Cómo leer el gráfico

Una línea por activo, con un marcador por cada fecha calculada. Las franjas
—verde arriba de +20, roja abajo de −20— y las punteadas en 0, +20 y −20 son
**guías visuales fijas**, iguales para toda estrategia: no son umbrales que la
estrategia use para nada.

El eje vertical va **siempre de −100 a +100**, la escala completa del score, así
que el gráfico **no hace zoom automático**: una estrategia cuyos scores se
muevan entre 5 y 15 se va a ver como una línea casi plana pegada al cero. No es
que no pase nada, es que el recorrido es chico contra la escala total.

Pasando el mouse ves los valores de **todos** los activos en esa fecha a la vez.
Con clic en un ticker de la leyenda lo escondés o lo volvés a mostrar, útil
cuando cargaste diez líneas y querés aislar dos.

> **Los tramos rectos y largos entre dos marcadores no son datos.** Un activo
> solo tiene punto en las fechas en que la estrategia le calculó score: los días
> en que **no pasó el filtro de elegibilidad** —o en que faltaban datos— no
> generan punto, y la línea une los marcadores vecinos como si nada. Mirá los
> marcadores, no la línea: un segmento largo sin marcas significa que en el
> medio ese activo estuvo fuera de la estrategia.

---

## Score y puesto no son lo mismo

Esta pantalla grafica el **score**, no el puesto en el ranking. La distinción
importa más de lo que parece: el score depende solo de las señales del activo,
pero su puesto depende de **todos los demás activos de ese día** (el ranking
transversal, explicado en [Cómo se calcula todo](/manual/conceptos-pipeline)).

En la práctica: un activo puede tener el score clavado en 60 durante un mes y
haberse caído del puesto 3 al 40 porque el resto del mercado mejoró; y al revés,
puede perder 15 puntos y **subir** en el ranking si los demás se cayeron más. Si
lo que te importa es el puesto, la vista correcta es el
[Screener de Señales](/manual/screener-de-senales), que ordena a todos los
activos de una fecha. Esta pantalla te dice cómo evolucionó el activo **en sus
propios términos**.

> **Si cambiaste la definición de la estrategia, el histórico viejo sigue siendo
> el viejo.** Las fechas anteriores quedaron calculadas con los pesos, las
> señales y el filtro de entonces, y una actualización incremental no las toca.
> Hasta que se haga un **recálculo completo**, el gráfico mezcla dos
> definiciones en la misma línea y cualquier quiebre que veas puede ser tuyo y
> no del mercado. Lo mismo con un activo agregado hace poco: su historia arranca
> recién cuando se lo incorporó. El detalle, en
> [Cómo se calcula todo](/manual/conceptos-pipeline).

---

## En qué se diferencia de «Historial de Señales»

Las dos grafican puntajes en el tiempo, pero cortan la información en sentidos
opuestos:

| | Evolución de Estrategia | [Historial de Señales](/manual/historial-de-senales) |
|---|---|---|
| Fija | Una estrategia | Un activo |
| Compara | Varios activos entre sí | Varias señales entre sí |
| Responde | ¿Cuál de estos activos viene mejor para esta estrategia? | ¿Qué parte del score de este activo está empujando y cuál frenando? |

El uso natural es encadenarlas: acá detectás **qué** activo se dio vuelta, y en
Historial de Señales averiguás **por qué**.

---

## Cuándo conviene abrirla

- **Antes de comprar algo que salió en el screener**: ¿el score alto de hoy es
  una tendencia de meses o un salto de tres días?
- **Para revisar una posición abierta**: si la línea viene bajando sostenida, la
  estrategia se está dando vuelta sobre ese activo aunque todavía figure bien
  rankeado.
- **Para entender un cambio en el ranking**: si un activo se cayó de puesto, acá
  ves si perdió score propio o si no se movió mientras el resto mejoraba.

> Si al tocar **Cargar activos** no aparece el selector, esa estrategia todavía
> no tiene resultados calculados: no es un error de la pantalla. Y si el gráfico
> responde «Sin datos de estrategia…», probá ampliando el rango — el histórico
> puede arrancar después de la fecha que pusiste en **Desde**.
