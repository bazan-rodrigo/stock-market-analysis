# Formato de packs de señales y estrategias — SPEC v1

Contrato de intercambio para modelar **señales** y **estrategias** de esta
aplicación sin acceso a su código. Está escrito para que lo pueda seguir tanto
una persona como un modelo de lenguaje: es autosuficiente salvo por una cosa
—el **catálogo de la instalación**— que se entrega aparte (§7).

Un *pack* es **un archivo JSON** con señales y estrategias: o bien una
estrategia junto con todas las señales que usa, o bien un catálogo de señales
publicado aparte de las estrategias que lo consumen (§2). Se importa desde la
aplicación en dos pasos y no requiere tocar la base ni escribir código.

> **Este documento describe el formato, no recomienda inversiones.** Los
> umbrales y pesos de los ejemplos son ilustrativos.

---

## 1. Cómo se usa (flujo completo)

Todo pasa por la pantalla **Packs** (`/admin/packs`, requiere rol admin), que
junta las dos descargas, el ensayo y la importación.

1. **Conseguir las dos piezas del estándar**, con los botones del primer paso
   de esa pantalla:
   - **Especificación**: este documento. Es igual en todas las instalaciones.
   - **Catálogo**: un `.json` con los indicadores disponibles, sus tipos y
     categorías, los sectores/mercados/países cargados y las señales que ya
     existen. Sin esto no se puede saber qué `indicator_key` son válidos:
     **cambian de una instalación a otra**. El mismo botón está también en la
     pantalla de Señales.
2. **Escribir el pack** siguiendo este documento.
3. **Validarlo offline**, sin base y sin la app:
   `python scripts/validate_pack.py mi_pack.json --catalog catalogo.json`
   Devuelve los mismos errores que devolvería el import, más avisos de las
   trampas silenciosas (§8). Iterar hasta que salga limpio.
4. **Subirlo y revisar el ensayo**: subir el archivo **no escribe nada**. La
   pantalla muestra los errores, los avisos y —fila por fila— qué va a **crear**
   y qué va a **actualizar**, y de quién es lo que pisaría. Con un solo error el
   botón *Importar* queda deshabilitado.
5. **Importar**: aplica los dos pasos en el orden que exigen las referencias
   —primero las señales, después las estrategias, que las referencian por
   `key`—, y completa la misma tabla con el resultado de cada fila.
6. **Calcular la historia**: Centro de Datos → *Señales y Estrategias →
   Ejecutar*, con alcance en la estrategia nueva. Hasta que eso corra, la
   estrategia existe pero no tiene resultados.

> **Si quien escribe el pack es un modelo conectado a esta aplicación** (la
> pantalla *Conexión IA* publica un servicio MCP), los pasos 1 a 4 no necesitan
> que nadie le pase archivos: `get_pack_spec` devuelve este documento,
> `get_catalog` el catálogo de la instalación, y `preview_pack` corre el mismo
> ensayo del punto 4 contra esta base —sin escribir nada— para poder corregir
> antes de entregar. El ensayo exige rol admin, igual que la pantalla; los dos
> primeros no. **Los pasos 5 y 6 siguen siendo de una persona**: ninguna IA
> importa ni dispara corridas.

La pantalla Packs acepta **solo el archivo JSON**. Las planillas Excel (§10)
siguen entrando por el camino histórico, en dos pantallas y sin ensayo previo:
primero *Señales → Importar* y después *Estrategias → Importar*.

---

## 2. El archivo

```json
{
  "spec_version": 1,
  "pack": "momentum_de_lideres",
  "description": "Compra los activos más fuertes de un universo en tendencia.",
  "signals": [ /* … objetos señal, §3 … */ ],
  "strategies": [ /* … objetos estrategia, §5 … */ ]
}
```

| Campo | Obligatorio | Qué es |
|---|---|---|
| `spec_version` | recomendado | Versión del formato. Hoy `1`. Un número distinto se rechaza con mensaje; ausente se asume `1`. |
| `pack` | no | Identificador corto del pack (`snake_case`). Se usa para nombrar archivos. |
| `description` | no | Para quien lo lea. La app la ignora. |
| `signals` | sí (ver nota) | Lista de señales. |
| `strategies` | sí (ver nota) | Lista de estrategias. |

Nota: el archivo debe traer al menos una de las dos listas. Hay **dos formas
sanas** de armarlo:

- **Pack completo** — trae las dos listas y es **autosuficiente**: incluye
  *todas* las señales que su estrategia usa, aunque ya existan en la
  instalación de destino. Una señal repetida entre packs no genera conflicto:
  el import actualiza por `key`, no duplica.
- **Catálogo de señales** — solo `signals`, publicado aparte de las estrategias
  que lo consumen. Es la forma de un catálogo curado (una sola señal por
  indicador, todas orientadas igual) que después varias estrategias usan. Por
  eso el aviso de "señales que ninguna estrategia usa" (§8) **no se emite**
  cuando el archivo no trae `strategies`: ahí es la forma del archivo, no un
  descuido.

Lo que conviene evitar es la mezcla: un pack con estrategias que además
arrastra señales sueltas que ninguna de ellas usa.

Codificación **UTF-8**. Se admiten tildes y `ñ` en cualquier texto, incluidas
las `key`.

---

## 3. Señales

Una señal traduce **un indicador** a un **puntaje de −100 a +100** para cada
activo y cada día.

```json
{
  "key": "rsi_sobreventa",
  "name": "RSI en sobreventa",
  "description": "RSI invertido: cuanto más sobrevendido, mejor puntaje.",
  "indicator_key": "rsi_daily",
  "formula_type": "range",
  "params": { "min": 70, "max": 30, "clamp": true },
  "publica": true
}
```

| Campo | Obligatorio | Reglas |
|---|---|---|
| `key` | sí | Identificador único, máx. **50** caracteres. Es la clave del upsert: reimportar con la misma `key` **actualiza** la señal existente. No distingue mayúsculas. |
| `name` | sí | Nombre visible, máx. **100** caracteres. Si falta se usa la `key`. |
| `description` | no | Texto libre. |
| `indicator_key` | **sí** | Código de indicador del catálogo (§7). Una señal sin indicador se rechaza: no tendría qué leer. |
| `formula_type` | sí | `discrete_map` \| `threshold` \| `range`. |
| `params` | sí | Objeto JSON; su forma depende de la fórmula (§4). |
| `publica` | no | `true` = la ven todos los usuarios; `false` = solo su dueño y los admins. **Ausente = privada.** |

**Elegir la fórmula por el tipo del indicador** (campo `type` del catálogo):

| `type` | Qué devuelve el indicador | Fórmula |
|---|---|---|
| `str` | Categorías (`bullish`, `alta_corta`, …) | `discrete_map` |
| `num` | Números | `threshold` o `range` |

Cruzarlas es un error que el validador rechaza: `discrete_map` compara contra
texto y con un indicador numérico **nunca puntúa**.

---

## 4. Las tres fórmulas

### `discrete_map` — categoría → puntaje

```json
{ "formula_type": "discrete_map",
  "params": { "map": { "bullish_strong": 100, "bullish": 60,
                       "lateral": 0, "bearish": -60, "bearish_strong": -100 } } }
```

- `map`: objeto no vacío, valores numéricos.
- **Una categoría que no esté en el mapa deja la señal sin valor ese día**, y
  una señal sin valor **no cuenta en el promedio de la estrategia — no cuenta
  como cero**. Es el error más frecuente: mapear solo las categorías
  "interesantes" deja la señal muda justo en los casos ambiguos. El catálogo
  lista todas las categorías posibles de cada indicador (`values`);
  cubrilas todas.

### `threshold` — tramos

```json
{ "formula_type": "threshold",
  "params": { "thresholds": [[-5, 100], [-15, 50], [-30, 0], [null, -50]] } }
```

- `thresholds`: lista no vacía de pares `[límite, puntaje]`.
- Se evalúa **en orden, de arriba hacia abajo: gana el primer límite que el
  valor SUPERA** (estrictamente mayor).
- Por lo tanto los límites van **de mayor a menor**. La app los ordena sola
  cuando se cargan por pantalla, pero **en un pack quedan como los escribas**:
  mal ordenados, el tramo más permisivo absorbe todo y los de abajo nunca se
  alcanzan — sin ningún error visible.
- El par final `[null, puntaje]` es el "en cualquier otro caso". Es opcional,
  pero sin él los valores que no superan ningún límite quedan **sin puntaje**.

### `range` — escala lineal

```json
{ "formula_type": "range",
  "params": { "min": -3, "max": 3, "clamp": true } }
```

- `min` es el valor del indicador que vale **−100**; `max` el que vale
  **+100**; el punto medio da 0. Interpolación lineal entre ambos.
- **`min` puede ser mayor que `max`**: así se invierte la escala (el ejemplo
  del RSI en §3 puntúa mejor cuanto más bajo es el RSI).
- `clamp` (default `true`) recorta a ±100 lo que quede fuera del rango. Con
  `false` el puntaje se desborda: en una escala de −3 a 3, un valor de **6 da
  200**. Un componente así distorsiona el promedio ponderado y hace que el
  ranking lo domine un solo activo con un valor extremo.
- `min` y `max` deben ser numéricos y distintos.

---

## 5. Estrategias

Una estrategia = **filtro de elegibilidad** (quién entra) + **ranking**
(en qué orden).

```json
{
  "name": "Momentum de líderes",
  "description": "Los más fuertes del universo en tendencia.",
  "publica": true,
  "filter": { "op": "AND", "children": [ /* … §6 … */ ] },
  "components": [
    { "signal_key": "retorno_52w",  "weight": 3 },
    { "signal_key": "tendencia_d",  "weight": 1 }
  ]
}
```

| Campo | Obligatorio | Reglas |
|---|---|---|
| `name` | sí | Máx. **100** caracteres. Clave del upsert (no distingue mayúsculas). |
| `description` | no | Texto libre. |
| `publica` | no | Igual que en las señales. **Ausente = privada.** |
| `filter` | no | Árbol de condiciones (§6). Sin filtro, la estrategia rankea **todos** los activos de la base. |
| `components` | **sí** | Al menos uno. Una estrategia sin componentes no puntúa nada y se rechaza. |

**Ranking**: promedio ponderado de los puntajes de los componentes, con el
divisor en valor absoluto:

```
SCORE = Σ(peso · señal) / Σ|peso|
```

- `weight` es un número **distinto de 0** (default 1). Solo importa la
  proporción entre pesos: `3/2/1` y `6/4/2` dan el mismo ranking.
- **El peso puede ser NEGATIVO**: la señal aporta al revés, es decir el activo
  puntúa alto donde esa señal puntúa bajo. Sirve para pedir dos cosas opuestas
  en una misma estrategia — *"momentum alto **pero** volatilidad baja"* — y
  para usar una señal existente invertida **sin duplicarla** en el catálogo
  (que además no podrías: las señales las crea un administrador, §8).

  ```json
  {
    "components": [
      { "signal_key": "momentum_12m",  "weight":  2 },
      { "signal_key": "volatilidad_d", "weight": -1 }
    ]
  }
  ```

  Ese ejemplo da `SCORE = (2·momentum − 1·volatilidad) / 3`. Como el divisor
  es Σ|peso| = 3 (no Σpeso = 1), el score sigue viviendo en **−100..100**, que
  es lo que hace que los umbrales absolutos de las reglas de trade signifiquen
  siempre lo mismo.
- `weight: 0` se **rechaza**: un componente con peso 0 no aporta al score ni al
  divisor, así que no hace nada. Sacá el componente.
- **Las señales sin valor se saltean**: el promedio se calcula solo sobre los
  componentes que puntuaron ese día, no cuentan como cero. Si ninguno puntúa,
  el activo no aparece en el ranking.
- El ranking es **transversal**: la posición de un activo depende de todos los
  demás en esa fecha.

> **Ojo con los indicadores que no cubren a todos los activos.** Saltear no es
> excluir: el activo sigue en el ranking, puntuado con los componentes que le
> quedan y los pesos renormalizados entre ellos. Como el componente que le falta
> tampoco puede castigarlo, **le va sistemáticamente mejor que a uno que sí tiene
> el dato**. Con dos componentes de peso 1, un activo que puntúa +80 en el
> primero y −60 en el segundo termina en 10; otro que puntúa +80 y no tiene dato
> en el segundo termina en 80, y gana el ranking por carecer del dato.
>
> El caso típico es el volumen: los activos sintéticos y las conversiones de
> moneda no tienen volumen propio (un cociente entre dos precios no lo tiene), y
> en esa instalación son muchos. Si tu estrategia puntúa por volumen, **agregá la
> condición también al filtro de elegibilidad** (§6): ahí el dato faltante sí
> deja al activo afuera, que es lo que querés. La misma precaución vale para
> cualquier indicador que el catálogo describa como de cobertura parcial.

**Regla de visibilidad**: una estrategia **pública solo puede usar señales
públicas** (si no, filtraría a otros usuarios una definición privada). Una
estrategia privada puede usar públicas y las propias. Lo más simple es marcar
todo el pack con `publica: true` o todo con `false`.

---

## 6. El filtro de elegibilidad

Árbol de grupos `AND`/`OR` con condiciones en las hojas. El activo que no lo
cumple **no aparece** en el ranking.

```json
{
  "op": "AND",
  "children": [
    { "cond": { "left":  { "type": "indicator", "key": "trend_weekly" },
                "operator": "in",
                "right": { "type": "const",
                           "value": ["bullish", "bullish_strong"] } } },
    { "cond": { "left":  { "type": "indicator", "key": "dist_sma200" },
                "operator": ">",
                "right": { "type": "const", "value": 0 } } },
    { "cond": { "left":  { "type": "attribute", "key": "instrument_type" },
                "operator": "in",
                "right": { "type": "const", "value": ["Equity", "FUND"] } } }
  ]
}
```

**Nodos**

| Nodo | Forma |
|---|---|
| Grupo | `{"op": "AND"\|"OR", "children": [nodo, …]}` — no puede estar vacío |
| Condición | `{"cond": {"left": operando, "operator": op, "right": operando}}` |

**Operandos**

| `type` | `key` / `value` | Qué vale |
|---|---|---|
| `indicator` | `key`: código del catálogo | Valor del indicador del activo ese día |
| `signal` | `key`: `key` de una señal | Puntaje de la señal (numérico, −100..100) |
| `attribute` | `key`: `sector`, `market`, `industry`, `country`, `instrument_type`, `currency`, `benchmark`, `synthetic` | Característica del activo: su grupo, su moneda, el activo que le sirve de benchmark o el tipo de fórmula si es sintético |
| `const` | `value`: número, texto o lista | Valor fijo de comparación |

**Operadores**

| Operadores | Uso |
|---|---|
| `>` `>=` `<` `<=` | Solo con **ambos lados numéricos** |
| `=` `!=` | Numéricos o de texto (mismo tipo de los dos lados) |
| `in` `not_in` | El lado derecho **debe** ser un `const` con **lista** |

Un operando `attribute` es un caso aparte: admite `=` `!=` `in` `not_in` contra
el nombre o contra el id, indistintamente, y **rechaza los operadores de orden**
—un sector o un mercado no se ordenan—. No entra en la regla de "mismo tipo de
los dos lados": comparar un atributo con su propio id es válido.

**Todo atributo puede estar vacío, y el vacío es un valor con nombre.** Un
activo puede no tener sector, ni país, ni benchmark. Ese hueco se escribe
`"(sin sector)"`, `"(sin país)"`, `"(sin benchmark)"` —está en el catálogo,
como cualquier otro valor— y sin él sería inexpresable: un dato faltante no
cumple ninguna condición, ni siquiera `!=`. Por eso también vale la vuelta:
`sector != "(sin sector)"` significa "que tenga sector cargado", y una
condición como `sector != "Technology"` **incluye** al activo sin sector.

Dos atributos no salen de una tabla de catálogo:

- **`benchmark`** — el activo contra el que se mide (el que usan los
  indicadores de fuerza relativa). Apunta a **otro activo**, así que su nombre
  es el **ticker**. Sirve para dejar afuera a los activos donde un indicador
  que depende del benchmark nunca se va a poder calcular:

  ```json
  { "cond": { "left":  { "type": "attribute", "key": "benchmark" },
              "operator": "!=",
              "right": { "type": "const", "value": "(sin benchmark)" } } }
  ```

- **`synthetic`** — el tipo de fórmula del activo calculado: `ratio`,
  `weighted_avg`, `weighted_sum`, `index`, o `"(no sintético)"` si es un activo
  común. `synthetic = "(no sintético)"` deja el universo sin activos
  calculados, que es lo que se quiere cuando la conversión de divisas creó un
  sintético por cada activo y esos duplicados compiten en el mismo ranking que
  su original. Un sintético de conversión de moneda es un `ratio` y **no se
  distingue** de un ratio armado a mano.

**Reglas de forma**

- El operando izquierdo **no puede ser** `const`.
- Una lista solo se admite con `in` / `not_in`.
- Los valores de un indicador categórico deben estar en su lista `values` del
  catálogo (un valor inventado se rechaza).
- **Dato faltante = condición NO cumplida.** Un activo sin ese indicador ese
  día queda afuera; el filtro nunca "deja pasar por las dudas".
- Los indicadores se leen *as-of*: la última fila con fecha ≤ la fecha
  evaluada (los semanales y mensuales no tienen fila todos los días). Ese es el
  default, `"resolution": "historic"`, y no hace falta escribirlo. La
  alternativa `"resolution": "current"` en una condición lee el valor
  **vigente** en vez del histórico: para fechas pasadas eso es **sesgo de
  anticipación deliberado** y solo sirve como diagnóstico, no lo uses en un
  pack que vaya a backtestearse.
- Ese arrastre *as-of* tiene un **tope de 45 días**: un valor más viejo que eso
  respecto de la fecha evaluada cuenta como dato faltante y —por la regla de
  arriba— deja al activo afuera. Alcanza para cubrir un indicador mensual, pero
  no para uno que se dejó de calcular ni para un activo que dejó de cotizar.
- **Las señales no se leen *as-of*, sino con fecha exacta** (la misma semántica
  con la que se calcula el score). Una señal sin valor en esa fecha exacta es un
  dato faltante: la condición da falso. En particular, de las fechas anteriores
  a la creación de la señal no hay score que reconstruir hasta que se recalcule
  su historia.

**Atributos: por nombre, no por id.** Escribí `"Technology"`, `"NASDAQ"`,
`"Equity"` — el import los resuelve al id de la instalación de destino. Los
ids internos **no son portables**: son distintos en cada base. (Un número o un
texto de solo dígitos se interpreta como id ya resuelto, para poder reimportar
sin cambios lo que exportó la app.) Los nombres válidos están en el catálogo,
en `attributes`; la comparación no distingue mayúsculas, pero el nombre tiene
que existir tal cual o el import falla con la lista de valores parecidos.

Para `benchmark` el nombre es el **ticker** del activo (`"^GSPC"`, `"SPY"`), y
solo valen los que **hoy son benchmark de al menos un activo** en la
instalación de destino —los que están en `attributes.benchmark` del catálogo—,
más el `"(sin benchmark)"`. Un ticker de solo dígitos (`"7203"`) se resuelve
como ticker y no como id, al revés que el resto de los atributos.

Para `synthetic` el nombre es el tipo de fórmula tal cual (`"ratio"`,
`"index"`, …): no hay ids que resolver, viaja igual entre instalaciones.

---

## 7. Lo que depende de la instalación (el catálogo)

Este documento es igual en todas las instalaciones. **Lo que cambia** —y por
eso viaja aparte, en el JSON del botón *Catálogo*— es:

| Sección | Para qué la necesitás |
|---|---|
| `indicators[]` | Los `indicator_key` válidos: cada entrada los trae en su campo **`code`**. Además `type` (`num`/`str`), `values` si es categórico, `keep_history` y una descripción. |
| `attributes` | Los valores válidos de cada atributo **en esa base**: los nombres de sector, mercado, industria, país, tipo de instrumento y moneda cargados; en `benchmark` los tickers que hoy son benchmark de algún activo; en `synthetic` los tipos de fórmula en uso. Cada lista incluye su `(sin …)`. |
| `signals[]` / `strategies[]` | Lo que ya existe: sirve para no pisar una `key` ajena y para saber qué señales podés reusar. Cada señal viene con su `description` y sus `params`, o sea **con qué criterio puntúa** — no alcanza con el nombre: en un catálogo curado el RSI puede estar definido a la inversa de lo que suponés (§8). |

Un indicador con `keep_history: false` solo tiene valor vigente: una señal
sobre él no tendrá historia y **no sirve para backtest**.

Algunas entradas vienen marcadas con `"virtual": true`: no son indicadores
calculados sino valores que el motor resuelve por su cuenta (hoy `last_close`,
el precio de cierre del día). Se usan como cualquier otro `indicator_key`,
tanto en una señal como en el filtro de una estrategia; en el filtro se leen
*as-of*, con el mismo tope de 45 días que el resto.

---

## 8. Qué acepta y qué rechaza el import

**Todo o nada dentro de cada paso.** Si una sola señal es inválida no se
escribe **ninguna** señal, y lo mismo con las estrategias: no hay import
parcial de una lista, y la pantalla muestra el motivo de cada fila.

Pero **los dos pasos son transacciones separadas**: si las señales entran y las
estrategias fallan, las señales quedan cargadas. Por eso el ensayo de la
pantalla Packs valida las dos partes *antes* de escribir nada, y por eso un
error en las señales corta ahí mismo en vez de seguir (continuar solo daría una
cascada de "señal no encontrada" que tapa el problema real).

**Upsert.** Las señales se identifican por `key` y las estrategias por
`name`, sin distinguir mayúsculas: reimportar actualiza la definición
existente (y reemplaza sus componentes) en vez de duplicarla. El dueño de una
definición existente **no cambia**; quien importa queda como dueño de las
nuevas.

**Las señales las escribe solo un administrador.** Es una regla de la
instalación, no del archivo: un pack con la sección `signals` importado por un
usuario que no es administrador se rechaza entero, antes de escribir nada. Un
pack **solo de estrategias** lo importa cualquiera que tenga la pantalla. El
motivo es que el catálogo de señales es **curado**: una sola implementación por
concepto, para que dos estrategias sean comparables entre sí. Si tu pack
necesita una señal que no existe en la instalación, entregásela a un
administrador para que la cargue; el resto del pack no depende de eso.

Consecuencia práctica al escribir packs: **reusá las señales del catálogo**
(la sección `signals[]` del catálogo, §7) antes de proponer una nueva.

Y leelas antes de usarlas: **la orientación de una señal no se deduce del
nombre**. Una instalación puede tener un catálogo donde todas las señales
apuntan para el mismo lado (por ejemplo, +100 siempre es la mejor condición
para comprar), y ahí "RSI diario" puntúa la **sobreventa**, no la fuerza. El
`description` y los `params` de cada señal vienen en el catálogo justamente
para eso. Si necesitás una señal al revés, **no propongas una nueva**: usá la
existente con `weight` negativo (§5).

Se **rechaza** (errores):

- Sección `signals` en un pack importado por alguien que no es administrador.
- `formula_type` desconocido, o `params` con la forma equivocada para esa
  fórmula.
- `indicator_key` ausente o inexistente en la instalación.
- Señal referenciada por una estrategia que no está ni en el pack ni en la
  base.
- Estrategia sin componentes.
- Filtro con JSON inválido, operador desconocido, tipos incompatibles, o
  valores fuera del catálogo de un indicador categórico.
- Nombre de sector/mercado/país/industria/tipo/moneda que no existe en la
  instalación, ticker que no es benchmark de ningún activo ahí, o tipo de
  sintético que no está en uso.
- Estrategia pública que usa señales privadas.
- `source` en una señal o `scope` en un componente: eran las señales de grupo
  y el Alcance de grupo, **removidos** del sistema. Se rechazan en vez de
  ignorarse, porque descartarlos cambiaría el resultado en silencio.

Se **avisa** pero se importa igual (el validador offline los lista como
`AVISO`): mapa discreto incompleto, `thresholds` desordenados o sin tramo
final, `clamp: false`, señal sobre un indicador sin historia, estrategia sin
filtro, y señales que ninguna estrategia del pack usa (cada señal cargada
cuesta cómputo en cada corrida). Este último **solo si el pack trae
estrategias**: en un catálogo de señales (§2) no se emite, porque ahí ninguna
señal tiene estrategia que la use y el aviso sería la lista entera.

**Después de importar**, cambiar los parámetros de una señal **no recalcula lo
ya guardado**: la historia sigue con la definición anterior hasta que corras
un recálculo completo. Es especialmente engañoso al backtestear — sin
recalcular estarías midiendo la versión vieja.

---

## 9. Ejemplo completo mínimo

```json
{
  "spec_version": 1,
  "pack": "ejemplo_minimo",
  "description": "Pullback en tendencia: compra retrocesos dentro de tendencias alcistas.",
  "signals": [
    {
      "key": "ej_rsi_sobreventa",
      "name": "RSI en sobreventa",
      "indicator_key": "rsi_daily",
      "formula_type": "range",
      "params": { "min": 70, "max": 30, "clamp": true },
      "publica": true
    },
    {
      "key": "ej_tendencia_diaria",
      "name": "Régimen de tendencia diario",
      "indicator_key": "trend_daily",
      "formula_type": "discrete_map",
      "params": { "map": {
        "bullish_strong": 100, "bullish_nascent_strong": 90, "bullish": 60,
        "bullish_nascent": 40, "lateral": 0, "lateral_nascent": 0,
        "bearish_nascent": -40, "bearish": -60,
        "bearish_nascent_strong": -90, "bearish_strong": -100 } },
      "publica": true
    }
  ],
  "strategies": [
    {
      "name": "Ejemplo — pullback en tendencia",
      "description": "Retrocesos de corto plazo dentro de tendencias alcistas.",
      "publica": true,
      "filter": {
        "op": "AND",
        "children": [
          { "cond": { "left":  { "type": "indicator", "key": "trend_weekly" },
                      "operator": "in",
                      "right": { "type": "const",
                                 "value": ["bullish", "bullish_strong",
                                           "bullish_nascent_strong"] } } },
          { "cond": { "left":  { "type": "attribute", "key": "instrument_type" },
                      "operator": "=",
                      "right": { "type": "const", "value": "Equity" } } }
        ]
      },
      "components": [
        { "signal_key": "ej_rsi_sobreventa",   "weight": 3 },
        { "signal_key": "ej_tendencia_diaria", "weight": 1 }
      ]
    }
  ]
}
```

Los `indicator_key` de este ejemplo (`rsi_daily`, `trend_daily`,
`trend_weekly`) y el tipo `Equity` **hay que verificarlos contra el catálogo**
de la instalación de destino.

---

## 10. Formato Excel (equivalente)

La app también importa —y exporta— el mismo contenido como planillas. Es el
formato histórico; el JSON es el canónico para intercambio. La conversión va en
las dos direcciones: `python scripts/pack_from_json.py mi_pack.json` genera las
planillas, y `python scripts/pack_to_json.py mi_pack` reconstruye el JSON desde
ellas (útil para pasar al canónico lo que exportó la app).

| Planilla | Hoja | Columnas (en este orden) |
|---|---|---|
| `<pack>_senales.xlsx` | Señales | `key`, `name`, `description`, `indicator_key`, `formula_type`, `params`, `publica` |
| `<pack>_estrategia.xlsx` | Estrategias (1ª) | `name`, `description`, `filter_conditions`, `publica` |
| | Componentes (2ª) | `strategy_name`, `signal_key`, `weight` |

Diferencias con el JSON: `params` y `filter_conditions` van como **texto JSON**
dentro de la celda, `publica` como `si`/`no`, y los componentes se vinculan por
`strategy_name` en vez de anidarse.

---

## 11. Versionado

`spec_version: 1` es la versión actual. Un pack con una versión que la
instalación no entiende se rechaza con un mensaje explícito, nunca se importa
a medias.

Removido de versiones anteriores del sistema (hoy se rechaza):

| Ya no existe | Reemplazo |
|---|---|
| `formula_type: "composite"` | Combinar señales es tarea de la estrategia: usá varios `components` con pesos. |
| `source: "group"` en señales | Las señales de grupo se removieron. |
| `scope` en componentes | El Alcance de grupo se removió. |

---

## 12. Checklist antes de entregar un pack

- [ ] Cada `indicator_key` existe en el catálogo y el `formula_type` coincide
      con su `type`.
- [ ] Los `discrete_map` cubren **todas** las categorías del indicador.
- [ ] Los `thresholds` están de mayor a menor y cierran con `[null, …]`.
- [ ] Cada `signal_key` de los componentes está en `signals` del mismo pack.
- [ ] Los nombres de sector/mercado/tipo existen en el catálogo, escritos como
      figuran ahí.
- [ ] `publica` coherente: si la estrategia es pública, sus señales también.
- [ ] `python scripts/validate_pack.py <pack>.json --catalog catalogo.json`
      sale sin errores, y los avisos que quedan son deliberados.
