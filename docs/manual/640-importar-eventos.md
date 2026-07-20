---
slug: importar-eventos
title: Importar eventos
chapter: 6. Datos de Mercado
order: 640
roles: admin
page: /admin/events/import
---

Cargar treinta crisis y elecciones de a una desde
[Eventos de mercado](/manual/eventos-de-mercado) es tedioso. Esta pantalla hace
lo mismo desde una planilla Excel: una fila por evento. Es el camino natural
para poblar el sistema por primera vez, o para sumar de golpe la historia de un
país nuevo.

La pantalla tiene tres bloques, en el orden en que se usan.

## 1. Descargar template

El botón **Descargar template** baja un archivo `.xlsx` con los encabezados
correctos y **los eventos que ya están cargados en el sistema**. Sirve para dos
cosas: como modelo de formato (nunca vas a equivocarte con los nombres de las
columnas) y como respaldo de lo que hay hoy.

La forma más segura de trabajar es descargarlo, agregar las filas nuevas al
final y subirlo de nuevo: las filas que ya existen se van a saltear solas.

## 2. Subir archivo

**Seleccionar archivo .xlsx** abre el explorador; solo acepta ese formato. Una
vez elegido, el nombre aparece debajo y se habilita **Importar**. Mientras
corre, una barra muestra el avance fila por fila.

## Las columnas del archivo

Se lee la primera hoja. Los encabezados no distinguen mayúsculas de minúsculas
ni molestan los espacios sobrantes, pero los nombres tienen que ser estos:

| Columna | ¿Obligatoria? | Formato esperado |
|---|---|---|
| **nombre** | Sí | Texto libre. Es la etiqueta que se ve en el gráfico. |
| **fecha_inicio** | Sí | `AAAA-MM-DD`, `DD/MM/AAAA` o `MM/DD/AAAA`. |
| **fecha_fin** | Sí | Mismos formatos. Puede ser igual a la de inicio, pero nunca anterior. |
| **alcance** | Sí | Uno de tres valores en inglés y minúscula: `global`, `country` o `asset`. |
| **pais** | Solo si el alcance es `country` | Nombre del país. Si no existe en el sistema, se crea. |
| **color** | No | Código de color tipo `#ff9800`. Vacío = naranja. |

> Cuidado con los formatos `DD/MM/AAAA` y `MM/DD/AAAA`: el sistema prueba
> primero el día/mes. Una fecha como `03/07/2024` se va a leer como 3 de julio.
> Si tenés dudas, usá siempre `AAAA-MM-DD`, que no es ambiguo.

> **La columna `alcance` no soporta eventos por activo desde el archivo.** El
> valor `asset` se acepta sin error, pero la planilla no tiene ninguna columna
> para indicar *cuál* activo, así que el evento queda sin activo asignado y no
> se ve en ningún gráfico. Los eventos de un activo puntual cargalos a mano
> desde [Eventos de mercado](/manual/eventos-de-mercado).

Se ignoran en silencio las filas sin nombre y las que empiezan con `──` o `--`,
así podés usarlas como separadores visuales para agrupar eventos por país o por
década.

## Qué pasa ante un error

Hay que distinguir dos niveles, porque se comportan al revés.

**Errores de estructura: se rechaza todo.** Si el archivo no se puede abrir como
Excel, o si le falta alguna de las cuatro columnas obligatorias, la importación
ni siquiera empieza y no se guarda nada. El mensaje dice qué columnas faltan.

**Errores de fila: se importa lo que se puede.** Superada la estructura, cada
fila se guarda por separado. Una fila con la fecha mal escrita no frena a las
demás: queda registrada como error y el proceso sigue. Es una importación
**parcial**, no un todo-o-nada.

## 3. Resultados

Al terminar aparece el detalle fila por fila, con filtro y ordenamiento propios:

| Estado | Qué significa |
|---|---|
| **imported** (verde) | El evento se creó. |
| **skipped** | Ya existía un evento con el **mismo nombre y las mismas dos fechas**. No se duplicó ni se pisó nada. |
| **error** (rojo) | La fila no se pudo cargar. La columna **Detalle** dice por qué: fechas inválidas o faltantes, fecha fin anterior a la de inicio, alcance distinto de los tres válidos, o país vacío con alcance `country`. |

Arriba, un resumen del estilo "12 importados, 2 errores".

> El resumen cuenta importados y errores, pero **no menciona los omitidos**. Si
> reimportás el template descargado y el resumen dice "0 importados, 0 errores",
> no es que falló: es que todo ya estaba cargado. Miralo en la tabla.

**Limpiar resultados** vacía la tabla de la pantalla. No deshace nada: los
eventos importados siguen cargados. Para revertir una importación hay que
eliminar los eventos desde [Eventos de mercado](/manual/eventos-de-mercado).

## Después de importar

Los eventos son puro contexto visual y no intervienen en el
[pipeline de cálculo](/manual/conceptos-pipeline): no hace falta recalcular
nada. Aparecen en los gráficos apenas los volvés a abrir.
