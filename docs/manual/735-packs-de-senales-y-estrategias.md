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

Un pack también puede traer **solo señales, sin ninguna estrategia**: es la
forma de cargar de una vez un catálogo entero de señales, para que después las
estrategias elijan de ahí. Se sube por esta misma pantalla y se revisa igual.

El formato es **público y estándar**: cualquiera que lo respete produce un
archivo que esta aplicación importa. La especificación completa se descarga
desde esta misma pantalla, así que no hace falta pedirle nada a nadie para
poder entregarla.

## Las dos piezas que necesita quien lo escribe

**El formato** es siempre el mismo, y **el catálogo** cambia en cada
instalación: qué indicadores hay disponibles, qué categorías devuelve cada uno,
y qué sectores, mercados, industrias, países y tipos de instrumento están
cargados en *esta* base. Sin el catálogo, quien escribe el pack tiene que
adivinar los nombres — y un nombre inventado hace que el import rechace el
archivo entero.

Por eso la pantalla arranca con los dos botones: **Especificación** y
**Catálogo**. Si le vas a pedir una estrategia a un asistente de inteligencia
artificial, adjuntale los dos archivos y describile en castellano común la
lógica que querés; con eso puede armar un pack que entre sin retoques.

## Los tres pasos de la pantalla

**1. Qué entregar.** Los dos archivos de arriba. La especificación es siempre
la misma; el catálogo cambia con lo que tengas cargado, así que conviene bajarlo
de nuevo cada vez.

**2. Subir el pack.** Un solo archivo, con las señales y la estrategia juntas o
con señales solas. Subirlo **no escribe nada**: solo se revisa.

**3. Informe.** Acá se ve, antes de decidir, qué va a pasar:

- **Errores** — impiden importar. Si hay uno solo, el botón **Importar** queda
  deshabilitado: la importación es todo o nada y se rechazaría entera.
- **Avisos** — no impiden nada, pero conviene leerlos. Marcan las trampas que
  no dan error: una señal que no puntúa en algunas categorías, un ranking que
  puede quedar dominado por un solo activo, o señales que el pack trae y su
  estrategia no usa. Este último no aparece en un pack de señales solas, donde
  ninguna señal tiene todavía estrategia que la use.
- **La tabla** — fila por fila, qué **crea** y qué **actualiza**, y de quién es
  lo que va a pisar. Reimportar un pack ya cargado actualiza sus definiciones
  en vez de duplicarlas, y una definición existente **conserva su dueño**.

Recién con el informe a la vista, **Importar** aplica los dos pasos en el orden
correcto: primero las señales, después la estrategia (que las referencia). Si el
pack trae solo señales, se aplica ese único paso. La misma tabla se completa con
el resultado de cada fila.

> Las planillas de Excel se importan como siempre, desde
> [Señales](/manual/configuracion-senales) y
> [Estrategias](/manual/configuracion-estrategias). Esta pantalla trabaja con
> el archivo único del estándar.

## Después de importar

Un pack recién importado **todavía no tiene resultados**. Para llenarlos, andá
al [Centro de Datos](/manual/centro-de-datos) → **Señales y Estrategias** →
**Ejecutar**, eligiendo como alcance la estrategia nueva: así se calcula solo su
historia y no se recalcula todo el sistema. Si el pack trajo solo señales, la
historia se les llena en la próxima corrida.

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
