---
slug: rotacion-relativa
title: Rotación Relativa (RRG)
chapter: 3. Análisis
order: 330
roles: invitado
page: /rrg
---

El RRG (*Relative Rotation Graph*) responde una pregunta que ninguna otra
pantalla contesta: **¿qué activos le están ganando al mercado, y cuáles están
empezando a hacerlo?**. Todo lo que se ve acá es **relativo a un benchmark**;
nada es precio absoluto.

Es la herramienta de rotación: sirve para decidir *dónde* pararse dentro de un
universo, no para decidir si comprar o vender el universo entero.

## Los controles

| Control | Para qué sirve |
|---|---|
| **Benchmark** | El activo contra el que se mide todo lo demás. Es la decisión más importante de la pantalla. |
| **Cola (semanas)** | Cuántas semanas de recorrido se dibujan detrás de cada activo. De 1 a 30, arranca en 12. |
| **Agregar activo** | Buscador para sumar activos al gráfico de a uno. |
| **+** | Confirma el activo elegido en el buscador. |
| **Limpiar** | Vacía el gráfico y la tabla. El benchmark queda elegido. |
| **×** (en la tabla) | Saca ese activo del gráfico. |

Al elegir un benchmark, la pantalla **carga sola** los activos que lo tienen
asignado como benchmark propio y los de los mercados que lo usan como
referencia. Ese autocompletado es el punto de partida esperado: después sumás o
sacás a mano. El benchmark nunca se dibuja a sí mismo (estaría fijo en el
centro).

Mover el slider de la cola es **instantáneo**: el sistema trae siempre 30
semanas y el control solo recorta lo que se muestra. Podés barrerlo de punta a
punta para ver cómo se va formando el recorrido sin esperar nada.

El símbolo **⚠️** delante de un activo en los buscadores marca que la
verificación automática le detectó discrepancias de cálculo o datos de origen
sospechosos. No impide usarlo, pero conviene mirarlo con desconfianza.

## Cómo leer el gráfico

El centro del gráfico es el punto **100 / 100**, y es el benchmark. Un activo
parado ahí se mueve exactamente igual que su referencia.

- El eje horizontal (**JdK RS-Ratio**) mide **cuán fuerte** está el activo
  contra el benchmark. A la derecha del 100, le está ganando.
- El eje vertical (**JdK RS-Momentum**) mide **hacia dónde va esa fuerza**.
  Arriba del 100, la ventaja se está agrandando; abajo, se está achicando.

De ahí salen los cuatro cuadrantes, que en pantalla aparecen con sus nombres
clásicos en inglés:

| Cuadrante | Posición | Situación |
|---|---|---|
| **Leading** | Arriba a la derecha | Le gana al benchmark y cada vez por más. El liderazgo confirmado. |
| **Weakening** | Abajo a la derecha | Todavía le gana, pero la ventaja se achica. Primera advertencia. |
| **Lagging** | Abajo a la izquierda | Pierde contra el benchmark y sigue empeorando. |
| **Improving** | Arriba a la izquierda | Todavía pierde, pero está recuperando. Es donde aparecen los candidatos tempranos. |

### El recorrido es lo que importa, no el punto

Un activo en **Improving** y otro en **Weakening** pueden estar a la misma
distancia del centro y sin embargo contar historias opuestas: uno viene
subiendo y el otro bajando. Por eso la cola —el rastro de semanas anteriores—
es el corazón del gráfico y no un adorno. Los puntos viejos se dibujan chicos y
transparentes, y el más reciente es el **cuadrado con el ticker**: la cola se
lee siempre *desde lo tenue hacia lo sólido*.

La rotación típica gira en **sentido horario**:

```
Improving  →  Leading  →  Weakening  →  Lagging  →  Improving
```

Un activo que entra a Improving y sigue girando hacia Leading está completando
el ciclo normal. Pero **la rotación no siempre se completa**, y ahí está la
mitad del valor del gráfico: un recorrido que sube hacia Improving y se da
vuelta hacia Lagging sin llegar nunca a cruzar el eje vertical es un intento de
recuperación que falló. Ver ese giro incompleto es información tan útil como
ver el ciclo entero.

La **longitud** de la cola también dice algo: colas largas son activos rotando
rápido; puntos amontonados son activos que se mueven prácticamente igual que el
benchmark, sin historia relativa que contar.

> **El error de lectura más frecuente.** Un activo en **Leading** puede estar
> **cayendo en precio**: si el benchmark cae más, la fuerza relativa sube igual.
> Y uno en **Lagging** puede estar subiendo, si el mercado sube más. El RRG
> nunca dice si algo gana o pierde plata — dice quién le gana a quién. Para el
> precio real está [Análisis de Activo](/manual/analisis-de-activo).

### Qué significan los números

Los valores de los ejes no son porcentajes ni retornos: cada activo se compara
**contra su propia historia del último año**. Un RS-Ratio de 103 quiere decir
"la fuerza relativa de este activo está bastante por encima de lo habitual
*para él*".

Esto tiene una consecuencia práctica: dos activos en el mismo lugar del gráfico
están igual de extremos **respecto de sí mismos**, no necesariamente igual de
fuertes en términos absolutos. El RRG es un ranking de *anomalía relativa*, y
esa es justamente la razón por la que activos muy distintos entre sí pueden
compararse en el mismo cuadro.

## La tabla lateral

Muestra los activos cargados con su color, **Ticker**, **Nombre**, la
**Semana** del último punto y sus valores de **RS-Ratio** y **RS-Mom.** actuales
—los mismos números del cuadrado del gráfico, para leerlos sin pasar el mouse.

Los activos que aparecen **atenuados y con guiones** son los que se pidieron
pero no se pudieron calcular. El motivo de cada uno se detalla en el aviso
amarillo de arriba, y casi siempre es uno de estos dos:

- **Sin precios disponibles** — el activo no tiene serie cargada.
- **Historial insuficiente** — le faltan semanas. El cálculo necesita unas
  **92 semanas** de historia compartida con el benchmark (cerca de dos años):
  una parte se consume en el suavizado y otra en la normalización, antes de
  poder dibujar el primer punto.

Ese piso explica por qué activos nuevos, recién listados o sintéticos de
creación reciente no aparecen aunque los agregues. No es un error: no hay
historia suficiente para que el punto signifique algo.

## Dos decisiones que cambian el resultado

**El benchmark elegido cambia todo el gráfico.** Un sector puede estar en
Leading contra el índice general y en Lagging contra su propio índice
sectorial, y ambas lecturas son correctas: responden preguntas distintas
("¿le gana al mercado?" vs. "¿le gana a sus pares?"). Cuando compares dos
corridas, asegurate de que sea el mismo benchmark.

**El gráfico es semanal.** Cada punto es el cierre de una semana, así que el
punto más reciente corresponde a la semana **en curso** y se va a mover hasta
que cierre. Como en el resto del sistema, el último dato es preliminar (ver
[Cómo se calcula todo](/manual/conceptos-pipeline)); no leas un giro de
cuadrante recién nacido como un hecho consumado.
