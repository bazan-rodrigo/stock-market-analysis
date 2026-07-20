---
slug: eventos-de-mercado
title: Eventos de mercado
chapter: 6. Datos de Mercado
order: 630
roles: admin
page: /admin/events
---

Un **evento de mercado** es un período con nombre —una crisis, una elección, un
default, el anuncio de un balance— que el sistema dibuja como una zona de color
sobre los gráficos. No afecta ningún cálculo: es contexto visual. Sirve para
responder "¿por qué se cayó acá?" sin tener que acordarse de memoria qué pasó en
esa fecha.

Esta pantalla es el alta, baja y modificación de esos eventos, uno por uno. Si
tenés que cargar muchos de una vez, usá [Importar eventos](/manual/importar-eventos).

## La tabla

Lista todos los eventos cargados, del más reciente al más viejo.

| Columna | Qué muestra |
|---|---|
| **Nombre** | El texto que aparece en la etiqueta del gráfico. |
| **Inicio** / **Fin** | El período que abarca, en formato día/mes/año. |
| **Alcance** | Global, País o Activo. Define a qué gráficos llega el evento. |
| **Ref.** | El país o el activo concreto al que está atado. Un guión si es global. |
| **Color** | El color de la zona sombreada. |

Se puede filtrar y ordenar por cualquier columna. Para editar o eliminar,
primero seleccioná la fila con la tilde de la izquierda: hasta que no haya una
selección, los botones **Editar** y **Eliminar** están apagados.

## Alcance: la decisión importante

El alcance es lo único que define **dónde se va a ver** el evento después. Es la
única decisión que conviene pensar dos veces, porque un evento mal alcanzado o
no aparece nunca, o aparece en gráficos donde no tiene nada que ver.

| Alcance | Se muestra en… | Cuándo usarlo |
|---|---|---|
| **Global (todos los activos)** | Absolutamente todos los activos. | Hechos que movieron todos los mercados: la crisis de 2008, la pandemia, una suba de tasas de la Fed. |
| **País** | Solo los activos cuyo país es el que elegiste. | Elecciones, defaults, cepos, devaluaciones. Un activo sin país cargado no lo va a ver nunca. |
| **Activo específico** | Solo ese activo. | Un split, una fusión, un cambio de CEO, un balance que rompió la serie. |

> El campo **País** solo aparece cuando elegís alcance País, y el campo
> **Activo** solo cuando elegís Activo específico. Si cambiás el alcance
> después de haber elegido, el sistema descarta la referencia que ya no
> corresponde: un evento de alcance Global nunca queda "con país adentro".

## El formulario

| Campo | Obligatorio | Detalle |
|---|---|---|
| **Nombre** | Sí | Es la etiqueta visible. Conviene que sea corto y reconocible: "Crisis financiera 2008", "PASO 2019". |
| **Fecha inicio** | Sí | Selector de fecha. |
| **Fecha fin** | Sí | Debe ser **posterior** a la de inicio. Para marcar un hecho de un solo día, poné el día siguiente como fin. |
| **Alcance** | Sí | Ver el cuadro de arriba. Por defecto, Global. |
| **Color de zona** | Sí | Naranja (por defecto), Rojo, Azul, Verde, Violeta, Amarillo o Cian. |
| **País** | Solo si el alcance es País | Lista de los países cargados en el sistema. |
| **Activo** | Solo si el alcance es Activo específico | Lista de activos por ticker y nombre; se puede escribir para buscar. |

El color no significa nada para el sistema: es una convención tuya. Un criterio
que funciona bien es rojo para crisis, azul para hechos políticos y verde para
recuperaciones, así el gráfico se lee de un vistazo.

> Si el guardado falla, el formulario **queda abierto** con todo lo que
> cargaste y el error se muestra adentro del mismo cuadro. No vas a perder lo
> escrito.

## Eliminar

Con una fila seleccionada, **Eliminar** pide confirmación mostrando el nombre
del evento. La baja es definitiva y el evento desaparece de todos los gráficos
donde se veía. No hay papelera: si era un evento importante, conviene editarlo
antes que borrarlo y volver a cargarlo.

## Dónde se ven los eventos cargados

- **[Análisis de Activo](/manual/analisis-de-activo)**, en el gráfico técnico:
  se prenden con el botón **Eventos**. Ahí llegan los tres alcances — los
  globales, los del país del activo y los propios del activo.
- **[Evolución](/manual/evolucion)**: se superponen sobre las series
  comparadas, tomando los eventos globales, los de los países de los activos
  elegidos y los propios de cada uno.
- **[Análisis de Pares](/manual/analisis-de-pares)**: se marcan los eventos
  sobre la nube de puntos, ubicados en el día más cercano al centro del período.

> En Análisis de Pares se muestran únicamente los eventos **globales** y los de
> **activo específico** de los dos activos comparados: los eventos de alcance
> País no llegan a esa pantalla.

Un evento recién cargado aparece la próxima vez que abrís el gráfico. No hace
falta recalcular nada: los eventos son independientes del
[pipeline de cálculo](/manual/conceptos-pipeline).
