---
slug: configuracion-estrategias
title: Estrategias — crear y editar
chapter: 7. Configuración
order: 730
roles: analista
page: /admin/strategies
---

Una estrategia es lo que produce el **ranking diario** de activos, y por eso es
la definición más importante —y la pantalla más densa— del sistema. Conviene
tener presente el [pipeline](/manual/conceptos-pipeline) antes de entrar acá.

Toda estrategia tiene **dos partes que hacen cosas distintas y se configuran por
separado**: el **filtro de elegibilidad** decide **quién participa** del ranking,
y los **componentes ponderados** deciden **en qué orden** quedan los que
participaron. Sin filtro participan todos los activos; sin componentes no hay
estrategia (el editor no deja guardar).

## La lista y la barra de acciones

La tabla muestra las estrategias que podés ver —las públicas y las tuyas—, con
su cantidad de componentes (**Comp.**), si tiene **Filtro** («sí» / «—»),
**Dueño**, si es **Pública** y la descripción. Se puede ordenar y filtrar por
cualquier columna.

Marcá una fila para habilitar los botones. **Editar** y **Calcular historia**
piden **una sola** estrategia seleccionada; **Eliminar** y **Calcular
resultados** aceptan varias. Todos exigen que seas el dueño (o administrador):
sobre una estrategia pública ajena los botones quedan apagados.

## Parte 1 — Los componentes: en qué orden

Cada componente es una señal con un peso. El score final del activo es el
**promedio ponderado** de los componentes: cada score por su peso, dividido por
la suma de los pesos.

| Campo | Para qué sirve |
|---|---|
| **Señal (key)** | La señal a usar. El desplegable lista solo las señales que podés ver. |
| **Peso** | Cuánto pesa dentro del promedio. No hace falta que sumen 1: son relativos entre sí, porque siempre se divide por el total. |
| **Alcance** | Si la señal se lee del activo o de un grupo. |
| **Tipo grupo** | Solo aplica con alcance de grupo: **Sector**, **Mercado** o **Industria**. |

El **Alcance** tiene tres valores. **Activo directo** es lo normal: el score de
la señal para ese activo. **Grupo propio** usa el score de esa señal para el
grupo al que el activo pertenece según el **Tipo grupo** elegido — sirve para
premiar al activo cuyo sector viene bien, sin importar cuál sea ese sector.
**Grupo fijo** apunta a un grupo puntual, el mismo para todos; la pantalla no
ofrece dónde elegir *cuál*, así que un componente creado acá con ese alcance no
llega a resolverse y no aporta al score (solo queda definido si la estrategia
entra por importación).

> **El campo Tipo grupo no aparece en el momento en que elegís el alcance.** La
> lista de componentes no se vuelve a dibujar al tocar ese desplegable: el campo
> se muestra recién cuando la lista se redibuja, o sea al agregar o quitar un
> componente, o al cerrar y reabrir el editor. Si elegiste **Grupo propio** y no
> ves dónde cargar el tipo, no está rota la pantalla: agregá un componente (o
> reabrí el editor) y va a estar ahí, con el alcance que elegiste intacto.

### La sutileza que más sorprende: los componentes sin dato se saltean

Si una señal no tiene score para un activo en esa fecha, **ese componente se
descarta por completo**: no cuenta ni en la suma ni en el divisor. El resultado
es el promedio ponderado *de lo que sí había*, no de lo que definiste. Dos
activos pueden entonces tener el mismo score habiendo sido evaluados con
distinta cantidad de señales, y uno con una sola señal disponible puede quedar
arriba de todo. Si eso te preocupa, exigí esa señal en el filtro: así el activo
sin dato queda afuera en vez de entrar con un promedio incompleto.

Caso límite: si **ningún** componente tiene dato, el activo no recibe score y no
aparece en el ranking de ese día. Tampoco se consideran los activos que no
tengan ningún valor de las señales de la estrategia en esa fecha.

Además del score, cada resultado guarda el **percentil** del activo dentro del
ranking del día (100 = el mejor). Es el número que usan las condiciones de
percentil en la [simulación de trades](/manual/analisis-de-activo).

## Parte 2 — El filtro de elegibilidad: quién participa

El filtro es un **árbol de condiciones**. Un activo que no lo cumple no recibe
score y **no aparece en el ranking de ese día** — no es que quede último: no
está.

Cada **grupo** tiene un conector: **AND (todas)** exige que el activo cumpla
todas sus condiciones, **OR (alguna)** con una le alcanza. Con **+ condición**
agregás una línea al grupo y con **+ grupo** anidás un grupo adentro. **No hay
precedencia implícita entre Y y O**: la única forma de mezclarlos es anidando.
«Del panel líder **Y** (del sector energía **O** del sector bancos)» se arma con
un grupo raíz en AND que contiene la condición del panel más un subgrupo en OR
con los dos sectores. Los grupos anidados se reconocen por la barra vertical a
la izquierda. La **×** de una condición la borra; la de un grupo borra el grupo
**y todo lo que tenga adentro**. El raíz no se puede borrar, y un grupo que
queda sin condiciones se descarta solo al guardar.

Cada condición se lee de izquierda a derecha: un operando, un operador y un
valor. El operando izquierdo puede ser un **[Atributo]** del activo (Sector,
Industria, Mercado, País o Tipo de instrumento), un **[Ind]** (el valor del
indicador) o una **[Señal]** (su score).

| Tipo de operando | Operadores |
|---|---|
| Numérico (indicadores numéricos y señales) | `=` `!=` `>` `>=` `<` `<=` |
| Categórico (atributos e indicadores de categorías) | `=` `!=` `in` `not in` |

Con `in` / `not in` el valor pasa a ser una lista y elegís varios de una: es la
forma corta de un OR sobre el mismo atributo. Los atributos se eligen por nombre
de una lista y los indicadores de categorías solo admiten los valores de su
catálogo. Cuando el operando izquierdo es numérico se habilita además el campo
**…o vs indicador/señal**: en vez de comparar contra un número fijo, comparás
contra **otro indicador o señal del mismo activo** (por ejemplo, precio contra
su media); si lo completás, el número se ignora.

> Al cambiar el operando izquierdo se **borran el valor y el campo de
> comparación** —el tipo de dato cambió y lo anterior ya no aplica— y el
> **operador vuelve a un valor por defecto**: `>` si el operando nuevo es
> numérico y `=` si es categórico. Ojo con eso: el operador no queda vacío
> esperando que elijas, así que si no lo tocás se guarda el que quedó puesto.
> Al valor le pasa lo mismo al pasar de `=` a `in` o al revés.

### Dato faltante = condición NO cumplida

Es la regla que más resultados «raros» explica: si el activo no tiene ese
indicador o esa señal en la fecha evaluada, la condición da falso y el activo
queda **afuera** del ranking. El criterio es deliberado —un filtro que dejara
pasar lo que no pudo evaluar sería una trampa silenciosa—, pero implica que
filtrar por un indicador que solo existe para algunas familias de activos
recorta el universo mucho más de lo que parece. Comparar tipos incompatibles (un
número contra un texto) también da falso, y el editor lo rechaza al guardar.

### Cómo se lee el valor en fechas pasadas

Los **indicadores** se leen «as-of»: se usa la última fecha disponible menor o
igual a la evaluada, que es lo que hace que un indicador semanal o mensual siga
sirviendo cualquier día. Pero ese arrastre tiene un **tope de antigüedad de unos
45 días**: si el último valor del indicador quedó más viejo que eso respecto de
la fecha evaluada, se considera que no hay dato y —por la regla de acá arriba—
la condición da falso y el activo queda afuera. Es exactamente lo que pasa con
un indicador que se dejó de calcular, o con un activo que dejó de cotizar. Las
**señales**, en cambio, se leen con **fecha exacta**, igual que en el cálculo
del score.

> **Operandos sin historia.** Algunos indicadores solo guardan su valor vigente,
> y quedan marcadas también las señales que se apoyan en ellos: en los dos casos
> la condición muestra el aviso «⚠ sin historia». No significan lo mismo.
>
> Con un **indicador** sin historia, en fechas pasadas la condición se evalúa
> **con el valor de hoy**. Eso es sesgo de anticipación: sirve como diagnóstico,
> **no como backtest**, y al calcular una fecha pasada la pantalla lo vuelve a
> advertir con un cartel de «Diagnóstico in-sample».
>
> Con una **señal** marcada no pasa eso: se sigue leyendo su score de la fecha
> exacta, como cualquier otra señal. El aviso está para recordarte que de las
> fechas anteriores a la creación de la señal no hay score que reconstruir —
> quedan sin dato, y sin dato la condición no se cumple.

## La previsualización de la fórmula

El recuadro **Fórmula (previsualización)**, abajo de todo, se actualiza mientras
editás y muestra en texto plano el score (con sus pesos y su divisor) y el filtro
con sus Y / O y sus paréntesis. Es de solo lectura: está para releer la lógica
antes de guardar, que en un árbol de tres niveles es justo lo que no se ve de un
vistazo.

## Visibilidad

El switch **Pública** decide quién la ve. Regla clave: **una estrategia pública
solo puede usar señales públicas**, y vale tanto para los componentes como para
los operandos del filtro. Si intentás publicarla con una señal privada adentro,
el guardado falla y te dice cuál. El detalle completo está en
[Visibilidad y permisos](/manual/visibilidad-y-permisos).

## Guardar, y después recalcular

El editor no se cierra si el guardado falla: el mensaje aparece en rojo adentro
del modal y no perdés lo cargado (falta el nombre, falta un componente, hay una
condición sin completar o sin valor).

> **Guardar no recalcula nada**: lo que ya estaba calculado quedó hecho con la
> definición anterior. Si la estrategia es **nueva**, corré **Calcular
> historia** para poblar sus resultados. Si la **editaste**, hace falta
> **Recalcular completo** en el [Centro de Datos](/manual/centro-de-datos) →
> Señales y Estrategias: Calcular historia no alcanza, porque llena los huecos y
> reescribe **únicamente la última fecha** — todas las anteriores que ya tenían
> resultado quedarían calculadas con la definición vieja.

## Calcular resultados y Calcular historia

**Calcular resultados** recalcula **una sola fecha** (la del selector; vacío =
hoy) para las estrategias seleccionadas. Con una sola marcada aparece abajo el
**Top 10** de esa fecha y un acceso al
[screener](/manual/screener-de-senales). Es la forma rápida de probar una
definición recién tocada antes de comprometerse con la historia entera.

**Calcular historia** llena las fechas pasadas que no tengan resultado de esa
estrategia y, además, vuelve a calcular la última (sus precios todavía son
preliminares). El campo **días** limita a los últimos N; **vacío significa toda la
historia**. Corre en primer plano y sobre muchos años **puede tardar varios
minutos**: dejá la pestaña abierta y empezá acotando con pocos días para medir
cuánto tarda.

## Importar, exportar y eliminar

**Exportar** e **Importar** (solo administradores) bajan y suben todas las
estrategias en un archivo de planilla, con una hoja de estrategias y otra de
componentes. La importación es **todo o nada**: se valida el archivo completo y,
si algo falla, no entra ninguna; el resultado se lista fila por fila con el
detalle del error. Las estrategias se identifican **por nombre sin distinguir
mayúsculas**, así que importar una que ya existe **la sobrescribe**, reemplazando
todos sus componentes.

> **Eliminar** borra la estrategia junto con todos sus resultados históricos y
> no se puede deshacer.
