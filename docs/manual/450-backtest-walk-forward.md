---
slug: backtest-walk-forward
title: Walk-forward
chapter: 4. Backtest y Carteras
order: 450
roles: invitado
---

Esta es la solapa más importante del módulo y la que más se malinterpreta. Vale
la pena leerla entera antes de usarla, porque no sirve para encontrar la mejor
configuración: sirve para descubrir **cuánto de lo que encontraste era mentira**.

## El problema: el sobreajuste

Probás cien configuraciones sobre diez años de historia y te quedás con la que
mejor rindió. Parece razonable, y es la forma más confiable de engañarse.

El motivo es simple. Los precios tienen una parte que responde a algo real
(tendencias, comportamiento del sector) y una parte que es puro accidente. Al
probar muchas configuraciones sobre el mismo tramo de historia, la que gana no
es necesariamente la que capturó lo real: es la que mejor le calzó a los
accidentes de **ese** tramo. Salió primera porque sus stops cayeron justo antes
de las tres caídas grandes que ocurrieron, no porque sepa anticipar caídas.

Eso es el **sobreajuste** (*overfitting*): la configuración quedó moldeada sobre
el detalle irrepetible de la historia que usaste para elegirla, y como los
accidentes futuros van a ser otros, el rendimiento no se repite — un backtest
espectacular seguido de una operatoria real decepcionante. Lo perverso es que
**cuantas más combinaciones probás, peor es el problema**: con suficientes
intentos siempre aparece alguna que rindió increíble por casualidad. Ese número
no es una predicción, es el premio de una lotería que ya se sorteó.

## La solución: entrenar en un tramo, validar en el siguiente

El walk-forward corta la historia en tramos consecutivos y avanza en el tiempo,
como se movería alguien operando de verdad:

1. Toma el primer tramo (**entrenamiento**), prueba ahí todas las combinaciones
   y elige la mejor.
2. Aplica **esa** configuración —sin volver a tocarla— sobre el tramo siguiente
   (**test**), que es historia que la búsqueda nunca vio.
3. Anota el resultado, avanza una ventana e incorpora al entrenamiento todo lo
   ya recorrido. Vuelve a optimizar, vuelve a aplicar hacia adelante.

El entrenamiento siempre arranca desde el comienzo de la historia y se va
estirando, igual que en la realidad la experiencia se acumula. Al final el
sistema pega uno tras otro todos los tramos de test: esa costura es la **curva
out-of-sample** (fuera de muestra), donde cada decisión se tomó solo con
información disponible entonces. Es lo más parecido a haberla operado en vivo
que se puede sacar del pasado.

### El número que importa es la brecha

Por cada ventana se informan dos resultados: cómo rindió la configuración
elegida **en su entrenamiento** y cómo rindió después **en el test**. La
distancia entre esos dos números es la medida directa del sobreajuste. Que el
test rinda algo menos es normal; que rinda sistemáticamente mucho menos —o que
dé negativo cuando el entrenamiento daba brillante— significa que lo que medías
era el ajuste al ruido y no una ventaja real.

## Qué optimiza y qué deja fijo

En cada entrenamiento se prueban **nueve combinaciones**: el tamaño de la
cartera (**top-N** de 10, 20 o 30 activos) contra el **trailing stop** (10%, 15%
o 20%). Nada más — la grilla es corta a propósito: cuantas menos opciones se
prueban, menos margen hay para que gane una por casualidad. Todo lo demás queda
fijo: la condición de entrada que definís vos, un rebalanceo de una rueda y el
costo que indiques. No intervienen stop loss, take profit, duración máxima ni
enfriamiento, para que se mida el efecto de los dos parámetros optimizados.

### Se maximiza el Sharpe, no la ganancia

Dentro de cada entrenamiento gana la combinación de mejor **Sharpe**, no la que
más ganó. El Sharpe es el retorno dividido por su propia variabilidad; dicho
llanamente, premia ganar **parejo**: dos configuraciones que terminan en el
mismo lugar, una subiendo de a poco y otra a los saltos, tienen la misma
ganancia y muy distinto Sharpe — gana la primera. Se eligió así justamente por
el sobreajuste: si el criterio fuera la ganancia cruda, el ganador tiende a ser
la configuración más suelta, la que se quedó montada en el tramo más favorable
sin mirar el riesgo, y esa es la que peor se repite. Pedir consistencia es pedir
algo más difícil de lograr por casualidad.

## Controles

| Control | Qué hace |
|---|---|
| **Estrategia** | Sobre qué estrategia corre. El universo son todos sus activos con score calculado. |
| **Entrada: score ≥** | La condición de entrada, fija para toda la corrida. Es lo único que define cuándo un activo es candidato. Obligatorio. |
| **Ventanas** | En cuántos tramos de test se parte la historia (entre 2 y 8; por defecto 4). Más ventanas = más validaciones independientes, pero cada tramo más corto y más ruidoso. |
| **Costo (bps/lado)** | Costo de operar en puntos básicos por operación y por lado. Arranca en 0; poné el costo real si querés un resultado creíble. |
| **Correr walk-forward** | Ejecuta. La barra avanza de a una ventana. |

## Cómo leer los resultados

**Las tarjetas de arriba** resumen la curva out-of-sample completa: **CAGR OOS**
(retorno anualizado), **Retorno total OOS** (multiplicador), **Sharpe OOS** y
**Máx drawdown OOS**. Son los números honestos de la estrategia y casi siempre
van a ser peores que los de [Cartera](/manual/backtest-cartera): esa diferencia
es el precio de no hacer trampa. **La curva** concatena los tramos de test,
indexada a 100.

**La tabla de ventanas** es donde está la información más valiosa: una fila por
ventana, con el período de test, la configuración que ganó el entrenamiento
(top-N y trailing), el **CAGR train** y el **CAGR test** —anualizados los dos,
porque los tramos tienen largos distintos y los retornos crudos no serían
comparables—. Dos cosas para mirar:

- **La brecha train contra test**, fila por fila — la medida del sobreajuste.
- **La estabilidad de la configuración ganadora.** Si todas eligen más o menos
  lo mismo (siempre top-20, siempre trailing 15%), hay algo estructural y podés
  confiar. Si cada ventana elige algo distinto, el óptimo salta con el ruido:
  quedate con el valor más conservador o asumí que ese parámetro no aporta.

## Advertencias

> **En cada costura la cartera se rearma desde cero:** cada tramo de test
> arranca sin posiciones heredadas del entrenamiento. Se pierde el retorno de la
> rueda de la costura y se paga la entrada de nuevo, así que el criterio castiga
> un poco el resultado y nunca lo mejora — que es lo que querés en una validación.

> **Necesita historia suficiente.** Los tramos salen de dividir toda la historia
> disponible y cada uno tiene que llegar a un mínimo de ruedas; si no alcanza, la
> pantalla te lo dice y hay que bajar las ventanas. Si avisa que la estrategia no
> tiene historia calculada, falta el recálculo completo — ver
> [Cómo se calcula todo](/manual/conceptos-pipeline).

> **La corrida no se guarda** y **corre de a una por vez en todo el sistema.**
> Vive solo mientras tengas la pantalla abierta: no se archiva ni aparece en
> [Comparar](/manual/backtest-comparar), así que si el resultado importa,
> anotalo. Y si otra persona está corriendo una, la tuya espera: es un cálculo
> pesado y la barra puede quedarse quieta un rato largo entre ventana y ventana.

## Cuándo usarlo

No es la primera parada: el orden natural es explorar en
[Cartera](/manual/backtest-cartera), quedarte con dos o tres candidatas,
contrastarlas en [Comparar](/manual/backtest-comparar) y **recién entonces**
traer la ganadora acá. Usalo sobre todo cuando el resultado te entusiasme
demasiado: un backtest extraordinario es el que más chances tiene de estar
sobreajustado, y el walk-forward es la pregunta incómoda que conviene hacerse
antes de poner plata, no después.
