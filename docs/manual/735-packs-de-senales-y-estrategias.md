---
slug: packs-de-senales-y-estrategias
title: Packs — traer estrategias armadas de afuera
chapter: 7. Configuración
order: 735
roles: admin
---

Un **pack** es un archivo que trae una estrategia completa y lista para
importar: la estrategia y **todas las señales que usa**, con sus fórmulas y su
filtro de elegibilidad. Sirve para traer trabajo hecho afuera del sistema —por
vos, por un colega o por un asistente de inteligencia artificial— sin tener que
cargar una por una cada señal a mano en
[Señales](/manual/configuracion-senales) y en
[Estrategias](/manual/configuracion-estrategias).

El formato es **público y estándar**: cualquiera que lo respete produce un
archivo que esta aplicación importa. Está documentado en el archivo `SPEC.md`
que acompaña al programa, junto con los packs de ejemplo.

## Las dos piezas que necesita quien lo escribe

**El formato** es siempre el mismo, y **el catálogo** cambia en cada
instalación: qué indicadores hay disponibles, qué categorías devuelve cada uno,
y qué sectores, mercados, industrias, países y tipos de instrumento están
cargados en *esta* base. Sin el catálogo, quien escribe el pack tiene que
adivinar los nombres — y un nombre inventado hace que el import rechace el
archivo entero.

Por eso la pantalla de [Señales](/manual/configuracion-senales) tiene el botón
**Catálogo**: descarga ese inventario en un archivo. Si le vas a pedir una
estrategia a un asistente de inteligencia artificial, dale las dos cosas —la
especificación del formato y este catálogo— y podrá armar un pack que entre sin
retoques.

## Cómo se importa

El mismo archivo se sube **dos veces**, y el orden importa:

1. En [Señales](/manual/configuracion-senales) → **Importar**. Entran las
   señales.
2. En [Estrategias](/manual/configuracion-estrategias) → **Importar**. Entra la
   estrategia, que ya puede encontrar las señales del paso anterior.

Si lo hacés al revés, el segundo paso falla: la estrategia referencia señales
que todavía no existen.

La importación es **todo o nada** en cada paso: si una sola línea del archivo
tiene un problema, no entra nada y la pantalla lista el motivo de cada una.
Reimportar un pack que ya está cargado **actualiza** sus definiciones en vez de
duplicarlas.

Se aceptan dos formatos indistintamente: el archivo único del estándar y las
planillas de siempre (una de señales y otra de estrategias), que son las que
bajan los botones **Exportar**.

## Después de importar

Un pack recién importado **todavía no tiene resultados**. Para llenarlos, andá
al [Centro de Datos](/manual/centro-de-datos) → **Señales y Estrategias** →
**Ejecutar**, eligiendo como alcance la estrategia nueva: así se calcula solo su
historia y no se recalcula todo el sistema.

Recién ahí la estrategia aparece con datos en el
[screener](/manual/screener-de-senales), en la
[evolución de estrategia](/manual/evolucion-de-estrategia) y en el
[backtest](/manual/backtest).

## Qué revisar antes de confiar en un pack ajeno

Un pack es una definición, no un resultado: **nadie garantiza que la estrategia
sea buena**, solo que el archivo es válido. Antes de usarlo en serio:

- Abrí la estrategia y mirá su **filtro de elegibilidad**: un filtro más
  permisivo de lo que creías puede dejar entrar activos que no querías.
- Revisá que cada señal **cubra todos los casos** de su indicador. Una señal que
  no puntúa en cierta categoría no cuenta como cero: **se saltea**, y el
  promedio se calcula sin ella. Ver
  [Referencia de fórmulas](/manual/formulas-de-senales).
- Fijate cuántas señales trae. Cada señal cargada **se recalcula en cada
  corrida** del sistema, use o no una estrategia: un pack con señales de más
  encarece todas las actualizaciones diarias.
- Corré un [backtest](/manual/backtest) antes de tomar decisiones con su
  ranking.

> Las señales y estrategias importadas nacen **privadas** salvo que el archivo
> diga lo contrario, y quien importa queda como su dueño. Ver
> [Visibilidad y permisos](/manual/visibilidad-y-permisos).
