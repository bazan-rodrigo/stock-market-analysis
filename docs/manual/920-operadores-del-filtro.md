---
slug: operadores-del-filtro
title: Referencia de operadores del filtro
chapter: Apéndices
order: 920
roles: analista
---

Referencia de consulta del filtro de elegibilidad de las estrategias. Para
aprender a armarlo, empezá por
[Estrategias — crear y editar](/manual/configuracion-estrategias); esta sección
es para consultar mientras lo hacés.

## Estructura de una condición

Toda condición tiene la misma forma:

```
<operando izquierdo>  <operador>  <operando derecho>
```

Las condiciones se agrupan en bloques **AND (todas)** / **OR (alguna)** —en la
fórmula en texto se muestran como **Y** / **O**—, y los bloques se pueden
anidar unos dentro de otros. El activo entra al ranking solo si el árbol
completo da verdadero.

## Tipos de operando

El lado izquierdo es siempre un indicador, una señal o un atributo. El lado
derecho es normalmente un valor fijo; en comparaciones numéricas también puede
ser otro indicador u otra señal. Los tipos:

| Tipo | Qué aporta | Ejemplo |
|---|---|---|
| **Indicador** | El valor del indicador para ese activo | el RSI diario |
| **Señal** | El puntaje que da una señal para ese activo | el score de tu señal de tendencia |
| **Atributo** | Una característica del activo | su sector |
| **Valor fijo** | Un número que escribís vos, o un valor (o lista de valores) que elegís del desplegable | `70`, `bullish`, una lista de sectores |

Los atributos disponibles son:

| Atributo | De dónde salen sus valores |
|---|---|
| **Sector**, **Mercado**, **Industria**, **País**, **Tipo de instrumento** | Las mismas cinco tablas que sirven para agrupar, ver [Activos, sintéticos y grupos](/manual/activos-y-grupos) |
| **Moneda** | La moneda en la que cotiza el activo |
| **Benchmark** | Los activos que **hoy son benchmark de alguien** (no la lista completa de activos) |
| **Tipo de sintético** | La fórmula del activo calculado: Ratio, Promedio ponderado, Suma ponderada, Índice base |

### Cada lista trae un "(sin …)"

Todos los atributos pueden estar vacíos: hay activos sin sector, sin país, sin
benchmark. Por eso cada desplegable de valores arranca con su propio hueco
—**(sin sector)**, **(sin benchmark)**, **(no sintético)**— que se elige como
cualquier otro valor.

Existe por lo que se explica más abajo: un dato vacío no cumple ninguna
condición, así que sin ese valor no habría forma de escribir "los que no tienen
sector". Con él la relación se puede pedir en los dos sentidos:

```
Benchmark  !=  (sin benchmark)      solo los que tienen benchmark
Sector      =  (sin sector)         solo los que quedaron sin clasificar
```

La primera es la forma de sacar del ranking a los activos que **nunca van a
tener calculado** un indicador que depende del benchmark —como Relative
Strength 52W—, sin quedar a merced de que el faltante se disimule en el
puntaje: el filtro descarta, pero el score reparte el peso del componente
faltante entre los demás, y así el activo sin dato termina midiéndose con otra
fórmula.

> **Ojo con el `!=`:** como el vacío ahora es un valor, `Sector != Tecnología`
> **incluye** a los activos sin sector. Es lo correcto —"no es tecnología" es
> verdad para el que no tiene ninguno— pero si querés además exigir que tenga
> sector, sumá la condición `Sector != (sin sector)`.

### Sacar del universo los activos calculados

**Tipo de sintético = (no sintético)** deja afuera a todos los activos
calculados. Importa cuando usás conversión de divisas: esa función crea **un
sintético por cada activo** en esa moneda, y esos duplicados compiten en el
mismo ranking que su original. Un sintético de conversión aparece como
**Ratio**, igual que un ratio que hayas armado a mano — el filtro no los
distingue entre sí.

## Operadores

Cuáles podés usar depende de si estás comparando números o categorías.

### Para valores numéricos

Indicadores numéricos, puntajes de señales y números fijos.

| Operador | Significa |
|---|---|
| `=` | Igual a |
| `!=` | Distinto de |
| `>` | Mayor que |
| `>=` | Mayor o igual que |
| `<` | Menor que |
| `<=` | Menor o igual que |

### Para categorías y atributos

Indicadores que devuelven una categoría (como el régimen de tendencia) y los
atributos del activo.

| Operador | Significa |
|---|---|
| `=` | Es exactamente |
| `!=` | No es |
| `in` | Está dentro de una lista |
| `not in` | No está en una lista |

`in` y `not in` son los que te ahorran repetir condiciones: en vez de
"sector = Energía **O** sector = Bancos **O** sector = Minería", ponés
`sector in [Energía, Bancos, Minería]`.

## Tres reglas que cambian el resultado

### Un dato faltante nunca cumple la condición

Si el activo no tiene ese indicador calculado para esa fecha, la condición da
**falso** y el activo queda afuera. No se lo deja pasar "por las dudas".

Es deliberado: un filtro que dejara pasar lo que no pudo evaluar sería una
trampa silenciosa —creerías estar filtrando por algo que en realidad no se está
aplicando—. La contracara práctica es que **un activo con historia corta queda
afuera del ranking**, y eso a veces se lee como un error cuando en realidad el
filtro está funcionando bien.

### Comparar tipos incompatibles no se puede guardar

Un número contra un texto no se compara: al guardar la estrategia, la
validación lo rechaza como error y el filtro no queda guardado hasta que lo
corrijas.

### Los indicadores se leen "a la fecha más reciente disponible"

Cuando el filtro evalúa un indicador para una fecha, toma **el último valor
disponible en esa fecha o antes** —no exige que haya uno exactamente ese día—,
con un límite: un valor de más de 45 días atrás ya no cuenta (así un activo
que dejó de cotizar no sigue pasando el filtro para siempre). Esto es lo que
permite que un indicador semanal o mensual —que se guarda con
fecha de fin de período— sirva para filtrar en cualquier día.

Los puntajes de señales, en cambio, se leen **con fecha exacta**, igual que en
el scoring.

> **Los operandos sin historia introducen sesgo a propósito.** Algunos
> indicadores guardan solo su valor vigente, sin serie histórica. Cuando una
> condición usa uno, no hay nada que elegir: en fechas pasadas el filtro lee
> **el valor de hoy**. Eso es usar información del futuro al mirar el pasado, y
> **cualquier backtest hecho así da resultados irrealmente buenos**. El
> constructor lo avisa en la propia condición («⚠ sin historia») y la pantalla
> de cálculo marca los resultados como diagnóstico. No evalúes con esos
> operandos una estrategia que pensás operar.

## Relación con el score

El filtro decide **quién participa**; los componentes ponderados deciden **en
qué orden**. Son dos mecanismos independientes: una señal puede usarse en el
filtro, en el score, en los dos o en ninguno.

Un activo que no pasa el filtro **no aparece en el ranking**, sin importar qué
puntaje habría sacado. No aparece con score bajo: no aparece.
