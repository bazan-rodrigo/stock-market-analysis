---
slug: activos-y-grupos
title: Activos, sintéticos y grupos
chapter: 2. Conceptos centrales
order: 210
roles: invitado
---

Todo en el sistema cuelga de un **activo**: los precios, los indicadores, las
señales, el ranking, las carteras. Vale la pena saber qué es exactamente, porque
no todos los activos se comportan igual.

## Qué define a un activo

Un activo se identifica por su **ticker**, que es único en todo el sistema y no
se puede repetir. Además tiene:

| Dato | Para qué se usa |
|---|---|
| **Nombre** | Descripción legible. Es lo que ves junto al ticker en los selectores. |
| **Fuente de precios** | De dónde salen las cotizaciones: descargadas de un proveedor externo, o **calculadas** por el propio sistema. Esto es lo que distingue a un activo normal de un sintético. |
| **Moneda** | En qué moneda cotiza. Es un dato del activo, pero **no** es un criterio de agrupación (ver más abajo). |
| **País, mercado, industria, sector, tipo de instrumento** | Los cinco **grupos**. Ninguno es obligatorio. |
| **Benchmark** | Otro activo contra el cual compararlo. Se puede fijar activo por activo, y también a nivel de mercado (todos los activos de ese mercado quedan referidos a él). |
| **Fuente de fundamentales** | De dónde salen balances y ratios. Solo aplica a activos que los tengan. |

> Un activo que está configurado como benchmark de otros activos o de un mercado
> **no se puede borrar** hasta que reasignes ese benchmark. Y cuando se borra un
> activo, se borra con toda su historia: precios, indicadores y fundamentales.

## Los tres tipos de activo

### 1. Normales

Los que se descargan de una fuente externa. Tienen apertura, máximo, mínimo,
cierre y volumen reales.

### 2. Sintéticos (calculados)

Son activos cuyo precio **no se descarga: se calcula** a partir de los precios de
otros activos. Para todo el resto del sistema son activos como cualquier otro —
tienen indicadores, entran a las señales y compiten en el ranking.

Hay cuatro formas de armarlos:

| Tipo | Qué calcula | Para qué sirve |
|---|---|---|
| **Ratio** | Un conjunto de activos dividido por otro. | La pregunta clásica «¿qué rinde más, A o B?». Un ratio subiendo significa que el numerador le está ganando al denominador. Sirve para fuerza relativa contra un índice, o para el precio de un activo medido en otro. |
| **Promedio ponderado** | El promedio de varios activos, con el peso que le des a cada uno. | Un índice propio: «el promedio de los cuatro bancos». |
| **Suma ponderada** | La suma de varios activos, con pesos. | Canastas y spreads: una combinación cuyo valor absoluto tiene sentido. |
| **Índice base** | Un índice que arranca en un valor base en una fecha base, y desde ahí evoluciona con el promedio de sus componentes. | Comparar la evolución de una canasta desde un punto de partida común, en vez de mirar precios de escalas distintas. |

Tres cosas que conviene tener presentes con los sintéticos:

- **Solo tienen precio en las fechas en que cotizaron TODOS sus componentes.** Si
  uno de los componentes no operó ese día, el sintético no tiene valor ese día.
  Cuantos más componentes, más se recorta el calendario.
- **No tienen volumen** y, salvo excepciones, **no tienen fundamentales**: son un
  precio construido, no un instrumento que se opera.
- **Un sintético puede ser componente de otro sintético.** El sistema los calcula
  en orden de dependencia, así que el de arriba siempre lee precios ya
  actualizados.

### 3. Conversiones de moneda

Son un caso particular y automatizado del sintético de tipo ratio, y merecen
explicación aparte porque el sistema los crea **de a cientos, solo**.

La idea: elegís una moneda y un activo que funcione como **divisor** de esa
moneda (típicamente el tipo de cambio). A partir de ahí, por cada activo que
cotice en esa moneda el sistema crea un sintético:

```
activo convertido = activo base / divisor
```

que es el mismo activo **valuado en la moneda del divisor**. El ticker se arma
concatenando el del activo base y el del divisor, y el nombre queda como el del
base con el divisor entre paréntesis, para que se reconozcan de un vistazo.

**Por qué hereda los grupos de su activo base.** Al crearse, la conversión copia
el país, el mercado, la industria, el sector y el tipo de instrumento del activo
base; lo único que cambia es la moneda, que pasa a ser la del divisor. El motivo
es que **es el mismo activo, medido en otra unidad**: un banco visto en dólares
sigue siendo del sector bancos y del mismo mercado. Si no heredara los grupos,
quedaría fuera de todos los agregados por sector y sería invisible para cualquier
filtro de estrategia que trabaje por sector o mercado — es decir, existiría pero
no participaría de nada.

> Las conversiones se crean solo para activos **normales**. Un sintético no
> genera conversiones de moneda propias, para no encadenar cálculos sobre
> cálculos indefinidamente.

## Los grupos

Hay exactamente **cinco** dimensiones de agrupación:

| Grupo | Notas |
|---|---|
| **Sector** | El más usado. |
| **Industria** | Más fina que el sector; cada industria pertenece a un sector. |
| **Mercado** | Dónde cotiza. Cada mercado pertenece a un país y puede definir un benchmark para todos sus activos. |
| **País** | |
| **Tipo de instrumento** | Acción, índice, ETF, etc. |

La **moneda no es un grupo**: podés filtrar por ella, pero no genera agregados.

Los grupos sirven para dos cosas distintas:

**1. Filtrar y segmentar.** En el screener y en el filtro de elegibilidad de una
estrategia podés pedir «solo el sector energía» o «solo este mercado».

**2. Alimentar los agregados de grupo.** Esta es la importante. Todos los días,
para cada grupo, el sistema promedia el **régimen de tendencia** de los activos
que lo integran —en escala diaria, semanal y mensual— y guarda ese promedio junto
con la cantidad de activos que lo componen. Ese promedio es exactamente lo que
consumen las **señales de grupo** descritas en
[Cómo se calcula todo](/manual/conceptos-pipeline): es lo que permite preguntar
«¿el sector de este activo viene bien?» y usar la respuesta como componente de
una estrategia.

Dos detalles de cómo se arma ese promedio:

- Solo aportan los activos que **tienen el régimen de tendencia calculado** ese
  día. Un activo recién dado de alta, o uno sin suficiente historia, no arrastra
  el promedio hacia abajo: simplemente no cuenta todavía.
- Un activo **sin sector asignado** no aporta a ningún sector, pero sí sigue
  aportando a su país, su mercado y su tipo de instrumento. Cada dimensión se
  resuelve por separado.

> **Cambiar la agrupación de un activo afecta la historia.** Los agregados se
> calculan con los grupos tal como están definidos en el momento del cálculo, así
> que la historia ya calculada conserva la agrupación anterior. Lo mismo pasa al
> **incorporar activos nuevos**: pasan a integrar los agregados de sus grupos, y
> eso desactualiza las señales de grupo y las estrategias que las usan en toda la
> historia. En ambos casos hace falta un **recálculo completo** para que quede
> consistente; la aplicación te avisa cuándo corresponde.
