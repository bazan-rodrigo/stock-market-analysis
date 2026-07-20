---
slug: regimen-de-tendencia
title: Régimen de Tendencia — configuración
chapter: 7. Configuración
order: 740
roles: admin
page: /admin/regime-config
---

El **régimen de tendencia** es la etiqueta que responde "¿este activo está
alcista, lateral o bajista?" en las tres temporalidades (diaria, semanal y
mensual). No se calcula al abrir una pantalla: es un indicador más del
[pipeline](/manual/conceptos-pipeline), pre-calculado para todos los activos y
todas las fechas. Esta pantalla define **con qué reglas** se calcula, para todo
el sistema a la vez — no hay configuración por activo ni por cartera.

Lo que dependa de acá: el coloreado **Régimen** del gráfico y la solapa
**Panel de Indicadores** del [Análisis de Activo](/manual/analisis-de-activo),
el [Mapa de Tendencia](/manual/mapa-de-tendencia), las señales que usan la
tendencia como insumo (y por lo tanto el
[Screener](/manual/screener-de-senales) y los rankings de estrategia) y los
agregados de tendencia por sector, mercado, industria, país y tipo de
instrumento.

## Los diez regímenes

Hay tres regímenes base — **Alcista**, **Lateral** y **Bajista** — y dos
matices que los combinan: *naciente* (la zona todavía es corta) y *fuerte* (la
pendiente es muy pronunciada). El lateral **no tiene versión fuerte**: por
definición no tiene pendiente que destacar.

Cuando el sistema promedia la tendencia de un grupo necesita convertir cada
etiqueta en un número, y usa esta tabla fija (**no es editable desde ninguna
pantalla**):

| Régimen | Puntaje |
|---|---|
| **Alcista Fuerte** | +100 |
| **Alcista Naciente Fuerte** | +75 |
| **Alcista** | +60 |
| **Alcista Naciente** | +40 |
| **Lateral Naciente** | +5 |
| **Lateral** | 0 |
| **Bajista Naciente** | −40 |
| **Bajista Naciente Fuerte** | −75 |
| **Bajista** | −60 |
| **Bajista Fuerte** | −100 |

Vale la pena leer el orden con atención, porque no es el intuitivo: una
tendencia **naciente fuerte** puntúa *más* que una alcista consolidada normal
(+75 contra +60), pero una naciente *sin* fuerza puntúa bastante menos (+40).
La lectura implícita es "un arranque violento vale más que una tendencia vieja
y tibia". Del lado bajista pasa lo mismo con el signo invertido. Y el *Lateral
Naciente* vale +5 en lugar de 0: un lateral recién estrenado se considera
apenas mejor que uno que ya lleva meses.

> Esta tabla es la que se usa para **promediar por grupo**. Para las señales
> sobre un activo concreto, el puntaje lo definís vos: la tendencia es un
> indicador de categorías y se traduce con un **mapa discreto**, asignando a
> mano el valor de cada uno de estos diez regímenes.

## Cómo se determina el régimen de cada barra

Sobre los cierres de la temporalidad correspondiente se calcula una EMA (media
móvil exponencial) y se mide su **pendiente**: cuánto varió esa media, en
porcentaje, respecto de N barras atrás. Con eso:

- Pendiente **mayor** al umbral **Y** precio **por encima** de la EMA →
  Alcista.
- Pendiente **menor** al umbral negativo **Y** precio **por debajo** de la EMA
  → Bajista.
- **Todo lo demás** → Lateral.

Las dos condiciones se exigen juntas, y ahí aparece la primera sorpresa: un
activo con la media subiendo con fuerza pero cotizando por debajo de ella
queda **Lateral**, no alcista. Lo mismo un precio muy por encima de una media
plana. El lateral no es solo "el medio", es también "las señales no coinciden".

Después, el cambio de régimen **se confirma**: la etiqueta no cambia hasta que
el nuevo régimen se sostenga la cantidad de barras configurada. Es el freno
anti-serrucho, y la barra que confirma ya cuenta como parte del régimen nuevo.

Por último, sobre la zona ya confirmada se deciden los matices: es **naciente**
si dura menos que las barras configuradas, y **fuerte** si la pendiente supera
al umbral multiplicado por el multiplicador.

## Los controles

| Campo | Qué controla | Valores admitidos |
|---|---|---|
| **EMA diaria** | Barras de la media sobre velas diarias. 200 ≈ tendencia de largo plazo. | 10 a 500 |
| **EMA semanal** | Barras de la media sobre velas semanales. 50 ≈ 1 año. | 5 a 300 |
| **EMA mensual** | Barras de la media sobre velas mensuales. | 3 a 100 |
| **Lookback pendiente** | Cuántas barras atrás se mira para medir la pendiente. Más barras = señal más suave y más lenta. | 1 a 100 |
| **Umbral pendiente (%)** | Variación mínima de la media para declarar tendencia. Más alto = más laterales. | 0,01 a 20 |
| **Barras confirmación** | Barras seguidas en el régimen nuevo antes de aceptarlo. | 1 a 20 |
| **Barras naciente** | Una zona más corta que esto se etiqueta *naciente*. | 1 a 200 |
| **Mult. fuerte** | La pendiente tiene que superar umbral × este número para ser *fuerte*. | 1,0 a 10,0 |

**Solo el período de la EMA es por temporalidad.** El lookback, el umbral, la
confirmación, las barras de naciente y el multiplicador son **únicos y
compartidos por las tres**, y se cuentan en barras de cada una: un lookback de
20 significa 20 ruedas en la diaria, 20 semanas (casi cinco meses) en la
semanal y 20 meses en la mensual. Lo mismo con la confirmación y con naciente:
un valor cómodo para la diaria puede ser brutal para la mensual.

> **Poner 1 en «Barras confirmación» no desactiva la confirmación:** el mínimo
> efectivo son 2 barras, así que 1 y 2 se comportan igual. Para que un régimen
> se declare siempre hacen falta al menos dos barras seguidas.

> **Un activo con poca historia no tiene régimen.** Hace falta, como mínimo,
> período de la EMA + lookback + confirmación barras *de esa temporalidad*. Con
> los valores de fábrica eso es ~223 ruedas para la diaria (casi un año), 73
> semanas para la semanal y 43 meses para la mensual: es normal que un activo
> nuevo aparezca sin tendencia mensual durante años. También queda sin
> etiqueta el tramo inicial de la historia de cualquier activo, hasta la
> primera confirmación. Un activo sin etiqueta no suma ni resta en el promedio
> del grupo, simplemente no participa.

## La sutileza grande: naciente y fuerte se deciden por la zona entera

Los matices no se calculan barra por barra sino **por zona**: se toma la
duración total de la zona y la pendiente de su última barra, y esa etiqueta se
aplica hacia atrás a todas las barras de la zona.

Para las zonas ya cerradas esto es estable y no molesta. Pero la zona **en
curso** —la que llega hasta hoy— sigue creciendo, y eso tiene una consecuencia
que sorprende: **el valor guardado para fechas pasadas de la zona actual puede
cambiar solo, sin que se toque ninguna configuración**. El día que la zona
supera las barras de naciente, todas sus fechas —también las viejas— dejan de
ser nacientes de golpe. Y como la fuerza se mide con la pendiente de la última
barra, un cambio de pendiente de hoy puede convertir toda la zona en curso de
*Alcista* a *Alcista Fuerte* y al revés.

Es intencional y tiene su lógica (la etiqueta describe la zona, no la barra),
pero conviene tenerlo presente al leer historia: si comparás una captura de la
semana pasada con la de hoy y las etiquetas viejas no coinciden, es esto y no
un error. Es un pariente cercano de la regla de que
[el último día siempre es preliminar](/manual/conceptos-pipeline).

## Guardar y recalcular

**Guardar** escribe la configuración y confirma con un cartel verde. Nada más:
**guardar no recalcula nada**, y hasta que recalcules conviven dos verdades
distintas en la app.

> **El gráfico te va a mentir apenas guardes.** El coloreado **Régimen** del
> Análisis de Activo se calcula en el momento, sobre los precios y con la
> configuración vigente, así que refleja los parámetros nuevos de inmediato.
> El **Panel de Indicadores**, el Mapa de Tendencia, el Screener y las
> estrategias leen lo guardado, o sea lo viejo. Ver el gráfico ya actualizado
> **no** significa que el recálculo esté hecho.

> **Cambiar cualquiera de estos valores invalida toda la historia de
> tendencia, no solo la última fecha.** La media exponencial arrastra toda la
> serie desde el principio, así que con parámetros nuevos cualquier fecha
> pasada puede dar distinto. Es una operación de las caras: planificala como
> planificarías un recálculo completo.

El orden para dejar todo consistente, desde el
[Centro de Datos](/manual/centro-de-datos):

1. **Indicadores Técnicos.** El sistema detecta por su cuenta que la tendencia
   quedó desactualizada y reescribe la historia de los activos afectados,
   incluso en modo **Ejecutar** (incremental): esa corrida tarda mucho más que
   una noche normal. **Recalcular completo** llega al mismo resultado y no deja
   lugar a dudas, a costa de rehacer también todos los demás indicadores.
2. **Señales y Estrategias, en «Recalcular completo».** Este paso **no** se
   entera solo. Los promedios por grupo, las señales y los rankings guardados
   se calcularon con los regímenes anteriores y ahí se quedan; una corrida
   incremental solo arregla las fechas nuevas y te deja la historia partida en
   dos criterios.

## Cuándo conviene tocar esto

Casi nunca, y de a un parámetro por vez. Los motivos válidos habituales son:
demasiados cambios de régimen sin sustancia (subí **Barras confirmación** o el
**Umbral pendiente**), la tendencia reacciona tarde a giros reales (bajá el
umbral o el período de la EMA), o *fuerte* aparece en casi todo o casi nunca
(ajustá **Mult. fuerte**, que es el cambio más barato de interpretar porque no
altera qué zonas existen, solo cómo se las califica).

Como cada prueba se paga con un recálculo largo, la forma sensata de validar
un cambio no es mirar dos o tres gráficos: es correr el recálculo y comparar el
comportamiento de una estrategia que dependa de la tendencia con el
[Backtest](/manual/backtest).
