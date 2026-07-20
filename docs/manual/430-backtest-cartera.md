---
slug: backtest-cartera
title: Nivel Cartera — simulación top-N
chapter: 4. Backtest y Carteras
order: 430
roles: invitado
---

Es la solapa donde el backtest deja de ser una medición estadística y pasa a
responder la pregunta que importa: **si hubiera operado esto, cuánta plata
tendría hoy y cuánto susto habría pasado en el camino.**

A diferencia de [Reglas](/manual/backtest-reglas), que simula cada activo
aislado, acá el capital es finito: en cada rebalanceo se reparte en partes
iguales entre los **N mejores por score** y nada más. Un activo que Reglas
contaba como ganador puede no haber entrado nunca acá, porque nunca llegó a
estar entre los mejores del día.

## Las tres curvas

La simulación corre tres cosas a la vez, superpuestas en el mismo gráfico e
indexadas a 100 al inicio:

- **Con reglas (gated)** — un activo entra si está en el top-N **y** además sus
  reglas de entrada dispararon; sale cuando alguna regla lo cierra **o** cuando
  se cae del corte del top-N.
- **Ranking puro** — la misma cartera top-N pero **sin reglas**: rota
  únicamente por score, siempre invertida.
- **EW universo** (punteada) — todos los activos en partes iguales. Es la vara:
  si tu curva no le gana a esto, la estrategia no aporta nada que no te diera
  comprar el universo entero.

La distancia entre las dos primeras es la respuesta a **cuánto aportan los
stops**. Si «Con reglas» va por debajo de «Ranking puro», tus salidas te sacan
de posiciones que después siguieron subiendo.

---

## Los controles

| Control | Para qué sirve |
|---|---|
| **Estrategia** | Define el universo y los scores que arman el ranking diario. |
| **Top-N** | Cuántos activos se mantienen. Con N chico la cartera es concentrada y volátil; con N grande se parece cada vez más al universo entero. |
| **Rebalanceo (ruedas)** | Cada cuántas ruedas se recalcula la composición. 1 = todos los días. |
| **Costos (bps/lado)** | Costo de operar, en puntos básicos por lado. 10 bps = 0,10% de lo que se compra o se vende. |
| **Entrada Score ≥** / **Percentil ≥** | Condiciones de entrada; si cargás las dos, se exigen las dos. Al menos una es obligatoria. |
| **Salida Score <** | Cierra la posición cuando el score cae bajo ese nivel. |
| **SL %** / **TP %** / **Trail %** | Stop loss, take profit y trailing stop sobre el precio. |
| **Máx r.** | Duración máxima de una posición, en ruedas. |
| **Enfr.** | Ruedas de espera tras una salida antes de volver a entrar en ese activo. |
| **Rearm** | Tras salir, la entrada tiene que dejar de cumplirse antes de habilitar otra. |
| **Correr** | Lanza la simulación. |

Las condiciones de entrada y salida son las mismas, y con la misma semántica,
que las de [Análisis de Activo](/manual/analisis-de-activo); solo afectan al
sub-modo **Con reglas (gated)**. Un campo vacío es una condición apagada.

> **Con rebalanceo mayor a 1 rueda, las salidas se aplican recién en el próximo
> rebalanceo.** Si ponés rebalanceo 5 y un stop se dispara al día siguiente, la
> cartera lo sigue teniendo cuatro ruedas más. Para que los stops actúen en el
> momento, usá **rebalanceo = 1** — a cambio de mucho más costo de rotación.

---

## Cómo se arma la simulación

- **Partes iguales**, sin ponderar por tamaño, convicción ni volatilidad.
- **Sin adelantarse a los hechos**: la cartera se arma con los scores del cierre
  de un día y su primer retorno es el del día siguiente.
- **Puede tener menos de N.** Si solo tres de los veinte mejores están
  habilitados, la cartera tiene tres posiciones — y si no hay ninguno queda
  **entera en efectivo**, que acá no rinde nada: la curva se aplana.
- **Los costos se cobran en cada rebalanceo**, proporcionales a la porción de la
  cartera que cambió de manos. Si nada se mueve, no se paga nada.

> **El benchmark EW no paga costos.** Es una decisión deliberada, para que la
> comparación te juegue en contra y no a favor: si tu cartera le gana **pagando**
> comisiones a un universo que no las paga, le gana de verdad.

---

## Las métricas, en castellano

Los cuatro recuadros de arriba, y la tabla **Comparación** que los repite para
los tres sub-modos, muestran:

| Métrica | Qué significa | Cómo se lee |
|---|---|---|
| **CAGR** | El retorno anual promedio que, compuesto, te habría llevado del principio al final. | Es la métrica para comparar períodos de largo distinto. Un 18% acá quiere decir «como si hubiera rendido 18% todos los años». |
| **Retorno total** | Cuánto se multiplicó el capital. Se muestra como múltiplo: ×2.41 es «terminé con 2,41 veces lo que puse». | No lo compares entre corridas de distinta duración: más años siempre da más múltiplo. |
| **Sharpe** | Cuánto retorno obtuviste **por unidad de riesgo**, midiendo el riesgo como la variabilidad diaria de la curva. Se calcula contra una tasa libre de riesgo de cero, así que con tasas altas es más generoso de lo que sería contra un plazo fijo. | Debajo de 1 es flojo, cerca de 2 es bueno. Sirve para elegir entre dos carteras que rindieron parecido: gana la que llegó más tranquila. |
| **Máx drawdown** | La peor caída desde un máximo hasta el piso siguiente, en porcentaje. | Es la métrica de tolerancia: un −45% significa que hubo un momento en que perdiste casi la mitad de lo que habías llegado a tener. Preguntate si te habrías bancado seguir. |

Debajo del gráfico de equity hay dos vistas más, ambas del sub-modo con reglas:

- **La curva de drawdown** (el área roja): cuánto estabas, en cada momento, por
  debajo de tu propio máximo anterior; el cero es «estoy en máximos». Mirá el
  ancho, no solo la profundidad: una caída del 20% que tarda tres años en
  recuperarse duele más que una del 30% que se recupera en dos meses.
- **El mapa de retornos mensuales**: un cuadro por mes, verde si ganó y rojo si
  perdió. Muestra si la ganancia está repartida o concentrada en dos o tres
  meses excepcionales.

## Guardar y promover

**💾 Guardar corrida** archiva la simulación con su configuración para
superponerla con otras en [Comparar](/manual/backtest-comparar). Solo podés
guardar la corrida que vos mismo lanzaste, y una vez guardada hay que volver a
correr para guardar de nuevo.

**↗ Promover a seguimiento** crea una cartera teórica en
[Carteras](/manual/carteras) que sigue el top-N de esa estrategia hacia
adelante. Es el puente entre el laboratorio y el día a día.

> **La cartera promovida se queda con la estrategia y el top-N, no con tus
> reglas.** Sigue el ranking puro: los stops, el take profit y el enfriamiento
> que configuraste acá **no** viajan con ella.

## Qué no modela esta simulación

- **No hay slippage ni spread.** El único costo es el que ponés en
  **Costos (bps/lado)**, igual para todos los activos y todos los días. Entrar
  en un papel ilíquido o en un día de pánico cuesta bastante más.
- **No hay restricción de liquidez ni de volumen**: compra lo que haga falta de
  cualquier activo, aunque en la realidad opere dos mil pesos por día.
- **No hay lotes ni fracciones mínimas**: se asume que podés comprar cualquier
  porción de cada activo, cosa que con capital chico y N grande no es cierta.
- **Todo se ejecuta al precio de cierre**, y **el efectivo no rinde**.
- **En universos de varios mercados**, un activo que no cotiza en una fecha en
  que sí cotizan otros se mantiene en cartera: no se lo vende por un feriado.

> **Corre sobre toda la historia disponible** y **hay una sola simulación a la
> vez en todo el sistema**. Si la estrategia no tiene historia calculada, hace
> falta un **recálculo completo**, explicado en
> [Cómo se calcula todo](/manual/conceptos-pipeline).

Y la advertencia de fondo: cada parámetro que ajustás mirando esta curva es una
decisión tomada sabiendo el resultado. Para saber si lo que encontraste sobrevive
a datos que nunca viste, está [Walk-forward](/manual/backtest-walk-forward).
