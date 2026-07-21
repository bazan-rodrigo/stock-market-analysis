---
slug: conceptos-pipeline
title: Cómo se calcula todo (indicadores → señales → estrategias)
chapter: 2. Conceptos centrales
order: 200
roles: invitado
---

Casi todas las pantallas del sistema son una vista sobre el mismo
encadenamiento de cuatro pasos. Entenderlo una vez ahorra entender veinte
pantallas por separado.

```
Precios  →  Indicadores  →  Señales  →  Estrategias  →  Ranking diario
```

## 1. Precios

La materia prima. Para cada activo se guarda la serie diaria de apertura,
máximo, mínimo, cierre y volumen. Sobre esto se construye todo lo demás.

Hay activos cuyo precio no se descarga sino que **se calcula**: los
*sintéticos* (por ejemplo el ratio entre dos activos) y las *conversiones de
moneda*. Para el resto del sistema son activos como cualquier otro.

## 2. Indicadores

Un indicador es una transformación de la serie de precios de **un solo activo**:
la media móvil de 200 ruedas, el RSI, el drawdown desde el máximo, el régimen de
tendencia. Cada activo se calcula por separado y no depende de los demás.

Los indicadores **no se calculan cuando abrís la pantalla**: están
pre-calculados y guardados. Esa es la decisión de diseño que permite rankear
miles de activos en un instante en vez de recalcular todo en cada consulta.

De casi todos los indicadores se guardan dos cosas: la **serie histórica**
completa (para graficarla y para el backtest) y el **valor vigente** (el del
último día, que es el que consultan las pantallas de screening). Unos pocos
guardan **solo el valor vigente** — su serie no se puede graficar ni usar hacia
atrás, y las pantallas que lo necesitan lo avisan.

## 3. Señales

Una señal traduce un indicador a un **puntaje entre −100 y +100**. Es la pieza
que convierte "el RSI está en 72" en "esto es bueno" o "esto es malo", según el
criterio que vos definas.

Hay tres formas de definir esa traducción:

| Fórmula | Para qué sirve |
|---|---|
| **Mapa discreto** | Indicadores con categorías. Asignás a mano el puntaje de cada categoría: tendencia alcista fuerte → 100, lateral → 0, bajista → −60. |
| **Umbrales** | Indicadores numéricos, por tramos. Se evalúa de arriba hacia abajo y el primer umbral que el valor supera define el puntaje. |
| **Rango lineal** | Indicadores numéricos, escala continua. Definís qué valor vale −100 y cuál +100; el resto se interpola en línea recta. |

Una señal puede mirar el indicador **de un activo** o el agregado **de un
grupo** (el sector, el mercado, el país al que pertenece). Las señales de grupo
permiten preguntas como "¿el sector de este activo viene bien?".

## 4. Estrategias

Una estrategia combina señales y produce el ranking. Tiene dos partes que hacen
cosas distintas y conviene no confundir:

**El filtro de elegibilidad** decide *quién participa*. Es un árbol de
condiciones Y/O: "que sea del panel líder **Y** que el RSI diario no esté
sobrecomprado **Y** (que sea del sector energía **O** del sector bancos)". Un
activo que no pasa el filtro simplemente no aparece en el ranking de ese día.

**El score ponderado** decide *en qué orden*. Es una suma de señales, cada una
con su peso: 40% la señal de tendencia, 30% la de momento, 30% la de valuación.
El resultado es un número por activo y por día, y ordenarlo da el ranking.

## Dos consecuencias que hay que tener presentes

### El ranking es transversal

El puesto de un activo depende de **todos los demás activos de ese día**. Un
activo puede bajar en el ranking sin que le haya pasado nada: alcanza con que
los otros hayan mejorado. Por eso el ranking no se puede calcular activo por
activo — se calcula fecha por fecha, con todos los activos juntos.

Esto tiene una implicancia práctica importante: **cuando agregás un activo
nuevo, su historia de indicadores se completa sola**, pero para que quede
incorporado a la historia de señales y rankings hay que pedir un **recálculo
completo** desde el [Centro de Datos](/manual/centro-de-datos). Una
actualización incremental no alcanza, porque cambiaría el ranking de todas las
fechas pasadas.

### El último día siempre es preliminar

El precio del día en curso puede cambiar hasta el cierre. Por eso toda
actualización incremental **recalcula siempre la última fecha** además de
llenar los huecos que falten. Si ves que el valor de ayer cambió respecto de lo
que habías mirado, es esto, y es intencional.

## Actualización incremental vs. recálculo completo

Cada vez que el sistema recalcula algo, podés elegir entre dos modos. La
diferencia importa porque uno tarda segundos y el otro puede tardar mucho.

| Modo | Qué hace | Cuándo usarlo |
|---|---|---|
| **Incremental** | Llena las fechas faltantes y rehace la última. | El día a día. Es lo que corre solo todas las noches mediante el [Scheduler de tareas](/manual/scheduler). |
| **Recálculo completo** | Borra todo y lo calcula de nuevo desde el principio. | Cambiaste la definición de un indicador, una señal o una estrategia; incorporaste activos nuevos a la historia; o **eliminaste un activo** que participaba de rankings pasados. |

La regla es simple: **si cambiaste una definición, lo viejo quedó calculado con
la definición anterior**, y solo el recálculo completo lo corrige.

Las dos operaciones se disparan desde el
[Centro de Datos](/manual/centro-de-datos); la incremental además corre sola
cada noche (ver [Scheduler de tareas](/manual/scheduler)). Y si algo no cuadra
—un valor que cambió, un activo que no aparece donde esperabas— empezá por
[Solución de problemas](/manual/solucion-de-problemas): recorre los síntomas
frecuentes y enlaza al remedio de cada uno.
