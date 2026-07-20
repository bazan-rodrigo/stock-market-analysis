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

Las condiciones se agrupan en bloques **Y** / **O**, y los bloques se pueden
anidar unos dentro de otros. El activo entra al ranking solo si el árbol
completo da verdadero.

## Tipos de operando

Cualquiera de los dos lados de una condición puede ser:

| Tipo | Qué aporta | Ejemplo |
|---|---|---|
| **Indicador** | El valor del indicador para ese activo | el RSI diario |
| **Señal** | El puntaje que da una señal para ese activo | el score de tu señal de tendencia |
| **Atributo** | Una característica del activo | su sector |
| **Valor fijo** | Un número, un texto o una lista que escribís vos | `70`, `bullish`, una lista de sectores |

Los cinco atributos disponibles son **sector**, **mercado**, **industria**,
**país** y **tipo de instrumento** — los mismos cinco que sirven para agrupar,
ver [Activos, sintéticos y grupos](/manual/activos-y-grupos).

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
| `not_in` | No está en una lista |

`in` y `not_in` son los que te ahorran repetir condiciones: en vez de
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

### Comparar tipos incompatibles da falso

Comparar un número contra un texto no da error en la corrida: da **falso**. Al
validar la estrategia sí se reporta como problema, así que conviene revisar los
avisos de validación antes de confiar en un filtro nuevo.

### Los indicadores se leen "a la fecha más reciente disponible"

Cuando el filtro evalúa un indicador para una fecha, toma **el último valor
disponible en esa fecha o antes**, no exige que haya uno exactamente ese día.
Esto es lo que permite que un indicador semanal o mensual —que se guarda con
fecha de fin de período— sirva para filtrar en cualquier día.

Los puntajes de señales, en cambio, se leen **con fecha exacta**, igual que en
el scoring.

> **La opción de resolución "actual" introduce sesgo a propósito.** Una
> condición puede configurarse para leer el valor **vigente** del indicador en
> lugar del que correspondía a la fecha evaluada. Eso significa usar información
> del futuro al mirar el pasado, y **cualquier backtest hecho así da resultados
> irrealmente buenos**. Existe solo como herramienta de diagnóstico; la interfaz
> lo marca cuando está activo. No la uses para evaluar una estrategia que
> pensás operar.

## Relación con el score

El filtro decide **quién participa**; los componentes ponderados deciden **en
qué orden**. Son dos mecanismos independientes: una señal puede usarse en el
filtro, en el score, en los dos o en ninguno.

Un activo que no pasa el filtro **no aparece en el ranking**, sin importar qué
puntaje habría sacado. No aparece con score bajo: no aparece.
