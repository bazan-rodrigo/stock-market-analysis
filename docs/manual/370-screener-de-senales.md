---
slug: screener-de-senales
title: Screener de Señales
chapter: 3. Análisis
order: 370
roles: invitado
page: /senales
---

Es la pantalla que responde la pregunta más frecuente del sistema: **¿qué
activos están mejor posicionados hoy según mi estrategia?** Mientras
[Análisis de Activo](/manual/analisis-de-activo) mira un activo en
profundidad, acá mirás todo el universo de una vez, ordenado.

La pantalla no calcula nada al abrirla: lee el ranking ya calculado para la
estrategia y la fecha que elijas (el porqué está en
[Cómo se calcula todo](/manual/conceptos-pipeline)).

---

## Filtrar

| Control | Para qué sirve |
|---|---|
| **Estrategia** | Define todo: quién entra al listado, con qué señales se puntúa y con qué pesos. Es lo primero que hay que elegir; sin estrategia no hay resultados. Aparecen las estrategias públicas más las tuyas. |
| **Fecha** | El día del ranking. Al elegir una estrategia se posiciona sola en la **fecha más reciente que tenga resultados calculados** para esa estrategia. |
| **Sector** | Restringe a un sector. Las opciones son solo los sectores que efectivamente tienen activos en el resultado de esa fecha. |
| **Mercado** | Ídem, por mercado. |
| **Buscar** | Ejecuta la consulta. Al lado aparece la cantidad de activos encontrados. |

Cambiar la estrategia, la fecha, el sector o el mercado **no actualiza la tabla
sola**: hay que apretar **Buscar**. Es a propósito, para que puedas armar la
combinación completa antes de disparar la consulta.

> Si el listado sale vacío o mucho más corto de lo esperado, lo más probable es
> que la fecha elegida no tenga resultados calculados para esa estrategia, o
> que el filtro de elegibilidad de la estrategia esté dejando afuera a casi
> todos. Un activo que no pasa el filtro **no aparece con score bajo: no
> aparece**.

## Ordenar y exportar

| Control | Qué hace |
|---|---|
| **Ordenar por** | **Score ↓** (el ranking, es el orden por defecto), **Δ Score ↓** (los que más mejoraron desde la fecha anterior) o **Ticker A-Z**. |
| **Exportar Excel** | Baja la tabla completa —con todas las columnas de señales— a una planilla. Se habilita recién después de la primera búsqueda. |

Reordenar es instantáneo y **no vuelve a consultar**: trabaja sobre los mismos
resultados que ya trajiste. Podés cambiar de orden todas las veces que quieras
sin costo.

---

## Leer la tabla

| Columna | Qué muestra |
|---|---|
| **Ticker** | El símbolo del activo. Es un enlace: lo abre en Análisis de Activo, en una pestaña nueva. Al lado, el enlace **hist.** lleva a [Historial de Señales](/manual/historial-de-senales) con el activo ya seleccionado. |
| **Nombre** | La denominación del activo. |
| **Score** | El puntaje de la estrategia para ese activo ese día, con una barra visual al lado. |
| **Δ** | Cuánto varió el score respecto de la fecha anterior con resultados. |
| **Una columna por señal** | El aporte individual de cada señal que compone la estrategia. Debajo del nombre de cada columna figura su peso (por ejemplo **×2**). |

### El score y su color

El score va de **−100 a +100** y es el **promedio ponderado** de las señales
que componen la estrategia, no la suma. Eso es lo que hace que sea comparable
con las columnas individuales: un score de 60 significa "en promedio, las
señales de esta estrategia dicen +60 para este activo".

El color sigue una regla simple: **verde a partir de +20**, **rojo desde −20
para abajo**, gris en el medio. La zona gris no es "neutral y listo": es la
zona donde las señales no se ponen de acuerdo o el activo no está haciendo
nada destacable.

La barra que acompaña al número es **relativa a la pantalla**: se dibuja
comparando contra el mayor valor absoluto del listado que estás viendo. Sirve
para ver de un golpe la forma de la distribución —si hay un puñado de activos
muy destacados o si están todos apretados—, pero no la leas como un porcentaje
absoluto. El número al lado es el dato duro.

Un guion (**—**) en cualquier columna significa que esa señal no tiene valor
para ese activo ese día: no la tomes como un cero. Cuando a un activo le falta
una señal, el score se calcula con las señales restantes reponderadas, así que
sigue siendo comparable, pero está construido con menos información. Si ves
varios guiones en una fila, mirá ese activo con más cuidado antes de actuar.

### La columna Δ

Compara contra la **fecha anterior que tenga resultados para esa estrategia**,
que no siempre es el día hábil inmediato anterior: si hubo un feriado o una
interrupción en el cálculo, el salto puede abarcar varios días. Verde por
encima de +0,5, rojo por debajo de −0,5, gris en el medio, para no teñir de
color movimientos que son ruido.

Ordenar por **Δ Score ↓** es la forma rápida de encontrar lo que *cambió*, que
suele ser más accionable que lo que ya venía bien hace semanas. Los activos sin
Δ calculable quedan al final.

### Las columnas de señales

Son la explicación del score: te dicen **por qué** un activo está donde está.
Dos activos con score 55 pueden ser casos completamente distintos —uno con
todas las señales en 55, otro con una en 100 y otra en 10—, y esa diferencia
importa para decidir. El peso que figura en la cabecera te dice cuánto empuja
cada columna: una señal con peso alto en rojo arrastra el total aunque el resto
esté en verde.

Ojo con el color de estas columnas: usa los mismos umbrales de ±20 que el
score, pero **la barra de cada columna se normaliza dentro de esa columna**.
Compará barras verticalmente (entre activos de la misma señal), no
horizontalmente.

---

## Dos cosas que conviene tener presentes

**El ranking es transversal.** El puesto de un activo depende de todos los
demás activos de ese día. Un activo puede caer varias posiciones sin que le
haya pasado absolutamente nada: alcanza con que los otros hayan mejorado. Por
eso el score en sí mismo dice más que la posición, y por eso la columna Δ mira
el score y no el puesto. Está desarrollado en
[Cómo se calcula todo](/manual/conceptos-pipeline).

> **El último día es preliminar.** El ranking de la fecha más reciente se
> calcula con el precio del día en curso, que todavía puede cambiar. Si mirás
> el screener a media rueda y volvés al cierre, los scores pueden haberse
> movido. Para decisiones que no son intradiarias, la fecha anterior es un
> dato más firme.

**Si agregaste activos hace poco**, puede que todavía no aparezcan en las
fechas históricas aunque sí estén en la última: incorporarlos a la historia de
rankings requiere un recálculo completo, no alcanza la actualización diaria.
