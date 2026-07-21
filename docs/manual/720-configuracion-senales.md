---
slug: configuracion-senales
title: Señales — crear y editar
chapter: 7. Configuración
order: 720
roles: analista
page: /admin/signals
---

Una señal convierte un indicador en una **opinión**: traduce "el RSI está en 72"
o "la tendencia es alcista fuerte" a un puntaje entre −100 y +100. El puntaje de
una estrategia no se arma con indicadores crudos: se arma con señales. (El filtro
de elegibilidad sí puede mirar indicadores directamente, pero el ranking sale de
las señales.) Por eso acá se define el criterio de análisis del sistema — todo lo
demás es plomería. Si no tenés claro dónde encaja este paso, leé antes
[cómo se calcula todo](/manual/conceptos-pipeline).

## La lista

La tabla muestra las señales que podés ver: las públicas más las tuyas (un
administrador ve todas), con **Key**, **Nombre**, **Fuente**, **Indicador**,
**Fórmula**, **Dueño** y **Pública**. Se ordena y filtra por cualquier columna.
Las señales de activo van en celeste y las de grupo en verde.

| Botón | Qué hace |
|---|---|
| **+ Nueva** | Abre el editor en blanco. |
| **Editar** | Requiere **una sola** fila seleccionada y que sea tuya (o ser administrador). |
| **Eliminar** | Borra las seleccionadas. Solo se habilita si podés editarlas todas. |
| **Calcular historia** | Requiere **una sola** fila seleccionada y que sea tuya (o ser administrador). Llena las fechas pasadas sin valor de **esa** señal. El campo **días** acota el horizonte; vacío = toda la historia. |
| **Exportar** / **Importar** | Solo administradores. Bajan y suben las definiciones en un Excel. |
| **Ejecutar pipeline** | Solo administradores. Calcula señales → estrategias para la fecha elegida (vacía = hoy). |

**Calcular historia** corre en el momento y la pantalla queda esperando: sobre
toda la historia puede tardar varios minutos. Es lo que hay que usar después de
**crear** una señal. Para reconstrucciones grandes está el
[Centro de Datos](/manual/centro-de-datos).

## El editor

| Campo | Para qué sirve |
|---|---|
| **Clave (key)** | El identificador con el que las estrategias la referencian. Corto y sin espacios (`tendencia_d`). |
| **Nombre** | El texto legible que se ve en el resto de las pantallas. |
| **Fuente** | **Activo** o **Grupo** (ver abajo). |
| **Tipo de grupo** | Solo con fuente Grupo: **Sector**, **Mercado** o **Industria**. |
| **Clave de indicador** | Qué indicador lee la señal. El desplegable ofrece el catálogo agrupado por categoría y se puede buscar escribiendo. |
| **Tipo de fórmula** | Mapa discreto, Umbrales o Rango. |
| **Descripción** | Opcional, para vos y para el equipo. |
| **Pública** | Visibilidad — ver [visibilidad y permisos](/manual/visibilidad-y-permisos). |
| **Parámetros** | El editor de la fórmula, con **vista previa** en vivo al costado. |

> **La clave no se puede cambiar al editar.** Aparece bloqueada a propósito: el
> filtro de elegibilidad de las estrategias referencia las señales por su clave,
> y renombrarla rompería esas referencias en silencio. Si necesitás otra clave,
> creá una señal nueva.

Al crear, la clave tiene que ser única (no distingue mayúsculas de minúsculas).
Y si algo falla al guardar, **el editor no se cierra**: lo cargado sigue ahí.

## Fuente: activo o grupo

Con **fuente Activo** la señal mira el indicador **de ese activo** — su
tendencia, su RSI, su drawdown. Es el caso normal.

Con **fuente Grupo** mira el agregado del grupo al que el activo pertenece, y
responde preguntas del estilo "¿el sector de esta acción viene bien?". Hay que
elegir **Tipo de grupo**, y el indicador queda restringido a tres opciones: la
**tendencia diaria, semanal o mensual del grupo**. No se pueden usar indicadores
de activo acá — los agregados de grupo no los tienen y la señal no puntuaría
nunca; el sistema no te deja guardarla. Todos los activos del mismo grupo
comparten el puntaje, y un activo sin ese grupo cargado no recibe ninguno.

## Las tres fórmulas

### Mapa discreto

Para indicadores con **categorías**, como la tendencia o el régimen de
volatilidad. Asignás a mano el puntaje de cada categoría: alcista fuerte → 100,
alcista → 60, lateral → 0, bajista → −60. Si el indicador tiene catálogo de
categorías conocidas, el editor **precarga las filas** y solo completás
puntajes; si no, escribís el valor exacto que produce el indicador — un error de
tipeo no da error al guardar, esa categoría simplemente no coincide nunca.

> **Categoría sin puntaje = la señal no puntúa ese día.** No vale 0: el activo
> queda sin score para esa señal, y entonces no aporta nada a la estrategia. Si
> querés que una categoría sea neutra, asignale 0 explícitamente. Dejarla vacía
> es una decisión distinta.

### Umbrales (escalones)

Para indicadores numéricos, cuando querés puntajes **por tramos** en vez de una
escala continua. Se evalúa de arriba hacia abajo y **el primer umbral que el
valor supera** define el puntaje. Con drawdown: mayor a −5% → 100; mayor a
−15% → 50; mayor a −30% → 0; y todo lo peor cae en «en otro caso» → −50.

La comparación es **estrictamente mayor**: un valor igual al límite no lo supera
y pasa al escalón siguiente. No hace falta cargarlos ordenados —se ordenan solos
de mayor a menor al guardar—, pero tienen que ser distintos entre sí y cada fila
necesita límite **y** puntaje.

El campo **«en otro caso»** es opcional, y ahí está la sutileza: si lo completás,
todo valor posible recibe exactamente un puntaje; si lo dejás vacío, los valores
que no superan ningún límite **quedan sin score**, igual que una categoría sin
asignar. La vista previa lo muestra como un hueco en el escalonado. Sirve para
que la señal opine solo cuando tiene algo que decir.

### Rango lineal

Para indicadores numéricos con **escala continua**: el puntaje crece
proporcionalmente con el valor. Definís **Min** (el valor que vale −100) y
**Max** (el que vale +100); lo intermedio se interpola en línea recta y el punto
medio da 0. Por ejemplo Min = −3 y Max = 3 para una distancia en desvíos
estándar. **Recortar a ±100** deja los valores fuera del rango pegados a ±100;
si lo apagás, la escala sigue de largo y el puntaje puede pasarse de ±100, algo
que después se propaga al score de la estrategia.

> **Para invertir la escala, poné el valor "bueno" en Max aunque sea el menor de
> los dos.** Min y Max no son mínimo y máximo: son *el valor que vale −100* y
> *el que vale +100*. Con un indicador donde menos es mejor, Min = 40 y Max = 10
> es válido y hace exactamente lo que querés. Lo único prohibido es que sean
> iguales.

### ¿Cuál conviene?

Categórico → mapa discreto, no hay alternativa. Numérico con niveles de
referencia conocidos (sobrecompra, zona de riesgo) → umbrales, más fáciles de
explicar y auditar. Numérico donde cada punto de diferencia importa → rango
lineal, que no tira a la basura la diferencia entre dos activos del mismo tramo.

## Vista previa y modo avanzado

El gráfico de la derecha se actualiza mientras escribís y muestra cómo se
traduce valor → puntaje: barras en el mapa, escalones en los umbrales, una recta
en el rango. Es la forma más rápida de detectar un signo invertido.

**Modo avanzado (editar JSON)** cambia el editor por el texto crudo de los
parámetros. Al prenderlo se vuelca lo armado; al apagarlo se intenta reflejar lo
escrito a mano, y si no es representable en el editor visual la pantalla avisa y
conserva los últimos valores válidos. Una señal cuyos parámetros no se pueden
representar abre directamente en modo avanzado. Para el uso normal no hace falta.

## Cuándo una señal no puntúa

- El activo no tiene valor para ese indicador en esa fecha.
- Cayó en una categoría sin puntaje, o bajo el último umbral sin «en otro caso».
- Es una señal de grupo y el activo no tiene ese grupo cargado.
- El indicador **no guarda serie histórica**, solo su valor vigente: esas señales
  puntúan únicamente en la última fecha y en las pasadas se omiten a propósito,
  porque usar el valor de hoy en una fecha vieja sería mirar el futuro.

Al revés, un detalle que también sorprende: para cada fecha se toma el **último
valor disponible del indicador hasta esa fecha**. Por eso una señal sobre un
indicador semanal o mensual puntúa todos los días, arrastrando el valor del
último período cerrado, en vez de puntuar solo los viernes o los fines de mes.

## Guardar, borrar y recalcular

> **Editar una señal ya calculada exige un recálculo completo.** Lo viejo quedó
> calculado con la definición anterior y la actualización incremental solo toca
> la última fecha. Al guardar, el sistema lista qué quedó desactualizado —la
> señal y **las estrategias que la usan**; si son muchas, muestra las primeras y
> cuántas quedan— para que corras «Recalcular completo» en el
> [Centro de Datos](/manual/centro-de-datos). Mientras no lo
> hagas convivís con historia calculada con dos criterios distintos, y un
> backtest sobre ella no significa nada.

Al **crear** una señal no hace falta el recálculo completo: alcanza con
**Calcular historia** sobre esa señal. Para verificar visualmente que la
historia quedó reconstruida, la pantalla de
[Historial de señales](/manual/historial-de-senales) muestra la serie de
puntajes fecha por fecha.

**Eliminar** borra la definición y toda su historia de puntajes, sin deshacer. El
sistema lo impide si alguna estrategia la usa —en sus componentes o en el
filtro— y te dice cuáles: primero hay que sacarla de ahí. La misma lógica rige
para despublicar una señal que otros usan; el detalle está en
[visibilidad y permisos](/manual/visibilidad-y-permisos).

## Importar y exportar (administradores)

**Exportar** baja todas las señales en un Excel; **Importar** lo sube de vuelta.
La importación es **todo o nada**: primero se valida el archivo entero sin tocar
nada y, si una fila tiene un error, no se importa ninguna; el resultado se
muestra fila por fila. Las filas se cruzan por clave, así que una señal que ya
existe **se actualiza** en vez de duplicarse. Las nuevas quedan a nombre de quien
importa, y la columna de visibilidad del archivo manda (si falta, entran como
públicas).
