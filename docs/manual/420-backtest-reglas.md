---
slug: backtest-reglas
title: Nivel Reglas — rendimiento sobre el universo
chapter: 4. Backtest y Carteras
order: 420
roles: invitado
---

Es la segunda solapa de [Backtest de Estrategia](/manual/backtest) y responde
una pregunta distinta a la de [Señal](/manual/backtest-senal). Aquella mide si
el **ranking** anticipa retornos; ésta, si **tus reglas de operación** —entrar
con tal score, salir con tal stop— ganan plata en promedio aplicadas a todos
los activos de la estrategia.

## Qué agrega respecto de Análisis de Activo

El motor de entrada y salida es **exactamente el mismo** que el de la simulación
de estrategias de [Análisis de Activo](/manual/analisis-de-activo): entrás
cuando se cumplen **todas** las condiciones de entrada activas, salís con la
**primera** condición de salida que dispare, y si el activo deja de ser elegible
para la estrategia el trade se cierra igual. Todo eso está explicado en detalle
allá y no se repite acá.

Lo que cambia es el alcance. En Análisis de Activo mirás **un** activo y ves los
trades dibujados sobre su gráfico. Acá esas mismas reglas se corren sobre
**todos los activos que la estrategia haya scoreado alguna vez**, uno por uno y
sobre toda su historia disponible, y después se agregan los resultados. Eso te
saca de una trampa muy común: una regla puede verse espectacular en el activo
que la inspiró y ser mediocre o perdedora en los otros doscientos. Acá lo ves.

Ojo: **no es una cartera**. Cada activo se simula aislado, como si tuvieras
plata infinita para tomar todas las posiciones a la vez. Para el caso realista
—capital finito, hay que elegir— está [Cartera](/manual/backtest-cartera).

---

## Los controles

| Control | Para qué sirve |
|---|---|
| **Estrategia** | Define el universo (los activos con score) y la serie de scores sobre la que corren las reglas. |
| **Entrada Score ≥** | Se entra cuando el score llega a ese nivel. |
| **Entrada Percentil ≥** | Se entra cuando el activo está sobre ese percentil del ranking del día (100 = el mejor). Si ponés las dos, se exigen **las dos**. |
| **Salida Score <** | Cierra cuando el score cae bajo ese nivel absoluto. |
| **SL %** | Stop loss: cierra si el precio cae ese porcentaje desde la entrada. |
| **TP %** | Take profit: cierra si el precio sube ese porcentaje desde la entrada. |
| **Trailing %** | Cierra si el precio cae ese porcentaje desde el máximo alcanzado durante el trade. |
| **Máx ruedas** | Duración máxima del trade. |
| **Enfriamiento** | Ruedas de espera después de una salida antes de poder volver a entrar. |
| **Rearm** | Es el «Cruce» de Análisis de Activo: tras salir, la condición de entrada tiene que dejar de cumplirse antes de habilitar otra entrada. Evita re-entrar al día siguiente. |
| **Correr reglas** | Lanza la corrida. La barra de progreso avanza activo por activo. |

> **Un campo con número es una condición prendida; para apagarla, vaciálo.** No
> hay tildes acá: la solapa arranca con SL, TP, Trailing y Máx ruedas cargados,
> así que para medir la señal desnuda hay que borrarlos a mano. Y no vas a poder
> correr nada sin al menos una entrada (**Score ≥** o **Percentil ≥**).

---

## Cómo se leen los resultados

Arriba, cuatro números que resumen la corrida:

- **Activos con trades** — cuántos activos del universo llegaron a operar
  alguna vez, sobre el total. Si es una fracción chica, tus reglas son muy
  exigentes y la muestra es más flaca de lo que parece.
- **Retorno mediano (por activo)** — el activo del medio. Es el número más
  honesto del tablero: no lo mueve un solo activo que se disparó.
- **Win rate medio** — el promedio de los porcentajes de acierto **de cada
  activo**, no el porcentaje global de trades ganadores: un activo con dos
  trades pesa lo mismo que uno con cincuenta.
- **Trades totales** — operaciones generadas en todo el universo.

Debajo, dos gráficos. **Salidas por motivo** cuenta por qué se cerró cada trade,
y es la forma más rápida de ver si una regla está haciendo todo el trabajo o
ninguno:

| Motivo | Qué lo disparó |
|---|---|
| **Stop loss (SL%)** | El SL % |
| **Take profit (TP%)** | El TP % |
| **Trailing stop (TS%)** | El Trailing % |
| **Máximo de ruedas** | Se agotó el Máx ruedas |
| **Score bajo el nivel** | El Salida Score < |
| **Dejó de ser elegible** | El activo dejó de ser elegible para la estrategia |

Si casi todo cierra por **Máximo de ruedas**, tus salidas por precio
prácticamente no existen y estás midiendo un buy & hold a plazo fijo. Si domina
**Stop loss (SL%)**, el stop está demasiado ajustado contra la volatilidad del
universo.

**Retorno total por activo** es el histograma de esos retornos. Mirale la forma,
no solo el centro: una distribución con cola derecha larga y mediana negativa
significa que la estrategia vive de unos pocos aciertos grandes, algo muy
distinto de una que gana parejo aunque el promedio sea el mismo.

Al final, la tabla **Mejores activos (por retorno total)** lista los **20
primeros** con sus trades, win rate, retorno total, retorno medio por trade y
duración promedio. Sirve para ir a mirar dos o tres casos en
[Análisis de Activo](/manual/analisis-de-activo) y entender qué pasó.

> **El «Ret. total» de un activo es compuesto, no una suma.** Encadena los
> retornos de sus trades cerrados, así que un activo con veinte operaciones
> tiene una escala completamente distinta a uno con dos, y no son comparables
> entre sí de forma directa. Para comparar la calidad de la regla, mirá el
> **Ret. medio** por trade.

---

## Límites de esta solapa

> **Los retornos son brutos: acá no se descuentan costos de transacción.**
> Con reglas de rotación rápida —enfriamiento corto, máx ruedas bajo— la
> diferencia contra la realidad puede ser grande. Si querés ver el efecto de las
> comisiones, corré la misma configuración en
> [Cartera](/manual/backtest-cartera), que sí las modela.

> **Corre siempre sobre toda la historia disponible**: no hay recorte de fechas.
> Todos los activos aportan desde su primera rueda con score, así que los que se
> agregaron hace poco pesan menos que los viejos.

> **La corrida no se guarda** y **hay una sola a la vez en todo el sistema.**
> Si cambiás un parámetro y volvés a correr, el resultado anterior se pierde:
> para comparar dos configuraciones, anotá los números. Guardar y comparar
> corridas hoy solo lo permite el nivel [Cartera](/manual/backtest-cartera).

Si la estrategia no tiene historia calculada, la pantalla te lo dice y no corre
nada: hace falta un **recálculo completo**, explicado en
[Cómo se calcula todo](/manual/conceptos-pipeline).

---

## Cuándo conviene usarla

- **Después de que Señal dio bien.** Que el ranking prediga no garantiza que tus
  reglas lo capturen: entre el poder predictivo y la plata están los stops.
- **Para calibrar un stop.** Corré la misma configuración cambiando solo el
  **Trailing %** y mirá cómo se mueven las Salidas por motivo y el retorno
  mediano.
- **Para descartar rápido.** Si con reglas razonables el retorno mediano por
  activo es negativo, no tiene mucho sentido seguir a la simulación de cartera.
