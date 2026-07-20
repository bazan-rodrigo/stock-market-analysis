---
slug: fuentes-de-datos
title: Fuentes de datos
chapter: 7. Configuración
order: 715
roles: admin
page: /admin/price-sources
---

Una **fuente** es el proveedor del que sale un dato: de dónde se descargan las
cotizaciones de un activo y, por separado, de dónde salen sus balances. Todo lo
que el sistema calcula después —indicadores, señales, ranking— se apoya en esos
números, así que la fuente es la primera pieza de la cadena descripta en
[Cómo se calcula todo](/manual/conceptos-pipeline).

Cada activo tiene **una sola fuente de precios y es obligatoria**. La fuente de
fundamentales es aparte y **opcional**.

## Qué es esta pantalla

Un **catálogo de consulta**: muestra, en tarjetas, las fuentes que el sistema
sabe usar, divididas en **Fuentes de Precios** y **Fuentes de Fundamentales**.
Cada tarjeta trae una descripción y estos datos:

| Dato de la tarjeta | Qué dice |
|---|---|
| **Mecanismo** | Cómo obtiene los datos: una librería, una API pública o un cálculo interno. |
| **Notas** | Restricciones de la fuente — qué tickers acepta, qué tipo de activos cubre. |
| **Campos** | Solo en fundamentales: qué conceptos de balance trae. |

Acá no se da de alta, ni se edita, ni se borra nada: es informativa. Sirve para
responder, antes de cargar un activo, **"¿de dónde puedo sacar esto?"**.

## Las fuentes de precios

| Fuente | Qué cubre | Cuándo elegirla |
|---|---|---|
| **Yahoo Finance** | Cualquier ticker de Yahoo: acciones, ETFs, índices, bonos, tipos de cambio. | Es el caso normal. Casi todos los activos van con esta. |
| **Ambito** | Únicamente el Riesgo País Argentina, con historia diaria desde diciembre de 1998. | Solo para ese dato: **acepta un único ticker**, `RIESGO_PAIS_AR`. Ese activo ya viene creado en el sistema. |
| **Calculado** | Nada externo: el precio se deriva de otros activos ya cargados. | Para [sintéticos](/manual/activos-sinteticos) (ratios, spreads) y para las [conversiones a divisa](/manual/activos-en-divisa). |

> **La serie del Riesgo País no tiene velas reales.** La fuente entrega un solo
> valor por día, así que apertura, máximo, mínimo y cierre son idénticos y el
> volumen es cero. Miralo siempre en modo **Línea**: en velas se ve como una
> sucesión de rayitas, y cualquier indicador que dependa del rango del día o del
> volumen no dice nada útil sobre este activo.

## Cómo se le asigna una fuente a un activo

| Vía | Cómo |
|---|---|
| **Alta o edición individual** | Campo **Fuente de precios** del formulario de [Gestión de activos](/manual/gestion-de-activos). Es obligatorio. |
| **Importación masiva** | Columna **fuente_precios** de la planilla de [Importar activos](/manual/importar-activos), obligatoria. |

> **La fuente de precios no está en la edición masiva.** Esa barra permite
> cambiar mercado, sector, moneda o fuente de *fundamentales* en muchos activos
> de una vez, pero **no** la fuente de precios: hay que entrar activo por activo.

En la importación, el nombre de la fuente tiene que coincidir **exactamente** con
el que muestra esta pantalla; si no coincide, la fila se rechaza con el error
"Fuente no encontrada". Ojo con la asimetría: si el nombre que no coincide es el
de la **fuente de fundamentales**, la fila **se importa igual** y el activo queda
sin fuente de fundamentales, sin ningún aviso. Después de importar conviene
revisar esa columna en el listado de activos.

### Autocompletar y validación del ticker

El botón **Autocompletar desde fuente** del alta le pregunta a la fuente elegida
si el ticker existe y trae los datos que tenga (nombre, país, moneda, mercado,
sector, industria). Sirve como validación previa: si la fuente no reconoce el
ticker, avisa y no completa nada. La importación hace esa misma verificación en
cada fila.

> **Con la fuente Calculado, el autocompletado siempre dice que sí y no completa
> nada.** No hay proveedor externo al que preguntarle, así que no valida ni trae
> metadatos. Un sintético mal escrito no se detecta en el alta: aparece recién
> cuando falla su cálculo.

## La fuente de fundamentales

Es un campo distinto e independiente del de precios. Hoy la única disponible es
**Yahoo Finance**, y trae por trimestre: Revenue, Gross Profit, Operating Income,
Net Income, EBITDA, Total Debt, Equity, Shares, FCF, Operating CF, EPS actual y
EPS estimado.

Dejarla vacía es una decisión válida y es lo correcto para índices, ETFs y
sintéticos: **un activo sin fuente de fundamentales queda directamente afuera de
las corridas de fundamentales**, no se lo intenta descargar y no genera error. Si
un activo con balances aparece sin ratios, lo primero que hay que mirar es si
tiene la fuente asignada — ver
[Actualización de fundamentales](/manual/actualizacion-de-fundamentales).

## Qué pasa cuando una fuente falla

Las fallas son **por activo y no cortan la corrida**: los demás siguen
actualizándose normalmente. Cada intento queda registrado con su resultado y el
motivo exacto en [Actualización de precios](/manual/actualizacion-de-precios).

Lo importante es que **una descarga fallida no destruye lo que ya tenías**: el
borrado del historial y la escritura de los datos nuevos ocurren juntos, así que
si la fuente no responde el activo se queda con la serie anterior intacta y solo
se anota el error. Incluso en la redescarga completa.

Los errores más comunes y qué significan:

| Lo que ves | Qué pasó |
|---|---|
| "No se encontraron datos de precio" | El ticker no existe en la fuente o está mal escrito. Corregilo y reintentá. |
| "Ticker no reconocido" al validar con **Ambito** | Le pediste a esa fuente algo que no sea el Riesgo País. |
| "Sin fórmula" en un activo **Calculado** | El activo quedó marcado como calculado pero nunca se le definió la fórmula. Va a fallar en cada actualización hasta que se la crees. |

Cuando la caída es del proveedor y no del ticker (una demora, un bloqueo por
exceso de pedidos), la actualización general **reintenta esos activos uno por
uno** después de la descarga en bloque. Por eso una corrida puede terminar bien
aunque en el momento hubiera habido intermitencia.

## Dos sutilezas que sorprenden

**Los precios de Yahoo vienen ajustados, y el ajuste es retroactivo.** La serie
llega corregida por splits y dividendos, o sea que un precio de hace cinco años
puede cambiar hoy si el activo pagó un dividendo o dividió su acción. La
actualización diaria no lo detecta: solo mira desde el último día guardado hacia
adelante. Cuando sospeches que la fuente reescribió la historia, la única forma
de alinearla es **Redescargar completo** sobre ese activo, que es la operación
más pesada de la pantalla de precios — usala sobre una selección chica.

**Cambiarle la fuente a un activo que ya tiene historia no borra esa historia.**
La próxima actualización sigue desde el último día guardado, pero pidiéndoselo al
proveedor nuevo: te queda una serie con un pedazo viejo de una fuente y un pedazo
nuevo de otra, con criterios de ajuste que pueden no coincidir. El salto es
difícil de ver en el gráfico y contamina todos los indicadores calculados sobre
esa serie. Si cambiás la fuente de precios, **redescargá el activo completo
inmediatamente después**.
