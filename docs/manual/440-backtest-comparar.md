---
slug: backtest-comparar
title: Comparar corridas
chapter: 4. Backtest y Carteras
order: 440
roles: invitado
---

Probar una idea una sola vez no dice casi nada. Lo que sirve es la comparación:
*¿top-20 rinde mejor que top-10? ¿el trailing al 15% aporta o solo recorta?
¿la estrategia nueva le gana a la que venís usando?* Esta solapa existe para
responder esas preguntas mirando las curvas una al lado de la otra en vez de
anotar números sueltos en un papel.

## Cómo llega una corrida acá

No se corre nada desde esta solapa. Las corridas se generan en
[Cartera](/manual/backtest-cartera) y se archivan desde ahí con el botón
**💾 Guardar corrida**. Recién entonces aparecen en la lista de esta pantalla.

Al guardar, el sistema arma solo el nombre de la corrida con los datos que la
definen: la estrategia, el **top-N**, cada cuántas ruedas rebalancea y el costo
en puntos básicos por lado. Por ejemplo:
`Momento sectorial · top-20 · rebal 5 · 10.0bps`. Ese nombre es lo único que vas
a tener después para saber qué comparaste, así que conviene mirarlo antes de
sacar conclusiones.

### Las corridas son fotos, no consultas en vivo

Una corrida guardada es una **foto**: se archivan la configuración, la curva de
la cartera y sus indicadores tal como quedaron el día que la corriste. **Nunca
se recalcula.** Si mañana llegan precios nuevos, o editás la estrategia, o
recalculás la historia, la corrida vieja sigue mostrando exactamente los mismos
números.

Eso es a propósito y es lo que la hace útil: una corrida es evidencia
reproducible de lo que decidiste en ese momento. Pero también significa que
para incorporar datos nuevos hay que **correr una nueva** y guardarla — no hay
forma de "refrescar" una existente.

> Cada simulación se puede guardar **una sola vez**. Si volvés a apretar
> **💾 Guardar corrida** sin haber corrido otra, la pantalla te avisa que corras
> una antes de guardar. Es para no archivar la misma foto dos veces.

## Controles

| Control | Qué hace |
|---|---|
| **Corridas guardadas** | Selector múltiple. Elegís cuántas corridas quieras y se superponen. Cada entrada muestra el número de corrida, su nombre y la fecha y hora en que se guardó. |

No hay botón de ejecutar: apenas elegís (o sacás) una corrida, el gráfico y la
tabla se rehacen solos.

## Qué muestra

**El gráfico de curvas superpuestas.** Una línea por corrida elegida, todas
**indexadas a 100** en su punto de partida. Indexar significa que no importa
con cuánto capital arrancó cada una: todas empiezan en 100 y lo que ves es el
crecimiento relativo. Una curva que termina en 180 multiplicó por 1,8.

**La tabla de KPIs, corrida por corrida:**

| Columna | Qué significa |
|---|---|
| **CAGR** | Retorno anualizado compuesto. Traduce todo el período a "cuánto rindió por año", que es la única forma justa de comparar tramos de distinto largo. |
| **Sharpe** | Retorno dividido por su propia variabilidad, anualizado. Mide qué tan parejo fue el camino: dos carteras que terminan igual pero una con sacudones y otra sin ellos tienen el mismo CAGR y muy distinto Sharpe. |
| **Máx DD** | La peor caída desde un máximo hasta el piso posterior. Es el número que dice cuánto dolor había que aguantar sin abandonar. |
| **Ret. total** | El resultado acumulado del período completo, como multiplicador (×2,41 = terminó valiendo 2,41 veces lo inicial). |

> Tanto el gráfico como la tabla muestran **únicamente el sub-modo con reglas
> (gated)** de cada corrida. Las otras dos curvas de la solapa Cartera —ranking
> puro y el promedio del universo— quedan guardadas pero no se dibujan acá. Si
> lo que querés medir es cuánto aportan los stops, esa comparación se hace
> dentro de la solapa [Cartera](/manual/backtest-cartera), no en esta.

## Comparar solo lo que es comparable

La pantalla te deja superponer **cualquier** par de corridas guardadas, incluso
cuando la comparación no significa nada. Nadie te va a frenar; el criterio lo
ponés vos.

Los casos en que el gráfico engaña:

- **Distintas estrategias.** Cada estrategia tiene su propio filtro de
  elegibilidad, así que el universo de activos no es el mismo. La comparación
  sigue siendo válida como pregunta de negocio ("¿cuál me conviene?"), pero no
  aísla el efecto de un parámetro: cambiaron demasiadas cosas a la vez.
- **Distintos períodos.** Cada curva se dibuja sobre las fechas que tuvo su
  propia corrida y arranca en 100 el día que arranca. Si una cubre 2015-2026 y
  otra 2020-2026, se ven en el mismo gráfico pero no atravesaron los mismos
  mercados. El CAGR sigue siendo comparable —está anualizado—; el **Ret. total**
  y el **Máx DD** no, porque dependen del largo del tramo.
- **Historia recalculada en el medio.** Si entre dos corridas cambiaste la
  definición de una señal o de la estrategia y pediste un recálculo, la primera
  quedó calculada con las reglas viejas. Ver
  [Cómo se calcula todo](/manual/conceptos-pipeline) para cuándo pasa esto.

**La comparación limpia es la que cambia una sola cosa.** Misma estrategia,
mismo período, mismos costos, y variás solo el top-N. O solo el trailing. Así
la diferencia entre las curvas se le puede atribuir a algo.

## Qué ves y qué no

Cada quien ve las corridas que guardó. El administrador ve todas. Una corrida
guardada por otro usuario no aparece en tu lista ni se dibuja aunque llegues a
ella de otra forma.

> Hoy las corridas guardadas **no se pueden borrar** una por una desde la
> pantalla. Se acumulan, y como los nombres se generan solos, dos pruebas con
> la misma configuración quedan con nombres idénticos y solo se distinguen por
> la fecha y hora. Guardá con criterio: archivá las corridas que representan
> una decisión, no cada tanteo.

## Cómo usarla

1. Corré en [Cartera](/manual/backtest-cartera) tu configuración de referencia y
   guardala. Es tu punto de comparación.
2. Cambiá **un** parámetro, corré de nuevo, guardá.
3. Volvé acá, elegí las dos y mirá si la curva nueva le gana de verdad o si la
   diferencia es ruido.
4. Cuando una configuración se sostiene, validala en
   [Walk-forward](/manual/backtest-walk-forward) antes de creerle. Comparar
   corridas te dice cuál rindió mejor **sobre el pasado que ya viste**; el
   walk-forward es el que responde si eso tenía chance de repetirse.
