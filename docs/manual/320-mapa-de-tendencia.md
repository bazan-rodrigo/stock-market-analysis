---
slug: mapa-de-tendencia
title: Mapa de Tendencia de Mercado
chapter: 3. Análisis
order: 320
roles: invitado
page: /market-map
---

Mientras [Análisis de Activo](/manual/analisis-de-activo) responde "¿cómo está
este activo?", esta pantalla responde la pregunta de arriba: **¿qué partes del
mercado están funcionando hoy?**. No hay que elegir nada: la pantalla muestra
todos los grupos de una dimensión, ordenados por su tendencia.

Es el punto de partida natural de una sesión de análisis. Primero mirás qué
sectores o mercados vienen bien, y recién después bajás a los activos.

## Las cinco solapas

Cada solapa es una forma distinta de agrupar los mismos activos:

| Solapa | Agrupa por |
|---|---|
| **Sectores** | El sector económico del activo. |
| **Industrias** | El desglose fino dentro del sector. |
| **Países** | El país al que pertenece el activo. |
| **Tipo de Instrumento** | Acción, ETF, índice, bono, sintético. |
| **Mercados** | La plaza donde cotiza. |

Un mismo activo pertenece a **varias** dimensiones a la vez, así que las solapas
no son particiones alternativas del mismo total: son cinco cortes distintos del
mismo universo. No tiene sentido sumar cantidades entre solapas.

## Qué es el score de tendencia

Cada activo del sistema tiene detectado un **régimen técnico**: alcista fuerte,
alcista, lateral, bajista, bajista fuerte, más los matices "nacientes" para los
regímenes recién iniciados. A cada régimen le corresponde un puntaje entre
**+100 y −100**, y el score del grupo es el **promedio simple** de los puntajes
de todos sus activos.

Un score de +70 no significa "el sector subió 70%": significa que, en promedio,
sus activos están en regímenes claramente alcistas.

Las categorías con las que se etiqueta ese número son:

| Etiqueta | Rango del score |
|---|---|
| **Alcista** | 50 o más |
| **Mejorando** | 20 a 49 |
| **Lateral** | −19 a 19 |
| **Deteriorando** | −20 a −49 |
| **Bajista** | −50 o menos |

## La tabla

A la izquierda, todos los grupos de la solapa activa, **ordenados de mayor a
menor Score Diario**:

| Columna | Qué muestra |
|---|---|
| **Grupo** | El nombre del sector, país, mercado, etc. |
| **N** | Cuántos activos aportaron al promedio. |
| **Score Diario** | Régimen medido sobre barras diarias. |
| **Score Semanal** | Régimen medido sobre barras semanales. |
| **Score Mensual** | Régimen medido sobre barras mensuales. |

Un guión (**—**) quiere decir que ese grupo no tiene score para esa columna
—típicamente porque ninguno de sus activos tiene el indicador de régimen
calculado todavía.

### La columna N es la que decide cuánto creerle al resto

Un grupo con **N = 2** puede marcar "Alcista +100" y no estar diciendo nada
sobre el mercado: son dos activos que suben. Antes de sacar una conclusión de
una fila, mirá cuántos activos la sostienen. Los grupos chicos son ruido, y en
la solapa **Industrias** —que es la más granular— hay muchos.

Además el promedio es **simple**: cada activo pesa lo mismo, sin importar su
tamaño ni su volumen. Un sector puede figurar "Alcista" con sus dos empresas
más grandes cayendo, si tiene ocho chicas subiendo.

## El gráfico de cuadrantes

A la derecha, los mismos grupos como puntos. El eje horizontal es el **Score
Mensual** (tendencia de fondo) y el vertical el **Score Diario** (la dirección
reciente). El **tamaño del punto** refleja la cantidad de activos del grupo, así
que el ruido de los grupos chicos se ve a simple vista. Pasando el mouse por un
punto aparecen los tres scores y el N.

| Cuadrante | Posición | Qué significa |
|---|---|---|
| **Alcista confirmado** | Arriba a la derecha | Tendencia de fondo alcista y dirección reciente que acompaña. |
| **Rebotando** | Arriba a la izquierda | Fondo todavía bajista, pero lo reciente ya dio vuelta. Puede ser un piso o un rebote pasajero. |
| **Corrigiendo** | Abajo a la derecha | Fondo alcista, pero lo reciente se dio vuelta. La primera señal de deterioro. |
| **Bajista confirmado** | Abajo a la izquierda | Todo mal en las dos escalas. |

Los grupos que no tienen **a la vez** score diario y mensual no se dibujan,
aunque sí figuren en la tabla. Si contás menos puntos que filas, es eso.

### La sutileza que confunde: "Diario" no quiere decir "de hoy"

Es el malentendido más común de esta pantalla. Los tres scores son **del mismo
día**: ninguno es más viejo o más nuevo que los otros. Lo que cambia es el
**tamaño de las barras** sobre las que se detectó el régimen, y con eso, el
horizonte que mide cada uno.

Por la configuración por defecto, el régimen diario usa una media de 200 ruedas,
el semanal una de 50 semanas y el mensual una de 20 meses. Contado en tiempo
calendario, el **diario es el más corto y el más reactivo**, y el **mensual el
más lento y estructural**. Por eso el gráfico pone el mensual en el eje
horizontal —el fondo— y el diario en el vertical —el movimiento.

Leído así, el cuadrante deja de ser una etiqueta y pasa a ser una comparación
entre dos horizontes: **Corrigiendo** es "el fondo todavía es bueno pero lo de
corto plazo se dio vuelta", y **Rebotando** es exactamente lo contrario.

> Estos scores describen el **régimen de tendencia**, no el rendimiento. Un
> grupo puede estar en **Alcista** y haber perdido plata en el mes: el régimen
> mide la estructura de la tendencia, no el retorno acumulado.

## De dónde salen los datos

La pantalla no calcula nada al abrirse: lee los scores ya guardados de la
**última fecha disponible**, que el sistema refresca en el proceso diario y
después de cada actualización de indicadores (ver
[Cómo se calcula todo](/manual/conceptos-pipeline)).

Como consecuencia, un activo recién agregado **no aparece en estos promedios**
hasta que se le calculen los indicadores, y un grupo sin ningún activo con
indicadores directamente no figura en la lista.
