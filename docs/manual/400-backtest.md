---
slug: backtest
title: Backtest de Estrategia
chapter: 4. Backtest y Carteras
order: 400
roles: invitado
page: /backtest
---

Todas las pantallas de análisis te muestran **qué dice hoy** una estrategia: qué
activos rankea arriba, con qué score, empujados por qué señales. Ninguna
responde la pregunta que viene después, que es la única que importa antes de
poner plata: **¿esto habría funcionado?**

Para eso está el Backtest. Es el laboratorio donde una estrategia se corre
contra el **pasado** y se mide con números en vez de con impresiones. Y no se
mide de una sola manera: la pantalla tiene cinco solapas, y cada una responde
una pregunta distinta sobre el mismo plan.

> El Backtest **no calcula nada nuevo sobre los activos**: lee la historia de
> scores que la estrategia ya dejó calculada (el encadenamiento está explicado
> en [Cómo se calcula todo](/manual/conceptos-pipeline)). Si esa historia está
> incompleta o quedó calculada con una definición vieja de la estrategia, el
> backtest va a medir eso, sin avisarte.

---

## Las cinco solapas, y cuál te sirve

| Si querés saber… | Usá la solapa |
|---|---|
| ¿El ranking de la estrategia **sirve para algo**? ¿Los mejores rinden más que los peores? | [**Señal**](/manual/backtest-senal) |
| ¿Qué tan buenas son **mis reglas de entrada y salida** (stops, take profit, límite de ruedas) aplicadas a todo el universo? | [**Reglas**](/manual/backtest-reglas) |
| Si armara una **cartera** con los mejores N y la rotara, ¿qué curva de resultado habría dado, contra un benchmark? | [**Cartera**](/manual/backtest-cartera) |
| ¿Cuál de las **corridas que ya hice** es mejor? ¿Cómo se ven una al lado de la otra? | [**Comparar**](/manual/backtest-comparar) |
| ¿Los parámetros que elegí funcionan **fuera del período donde los elegí**, o los sobreajusté? | [**Walk-forward**](/manual/backtest-walk-forward) |

El orden de las solapas no es decorativo: es una **escalera**, y conviene
subirla en orden.

### 1. Señal — calidad del ranking

Mide si el ranking predice retornos, sin simular ni una operación. Parte los
activos de cada fecha en cuantiles por score y mira cuánto rindió cada cuantil
después. Es el filtro más barato y el más duro: si acá no hay nada, ninguna
regla de entrada lo va a arreglar. **Empezá siempre por acá.**

### 2. Reglas — rendimiento sobre el universo

Toma un juego de reglas de operación (entrada por score o percentil, salida por
score, stop loss, take profit, trailing, máximo de ruedas, enfriamiento) y lo
corre sobre **todos** los activos de la estrategia, uno por uno. Responde "¿qué
tan buenas son estas reglas **en promedio**?", con el desglose de por qué motivo
se cerró cada operación.

Es el paso natural después de haber jugado con las condiciones en el gráfico de
[Análisis de Activo](/manual/analisis-de-activo): ahí probás las reglas sobre
**un** activo, acá las validás sobre todos.

### 3. Cartera — simulación top-N

Acá recién aparece una **cartera**: se mantienen los N mejores por score, con un
período de rebalanceo y costos de transacción. Dibuja dos curvas superpuestas —
una que rota solo por ranking y otra que además respeta las reglas de entrada y
salida— y las compara contra el promedio del universo. La distancia entre las
dos curvas es, justamente, **cuánto aportan los stops**.

Desde esta solapa podés **guardar la corrida** (para verla en Comparar) o
**promoverla a seguimiento**, que crea una cartera teórica en
[Carteras](/manual/carteras) siguiendo ese mismo top-N.

### 4. Comparar

Superpone las curvas de las corridas de Cartera que hayas guardado y pone sus
indicadores lado a lado. Es la solapa de la decisión final entre variantes que
ya corriste.

### 5. Walk-forward

La más honesta y la más incómoda. Divide la historia en ventanas: en cada una
busca la mejor combinación de parámetros y la aplica en la ventana
**siguiente**, sobre datos que no vio. Encadenando esos tramos sale una curva
sin trampa, y la brecha entre lo que prometía el ajuste y lo que dio después es
la medida del **sobreajuste**.

---

## Cosas que valen para toda la pantalla

**Qué estrategias ves.** El selector de estrategia lista las públicas y las
tuyas; si sos admin, todas. Es el mismo criterio de
[Visibilidad y permisos](/manual/visibilidad-y-permisos) del resto del sistema.

**Una corrida por vez en cada solapa.** Cada solapa corre en segundo plano con
su propia barra de progreso y no te deja lanzar dos corridas del mismo tipo a la
vez: si lo intentás, te avisa que ya hay una en curso. Solapas distintas sí
pueden estar corriendo en paralelo.

**Qué queda guardado y qué no.** No todas las solapas persisten lo que corren:

| Solapa | ¿Queda guardada? |
|---|---|
| **Señal** | Sí, automáticamente. Cada corrida aparece en **Corridas guardadas**. |
| **Reglas** | No. Se corre a demanda y se muestra en pantalla. |
| **Cartera** | Solo si tocás **Guardar corrida**. |
| **Comparar** | No corre nada: lee las corridas de Cartera guardadas. |
| **Walk-forward** | No. Se corre a demanda. |

> **Las corridas guardadas son fotos, no vistas vivas.** Nunca se recalculan: se
> guardan con su configuración y sus resultados tal como salieron ese día. Si
> cambiás la estrategia y querés el número nuevo, hay que correr una corrida
> nueva y comparar. Tené en cuenta además que **las corridas guardadas no se
> pueden borrar desde esta pantalla**, así que se acumulan: conviene ser
> ordenado con lo que guardás.

> **Antes de sacar conclusiones, revisá la historia.** Si editaste señales,
> pesos o el filtro de una estrategia, las fechas viejas siguen calculadas con
> la definición anterior hasta que corras un **recálculo completo**. Y si
> agregaste activos hace poco, su historia arranca recién ahí. Un backtest
> sobre una historia mezclada mide dos estrategias distintas pegadas.

---

## Backtest y Carteras no son lo mismo

Se parecen porque comparten las vistas, pero miran en direcciones opuestas: el
**Backtest** simula un plan sobre el **pasado** y produce corridas inmutables;
[Carteras](/manual/carteras) es la biblioteca de tus carteras —reales, con
registro de operaciones, y teóricas de seguimiento— que viven **hacia adelante**
y se actualizan solas con el paso de los días.

El puente entre los dos es el botón **Promover a seguimiento** de la solapa
Cartera: lo que validaste en el laboratorio pasa a ser algo que seguís todos los
días.
