---
slug: glosario-de-indicadores
title: Glosario de indicadores
chapter: Apéndices
order: 900
roles: invitado
---

Material de consulta: qué mide cada indicador que calcula el sistema y cómo se
lee. El listado vivo, con el tipo y la escala de cada uno, está en
[Indicadores del sistema](/manual/configuracion-indicadores).

Muchos vienen en tres versiones —**diaria**, **semanal** y **mensual**—, que
miden lo mismo sobre barras de distinta duración. La diaria reacciona rápido y
tiene más ruido; la mensual es estructural y se mueve poco.

---

## Tendencia

### Régimen de tendencia

**Es categórico, no numérico**: devuelve una etiqueta. Se calcula con una media
exponencial de período fijo —configurable por temporalidad— y su pendiente:
alcista cuando la media sube más que un umbral y el precio está por encima de
ella; bajista al revés; lateral en todo lo demás.

Los valores posibles son diez, no cinco:

| Familia | Valores |
|---|---|
| Alcista | `bullish_strong`, `bullish`, `bullish_nascent_strong`, `bullish_nascent` |
| Lateral | `lateral`, `lateral_nascent` |
| Bajista | `bearish_nascent`, `bearish_nascent_strong`, `bearish`, `bearish_strong` |

Los valores **`nascent`** ("naciente") marcan un régimen que recién se está
formando: la tendencia dio vuelta hace poco y todavía no se consolidó.

> Al armar una señal de mapa discreto sobre este indicador, **asigná puntaje a
> las diez categorías**. Las que dejes afuera hacen que la señal no puntúe ese
> día. Ver [Referencia de fórmulas de señales](/manual/formulas-de-senales).

Se configura en [Régimen de Tendencia](/manual/regimen-de-tendencia).

### Fuerza de tendencia (ADX)

De 0 a 100. Mide **cuánto empuja** la tendencia, sin decir hacia dónde: un
activo que cae con fuerza y uno que sube con fuerza pueden tener el mismo valor.

Es el complemento del régimen de tendencia, que dice la dirección pero no la
convicción. Dos activos pueden estar los dos en `bullish_nascent` y ser casos
muy distintos: con fuerza 12 el movimiento todavía es ruido, con 28 ya arrancó
en serio. Como referencia de lectura habitual: por debajo de 20 no hay tendencia
que valga la pena, entre 20 y 25 está empezando a definirse, y por encima de 25
hay una tendencia establecida.

Sube cuando el precio avanza sostenidamente en una dirección y baja cuando va y
viene, aunque se mueva mucho. Por eso no reemplaza al ATR %: uno mide cuánta
convicción hay, el otro cuánto recorrido.

Se calcula en las tres cadencias y guarda historia. No tiene configuración: usa
el período estándar de 14 barras.

### Distancia a la media móvil

Qué tan lejos está el precio de su media, en porcentaje. Hay versiones para las
medias de 20, 50 y 200 ruedas.

Positivo = el precio está por encima de la media. Es una medida de *extensión*:
un valor muy alto dice que el activo se alejó mucho de su media, no que sea
buena o mala compra.

### Distancia a la media óptima (en desvíos)

La misma idea, pero contra la **mejor media móvil** de ese activo en particular
(ver más abajo), y medida en **desvíos estándar** en vez de porcentaje.

Es la versión comparable entre activos: un 5% significa cosas distintas en un
activo tranquilo y en uno volátil, pero "dos desvíos" significa lo mismo en los
dos. **Si vas a comparar activos entre sí, usá esta.**

### Mejor media móvil

Qué período de media móvil funcionó mejor como soporte/resistencia para ese
activo —la media que más veces sostuvo al precio cuando la tocó—, calculado por
separado para simple y exponencial, y para cada frecuencia.

> **Este indicador mira toda la historia disponible para decidir cuál es la
> mejor.** Eso lo hace útil para describir un activo hoy, pero problemático en
> un backtest: al evaluar una fecha del pasado estarías usando información que
> en ese momento no existía. Tenelo presente antes de construir una señal sobre
> él.

---

## Momento

### RSI

Índice de fuerza relativa, de 0 a 100. Compara la magnitud de las subidas
recientes contra la de las bajadas.

La lectura clásica es: por encima de 70, sobrecomprado; por debajo de 30,
sobrevendido. En la práctica, un activo en tendencia fuerte puede quedarse
semanas por encima de 70 sin corregir, así que conviene comprobar contra la
historia del propio activo antes de fijar umbrales — para eso está la solapa
**Posicionamiento Histórico** de
[Análisis de Activo](/manual/analisis-de-activo).

---

## Volatilidad

### Régimen de volatilidad

**Categórico.** Combina dos cosas: qué tan alta es la volatilidad y hace cuánto
que está así.

| Componente | Valores |
|---|---|
| Nivel | `baja`, `normal`, `alta`, `extrema` |
| Duración | `corta`, `media`, `larga` |

Se combinan en etiquetas como `alta_larga` (volatilidad alta sostenida) o
`extrema_corta` (un pico reciente). La distinción importa: un pico puntual y un
régimen alto sostenido son situaciones distintas aunque el nivel coincida.

Se configura en [Volatilidad ATR](/manual/volatilidad-atr).

### Percentil de ATR

Dónde cae la volatilidad actual dentro de la historia del propio activo, de 0 a
100. Un valor de 90 significa que solo el 10% de los días de su historia fueron
más volátiles.

Es directamente comparable entre activos, porque cada uno se mide contra sí
mismo.

### ATR %

Cuánto se mueve un activo en un día típico, expresado como porcentaje de su
precio. Un 3% quiere decir que el recorrido diario habitual es de más o menos
tres por ciento del valor del activo.

Se calcula en las tres cadencias (diaria, semanal y mensual) y guarda historia,
así que podés ver en [Posicionamiento Histórico](/manual/analisis-de-activo) si
un activo está hoy más movido o más quieto que de costumbre.

No confundirlo con el percentil de arriba: el percentil te dice *en qué lugar de
su propia historia* está la volatilidad de hoy; el ATR % te dice *cuánto se
mueve*, en porcentaje de precio. Uno es una posición, el otro una magnitud.

La diferencia con el ATR que se dibuja en el gráfico es que ese está en pesos o
dólares: sirve para leerlo sobre el precio, pero no para comparar. Un activo de
$10 y otro de $1.000 no se pueden comparar por su ATR en moneda, y tampoco un
mismo activo consigo mismo si su precio cambió mucho a lo largo de los años.
Dividir por el precio arregla las dos cosas.

Usa el mismo período que configurás en
[Volatilidad ATR](/manual/volatilidad-atr).

---

## Volumen

### Volumen relativo

El volumen de la rueda comparado con el promedio de las **20 ruedas
anteriores**. Un valor de 1 es un día normal para ese activo, 3 es el triple de
lo habitual y 0,4 es una rueda floja.

Está armado para ser comparable entre activos: cada uno se mide contra su propio
promedio, así que un papel que opera mil acciones por día y otro que opera diez
millones dan los dos alrededor de 1 en una rueda cualquiera. El volumen a secas
no sirve para eso.

Se usa sobre todo para separar movimientos con respaldo de los que no lo tienen:
una ruptura de resistencia con volumen relativo alto pesa mucho más que la misma
ruptura en una rueda floja.

El promedio deja afuera la rueda que se está midiendo, a propósito: si la
incluyera, un día de volumen excepcional levantaría su propio promedio y se
disimularía solo, justo el día que interesa detectar.

> **No todos los activos lo tienen.** Los activos calculados (los sintéticos y
> las conversiones de moneda) son un cociente entre dos precios, y un cociente no
> tiene volumen propio: para ellos este indicador queda vacío. Si armás una
> estrategia que puntúe por volumen, agregá también una condición sobre él en el
> filtro de elegibilidad — si no, los activos sin el dato quedan igual en el
> ranking, puntuados solo con el resto de los componentes, y eso los favorece.
> Ver [Estrategias](/manual/configuracion-estrategias).

Solo tiene versión diaria y guarda historia.

---

## Drawdown

### Drawdown actual

Cuánto cayó el precio desde su máximo previo, en porcentaje. Siempre negativo o
cero. Cero significa que el activo está en su máximo.

### Drawdown % (con historia)

La misma medida que el drawdown actual, pero guardada para **todos los días** de
la historia del activo, no solo para hoy. El valor de hoy de los dos coincide
siempre; lo que agrega este es el pasado.

Sirve para responder preguntas que el valor suelto no contesta: cuánto tiempo
pasó el activo lejos de sus máximos, si la caída de hoy es habitual o excepcional
para él, o qué tan seguido llega a un −20%. En
[Posicionamiento Histórico](/manual/analisis-de-activo) lo ves como distribución:
qué porcentaje de su historia pasó en cada franja de caída.

Solo tiene versión diaria. El drawdown se mide siempre contra el máximo
acumulado desde el principio, así que verlo en cadencia semanal o mensual sería
mirar la misma curva con menos puntos, no una lectura distinta.

### Drawdowns máximos

Las tres lecturas más profundas del drawdown diario en la historia del activo.
Ojo: no son tres caídas distintas — la segunda y la tercera suelen ser días
vecinos del mismo fondo. La más profunda sirve de referencia para dimensionar
la caída actual: un −15% es poco en un activo cuyo peor drawdown fue −70%, y
mucho en uno que nunca cayó más de −20%.

Estos indicadores no tienen configuración. La pantalla
[Drawdowns](/manual/drawdowns) ajusta otra cosa: la profundidad mínima de los
episodios que se marcan sobre el gráfico de Análisis de Activo.

---

## Retornos

Variación porcentual del precio: **diaria** (contra la rueda anterior),
**mensual**, **trimestral** y **anual** (desde el inicio del mes, del trimestre
y del año calendario en curso) y **52 semanas** (móvil: contra el precio de un
año atrás). La anual no es "los últimos doce meses" — para eso está la de 52
semanas.

### Fuerza relativa a 52 semanas

El retorno del activo comparado con el de su referencia en el mismo período. Es
la medida de si le está ganando o perdiendo al mercado, que es una pregunta
distinta a si subió o bajó.

Un activo puede tener retorno negativo y buena fuerza relativa: cayó, pero menos
que todo lo demás.

### Posición en el rango de 52 semanas

De 0 a 100: dónde está el precio de hoy dentro del rango en el que se movió
durante el último año. 0 es el piso de las 52 semanas, 100 el techo, 50 la mitad
exacta.

Responde algo que ningún otro indicador contesta: si el activo está apoyado sobre
su piso anual o pegado a su techo. No confundirlo con el drawdown, que mide
contra el **máximo de toda la historia**. Las dos lecturas pueden ser opuestas al
mismo tiempo y las dos son ciertas: una empresa que valía $1.000 hace diez años,
cayó a $50 y este año se recuperó hasta $100 tiene un drawdown de −90% (muy lejos
de su máximo histórico) y a la vez posición 100 (en el techo de su último año).
El drawdown te cuenta de dónde viene; este te cuenta cómo viene.

Necesita un año completo de cotizaciones: los activos con menos historia no
tienen valor hasta cumplirlo.

Solo tiene versión diaria y guarda historia, así que en
[Posicionamiento Histórico](/manual/analisis-de-activo) podés ver cuánto tiempo
pasó el activo en cada zona de su rango.

---

## Soportes y resistencias

Distancia porcentual al soporte y a la resistencia más cercanos, detectados por
pivotes. Se configuran en
[Soporte / Resistencia](/manual/soporte-resistencia).

---

## Fundamentales

Solo tienen valor para activos con datos fundamentales cargados: las acciones
sí, los índices y la mayoría de los sintéticos no.

| Indicador | Qué mide |
|---|---|
| **P/E TTM** | Precio sobre ganancias de los últimos doce meses. |
| **P/B** | Precio sobre valor libro. |
| **P/S TTM** | Precio sobre ventas de los últimos doce meses. |
| **Margen neto / bruto / operativo** | Qué porcentaje de las ventas queda como ganancia en cada nivel. |
| **Deuda / Patrimonio** | Cuánto se apalanca la empresa. |
| **Crecimiento de ingresos, de ganancia por acción, de ganancia neta (interanual)** | Variación contra el mismo período del año anterior. |
| **Variación del P/E (interanual)** | Si la empresa se abarató o encareció en términos de múltiplo. |
| **ROIC** | Retorno sobre el capital invertido, con la ganancia de los últimos doce meses. |

> **Los fundamentales se actualizan por trimestre, no todos los días.** El valor
> de hoy suele ser el del último balance publicado. Un cambio brusco no
> significa que la empresa cambió hoy: significa que se publicó un balance
> nuevo. Ver
> [Actualización de fundamentales](/manual/actualizacion-de-fundamentales).
