---
slug: volatilidad-atr
title: Volatilidad ATR — configuración
chapter: 7. Configuración
order: 750
roles: admin
page: /admin/volatility-config
---

Acá se define **qué significa "alta volatilidad"** para todo el sistema. Los
parámetros de esta pantalla son los que producen el sombreado de fondo del
gráfico técnico y los indicadores de volatilidad que después usan las señales y
las estrategias.

Es una **configuración única y global**: no hay una por activo ni por
temporalidad. Los mismos valores se aplican a los tres marcos temporales
(diario, semanal y mensual) y a todos los activos. Solo la ven y la editan los
usuarios **admin**.

## La idea: volatilidad relativa, no absoluta

El sistema calcula el ATR (rango medio verdadero) del activo y después lo
compara **contra la propia historia de ese activo en esa temporalidad**, no
contra un valor fijo. Que un activo esté en régimen **alta** significa que su
ATR de hoy está por encima del percentil que definas *de su propia serie*, no
que se mueva mucho comparado con otro activo.

La consecuencia práctica es fuerte y conviene tenerla presente: **todos los
activos tienen días de volatilidad extrema**, incluso el más tranquilo de la
cartera. Un bono aburrido va a mostrar franjas rojas en sus momentos más
agitados, aunque en términos absolutos se mueva menos que una acción en régimen
"baja". Estos regímenes sirven para comparar un activo consigo mismo a lo largo
del tiempo, no para comparar activos entre sí. Para eso último está el valor
numérico del percentil, que sí es comparable porque todos están en la misma
escala 0-100.

Los cortes se recalculan sobre **toda la historia disponible** del activo, no
sobre una ventana móvil: una franja marcada "alta" en 2008 es alta contra la
historia completa, la de hoy incluida.

La excepción es el valor **vigente**, el que muestra el screener: ese se calcula
solo sobre los últimos cuatro años de cotizaciones aproximadamente. En un activo
con historia muy larga, el régimen que ves en el screener y el de la última
franja del gráfico pueden no coincidir.

---

## Los campos

### Cálculo del ATR

| Campo | Rango | Qué hace |
|---|---|---|
| **Período ATR** | 2 a 100 | Barras usadas para el ATR (suavizado de Wilder). Estándar 14. Más bajo = más reactivo, más cambios de régimen. |
| **Barras confirmación** | 1 a 20 | Barras seguidas en el régimen nuevo antes de darlo por válido. Es el filtro anti-ruido. |

### Umbrales de percentil

| Campo | Rango | Regla que aplica |
|---|---|---|
| **P_bajo (%)** | 5 a 49 | ATR **igual o por debajo** de ese percentil → régimen **baja**. |
| **P_alto (%)** | 51 a 95 | ATR **igual o por encima** → **alta**. Entre P_bajo y P_alto → **normal**. |
| **P_extremo (%)** | 60 a 99 | ATR **igual o por encima** → **extrema**. Tiene prioridad sobre *alta*. |

Los tres se evalúan en cascada de arriba hacia abajo: primero *extrema*, después
*alta*, después *baja*, y lo que no cae en ninguna es *normal*. Por eso *alta*
es en realidad la banda **entre P_alto y P_extremo**: si los ponés muy juntos
(por ejemplo 75 y 78), casi todo lo agitado se va a clasificar como *extrema* y
*alta* casi no va a aparecer.

### Clasificación de duración

| Campo | Rango | Qué hace |
|---|---|---|
| **Duración corta (%)** | 10 a 49 | Tramos cuya duración queda en ese percentil o menos → **corta**. |
| **Duración larga (%)** | 51 a 95 | Tramos que llegan a ese percentil o más → **larga**. En el medio → **media**. |

Al guardar se valida primero que **no falte ningún campo**, y después dos
condiciones de orden: **P_bajo < P_alto < P_extremo** y **duración corta <
duración larga**. Si algo de eso no se cumple, la pantalla avisa y no guarda
nada.

---

## Sutilezas que sorprenden

**La confirmación atrasa el inicio de la franja.** El régimen nuevo se activa
recién en la barra que completa las barras de confirmación, y esa barra ya
cuenta como parte del régimen nuevo. Con 3 barras de confirmación, el sombreado
empieza dos barras después de que el ATR cruzó el umbral. No es un error de
dibujo: es el precio de no marcar cada pico aislado como cambio de régimen.

**Poner 1 en «Barras confirmación» no desactiva el filtro.** Para estrenar un
régimen que no venía candidateándose el sistema exige siempre **al menos 2**
barras. Si querés el mínimo de suavizado, 1 y 2 dan el mismo resultado.

**El arranque de la historia queda sin sombrear.** Hasta que se confirma el
primer régimen no hay franja, así que el tramo inicial del gráfico aparece
limpio. Además, un activo necesita al menos **el triple del período de ATR** en
barras para tener regímenes: con período 14 son 42 barras. En diario es
irrelevante, pero **en mensual son 42 meses**, es decir tres años y medio de
historia. Un activo joven puede no tener sombreado mensual alguno mientras el
diario funciona perfecto.

**La duración se mide contra los tramos ya cerrados de ese mismo régimen.** El
tramo vigente no entra en la referencia, y si el activo no tiene al menos **3
tramos cerrados** de ese régimen, todos se clasifican como **media**. Por eso
*extrema* —que por definición es rara— suele mostrarse como "media" durante
mucho tiempo. Y por eso el tramo en curso arranca casi siempre como **corta** y
va migrando a *media* y *larga* a medida que se sostiene: no es que haya
cambiado el régimen, cambió cuánto lleva.

**Un día nuevo puede reclasificar el pasado.** Como los cortes son percentiles
sobre toda la muestra, una racha de volatilidad inédita corre los umbrales hacia
arriba y puede convertir en *normal* algo que ayer figuraba como *alta*, en
fechas de hace años. Es esperable y correcto: cambió la referencia, no el dato.

---

## Dónde se ve el resultado

**En el gráfico técnico** de [Análisis de Activo](/manual/analisis-de-activo),
con el control **Régimen de Volatilidad**: sombrea el fondo de punta a punta
según el régimen vigente en cada tramo, siguiendo la frecuencia elegida (D/W/M).

| Régimen | Color de fondo |
|---|---|
| **extrema** | rojo intenso |
| **alta** | naranja |
| **normal** | gris |
| **baja** | azul |

Al lado del control aparece la **etiqueta del régimen vigente** con su duración
(por ejemplo *Alta | Larga*), en el color del régimen. El sombreado no trae
detalle por tramo: el percentil de ATR de cada franja no se muestra en el
gráfico.

**En el resto del sistema**, como indicadores calculados que podés usar en
señales, filtros y estrategias:

- **Volatility Daily / Weekly / Monthly** — categórico, combina régimen y
  duración (`alta_larga`, `normal_corta`, …). Es el candidato natural para una
  señal de tipo *mapa discreto*.
- **ATR Percentile Daily / Weekly / Monthly** — numérico de 0 a 100, el percentil
  crudo sin regímenes ni confirmación. Sirve para señales de *umbrales* o de
  *rango lineal* y, a diferencia del régimen, es comparable entre activos.

---

## Después de guardar

> Guardar **no recalcula los indicadores**. El sombreado del gráfico técnico es
> la única excepción: se arma en el momento con los parámetros vigentes, así que
> muestra los valores nuevos apenas recargás la pantalla. La **etiqueta del
> régimen vigente**, el screener y todo lo que consuma *Volatility* o *ATR
> Percentile* siguen con la clasificación vieja hasta que corras la
> actualización de indicadores técnicos desde el
> [Centro de Datos](/manual/centro-de-datos).

> Ojo con el efecto secundario: justo después de guardar, y hasta que recalcules,
> el sombreado del gráfico y la etiqueta que está al lado pueden **contradecirse**
> — uno ya usa los parámetros nuevos y la otra todavía no.

Como cambiar estos parámetros reescribe la historia **completa** de los
indicadores de volatilidad —no solo el último día—, tené en cuenta el efecto
aguas abajo: si alguna señal o estrategia usa *Volatility* o *ATR Percentile*,
sus resultados históricos quedaron calculados con los parámetros anteriores y
hay que rehacerlos con un **recálculo completo**. Es la regla general de
[cómo se calcula todo](/manual/conceptos-pipeline): si cambiaste una definición,
lo viejo quedó con la definición vieja.

> Es una configuración para tocar poco y con criterio. Cada edición implica
> recalcular volatilidad para todos los activos y, si hay estrategias que la
> consumen, rehacer también su historia de señales y rankings — una tarea que en
> una base grande se mide en minutos, no en segundos. Si estás probando
> sensibilidad, cambiá **un parámetro por vez** y comparalo contra el anterior.
