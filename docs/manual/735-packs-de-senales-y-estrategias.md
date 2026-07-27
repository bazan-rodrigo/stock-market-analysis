---
slug: packs-de-senales-y-estrategias
title: Packs — traer estrategias armadas de afuera
chapter: 7. Configuración
order: 735
roles: admin
page: /admin/packs
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

Por eso esta pantalla arranca con el botón **Descargar catálogo**: baja ese
inventario en un archivo. Si le vas a pedir una estrategia a un asistente de
inteligencia artificial, dale las dos cosas —la especificación del formato y
este catálogo— y podrá armar un pack que entre sin retoques.

## Los tres pasos de la pantalla

**1. Catálogo.** Lo de arriba: se lo entregás a quien va a escribir el pack.

**2. Subir el pack.** Un solo archivo con las señales y la estrategia juntas.
Subirlo **no escribe nada**: solo se revisa.

**3. Informe.** Acá se ve, antes de decidir, qué va a pasar:

- **Errores** — impiden importar. Si hay uno solo, el botón **Importar** queda
  deshabilitado: la importación es todo o nada y se rechazaría entera.
- **Avisos** — no impiden nada, pero conviene leerlos. Marcan las trampas que
  no dan error: una señal que no puntúa en algunas categorías, un ranking que
  puede quedar dominado por un solo activo, señales que ninguna estrategia usa.
- **La tabla** — fila por fila, qué **crea** y qué **actualiza**, y de quién es
  lo que va a pisar. Reimportar un pack ya cargado actualiza sus definiciones
  en vez de duplicarlas, y una definición existente **conserva su dueño**.

Recién con el informe a la vista, **Importar** aplica los dos pasos en el orden
correcto: primero las señales, después la estrategia (que las referencia). La
misma tabla se completa con el resultado de cada fila.

> Las planillas de Excel se importan como siempre, desde
> [Señales](/manual/configuracion-senales) y
> [Estrategias](/manual/configuracion-estrategias). Esta pantalla trabaja con
> el archivo único del estándar.

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
