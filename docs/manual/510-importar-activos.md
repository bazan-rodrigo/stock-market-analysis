---
slug: importar-activos
title: Importar activos
chapter: 5. Activos
order: 510
roles: admin
page: /assets-import
---

Alta masiva de activos desde un Excel. Es la vía práctica para cargar un panel
entero, un sector nuevo o una lista armada afuera; el alta de a uno está en
[Gestión de activos](/manual/gestion-de-activos).

La pantalla tiene tres pasos: descargar la plantilla, subir el archivo
completado, e importar.

## 1. Descargar template

**Descargar template** genera un `.xlsx` con los encabezados correctos **y con
todos los activos que ya existen en el sistema**, una fila cada uno. Sirve para
dos cosas: como modelo de formato, y como copia del padrón actual.

> Los activos ya existentes que vengan en el archivo se **omiten**, no se
> actualizan. La importación **solo da de alta**: no es una vía para editar en
> masa (para eso está la edición masiva de
> [Gestión de activos](/manual/gestion-de-activos)).

## 2. Las columnas del archivo

Los encabezados se leen sin distinguir mayúsculas ni espacios sobrantes. El
orden de las columnas no importa, y las que no uses podés dejarlas vacías.

| Columna | Obligatoria | Qué espera |
|---|---|---|
| `ticker` | **Sí** | El símbolo. Se convierte a mayúsculas. Las filas con esta celda vacía se ignoran sin avisar. |
| `fuente_precios` | **Sí** | El **nombre exacto** de una fuente ya existente en el sistema (por ejemplo `Yahoo Finance`). Si no coincide, la fila da error. |
| `nombre` | No | Texto libre. Vacío: se usa el que reporte la fuente y, si tampoco hay, el ticker. |
| `pais_iso` | No | País. Se busca por nombre o por una equivalencia ya registrada; si no encuentra ninguno, **crea un país nuevo con ese texto**. |
| `mercado` | No | Nombre del mercado. Mismo criterio: busca, y si no existe lo crea. |
| `tipo_instrumento` | No | Acción, índice, ETF, etc. Busca o crea. |
| `moneda` | No | Se busca por **nombre** de moneda. Vacío: se usa la moneda que informe la fuente. |
| `sector` | No | Busca o crea. |
| `industria` | No | Busca o crea, colgada del sector de esa misma fila. |
| `benchmark_ticker` | No | Ticker del activo a usar como benchmark. Ver más abajo. |
| `fuente_fundamentales` | No | Nombre exacto de una fuente de fundamentales existente. Si no coincide, el activo se importa **sin** fuente de fundamentales y sin avisar. |

Dos reglas que conviene tener claras:

- **Lo que escribas en el archivo gana.** Para cada campo opcional, el valor del
  Excel tiene prioridad; solo si la celda está vacía se usa lo que reporta la
  fuente de precios.
- **Los catálogos se crean solos.** Un sector escrito con otra grafía no falla:
  crea un sector nuevo. Es la causa más común de catálogos duplicados, así que
  copiá los nombres tal como ya existen en el sistema.

### El benchmark se resuelve al final

Los benchmarks se asignan en una segunda pasada, **después** de crear todos los
activos del archivo. Por eso podés apuntar a un ticker que se da de alta más
abajo en la misma planilla. Si el ticker indicado no existe ni se creó, el
activo queda importado igual y el detalle agrega la aclaración de que no se
encontró el benchmark.

## 3. Subir e importar

**Seleccionar archivo .xlsx** carga el archivo (solo `.xlsx`) y habilita
**Importar**. Durante la corrida una barra muestra el avance `procesadas /
totales`; el proceso sigue en segundo plano, así que la pantalla no se cuelga.

Al terminar aparece el resumen: `Procesados N: X importados, Y omitidos, Z con
error.`

## Qué pasa ante errores

Hay dos niveles, y la diferencia importa:

| Situación | Resultado |
|---|---|
| El archivo no se puede leer, o le falta `ticker` o `fuente_precios` | **Se rechaza todo.** No se importa ninguna fila; el error aparece en rojo sobre el botón. |
| Una fila puntual falla | **Se importa igual el resto.** Cada activo se confirma por separado; un error no arrastra a los anteriores ni frena a los siguientes. |

Los motivos de fila fallida son básicamente tres: la fuente de precios no
existe con ese nombre, el ticker **no es válido para esa fuente** (se verifica
contra el proveedor, uno por uno), o algún dato hace fallar el guardado.

## La tabla de Resultados

Queda registrado el resultado de cada ticker, con filtro y orden por columna:

| Estado | Color | Significa |
|---|---|---|
| `imported` | Verde | Activo creado. |
| `skipped` | Naranja | El ticker ya existía; no se tocó nada. |
| `error` | Rojo | No se creó. La columna **Detalle** dice por qué. |

El registro **persiste entre sesiones** y se va pisando por ticker: si reintentás
una importación, cada ticker conserva solo su último resultado.
**Limpiar resultados** vacía la tabla; no afecta a los activos ya creados.

> Como la validación consulta al proveedor **ticker por ticker**, un archivo de
> cientos de filas puede tardar. Es normal.

## Después de importar

La importación crea los activos, pero **no descarga los precios**: eso lo
resuelve la actualización diaria. Hasta entonces los activos nuevos van a
aparecer sin historia.

Y como siempre que entran activos nuevos, las señales de grupo y los rankings de
estrategia quedan desactualizados en la historia ya calculada: hace falta un
**recálculo completo**, según se explica en
[Cómo se calcula todo](/manual/conceptos-pipeline).
