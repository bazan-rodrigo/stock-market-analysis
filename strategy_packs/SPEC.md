# Formato de packs de señales y estrategias — SPEC v1

Contrato de intercambio para modelar **señales** y **estrategias** de esta
aplicación sin acceso a su código. Está escrito para que lo pueda seguir tanto
una persona como un modelo de lenguaje: es autosuficiente salvo por una cosa
—el **catálogo de la instalación**— que se entrega aparte (§7).

Un *pack* es **un archivo JSON** con las señales y la estrategia que las usa.
Se importa desde la aplicación en dos pasos y no requiere tocar la base ni
escribir código.

> **Este documento describe el formato, no recomienda inversiones.** Los
> umbrales y pesos de los ejemplos son ilustrativos.

---

## 1. Cómo se usa (flujo completo)

1. **Conseguir el catálogo** de la instalación de destino: pantalla
   **Señales → Catálogo** (botón, solo admin). Descarga un `.json` con los
   indicadores disponibles, sus tipos y categorías, los sectores/mercados/
   países cargados y las señales que ya existen. Sin esto no se puede saber
   qué `indicator_key` son válidos: **cambian de una instalación a otra**.
2. **Escribir el pack** siguiendo este documento.
3. **Validarlo offline**, sin base y sin la app:
   `python scripts/validate_pack.py mi_pack.json --catalog catalogo.json`
   Devuelve los mismos errores que devolvería el import, más avisos de las
   trampas silenciosas (§8). Iterar hasta que salga limpio.
4. **Importarlo**: el mismo archivo se sube **primero** en
   *Señales → Importar* y **después** en *Estrategias → Importar*. Cada
   pantalla lee la parte que le toca (las estrategias referencian las señales
   por `key`, así que el orden importa). Requiere rol admin.
5. **Calcular la historia**: Centro de Datos → *Señales y Estrategias →
   Ejecutar*, con alcance en la estrategia nueva. Hasta que eso corra, la
   estrategia existe pero no tiene resultados.

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

Nota: el archivo debe traer al menos una de las dos listas, pero **un pack
bien armado trae las dos y es autosuficiente**: incluye *todas* las señales
que su estrategia usa, aunque ya existan en la instalación de destino. Una
señal repetida entre packs no genera conflicto — el import actualiza por
`key`, no duplica.

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
  `false`, un valor extremo produce puntajes de ±340 que distorsionan el
  promedio ponderado y hacen que el ranking lo domine un solo activo.
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

**Ranking**: promedio ponderado de los puntajes de los componentes.

- `weight` es un número (default 1). Solo importa la proporción entre pesos:
  `3/2/1` y `6/4/2` dan el mismo ranking.
- **Las señales sin valor se saltean**: el promedio se calcula solo sobre los
  componentes que puntuaron ese día, no cuentan como cero. Si ninguno puntúa,
  el activo no aparece en el ranking.
- El ranking es **transversal**: la posición de un activo depende de todos los
  demás en esa fecha.

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
| `attribute` | `key`: `sector`, `market`, `industry`, `country`, `instrument_type` | Grupo al que pertenece el activo |
| `const` | `value`: número, texto o lista | Valor fijo de comparación |

**Operadores**

| Operadores | Uso |
|---|---|
| `>` `>=` `<` `<=` | Solo con **ambos lados numéricos** |
| `=` `!=` | Numéricos o de texto (mismo tipo de los dos lados) |
| `in` `not_in` | El lado derecho **debe** ser un `const` con **lista** |

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

**Atributos: por nombre, no por id.** Escribí `"Technology"`, `"NASDAQ"`,
`"Equity"` — el import los resuelve al id de la instalación de destino. Los
ids internos **no son portables**: son distintos en cada base. (Un número o un
texto de solo dígitos se interpreta como id ya resuelto, para poder reimportar
sin cambios lo que exportó la app.) Los nombres válidos están en el catálogo,
en `attributes`; la comparación no distingue mayúsculas, pero el nombre tiene
que existir tal cual o el import falla con la lista de valores parecidos.

---

## 7. Lo que depende de la instalación (el catálogo)

Este documento es igual en todas las instalaciones. **Lo que cambia** —y por
eso viaja aparte, en el JSON del botón *Catálogo*— es:

| Sección | Para qué la necesitás |
|---|---|
| `indicators[]` | Los `indicator_key` válidos. Cada uno trae `type` (`num`/`str`), `values` si es categórico, `keep_history` y una descripción. |
| `attributes` | Los nombres de sector, mercado, industria, país y tipo de instrumento **cargados en esa base**. |
| `signals[]` / `strategies[]` | Lo que ya existe: sirve para no pisar una `key` ajena y para saber qué señales podés reusar. |

Un indicador con `keep_history: false` solo tiene valor vigente: una señal
sobre él no tendrá historia y **no sirve para backtest**.

---

## 8. Qué acepta y qué rechaza el import

**Todo o nada.** Si una sola fila es inválida, **no se escribe nada** y la
pantalla muestra el motivo de cada una. No hay import parcial.

**Upsert.** Las señales se identifican por `key` y las estrategias por
`name`, sin distinguir mayúsculas: reimportar actualiza la definición
existente (y reemplaza sus componentes) en vez de duplicarla. El dueño de una
definición existente **no cambia**; quien importa queda como dueño de las
nuevas.

Se **rechaza** (errores):

- `formula_type` desconocido, o `params` con la forma equivocada para esa
  fórmula.
- `indicator_key` ausente o inexistente en la instalación.
- Señal referenciada por una estrategia que no está ni en el pack ni en la
  base.
- Estrategia sin componentes.
- Filtro con JSON inválido, operador desconocido, tipos incompatibles, o
  valores fuera del catálogo de un indicador categórico.
- Nombre de sector/mercado/país/industria/tipo que no existe en la
  instalación.
- Estrategia pública que usa señales privadas.
- `source` en una señal o `scope` en un componente: eran las señales de grupo
  y el Alcance de grupo, **removidos** del sistema. Se rechazan en vez de
  ignorarse, porque descartarlos cambiaría el resultado en silencio.

Se **avisa** pero se importa igual (el validador offline los lista como
`AVISO`): mapa discreto incompleto, `thresholds` desordenados o sin tramo
final, `clamp: false`, señal sobre un indicador sin historia, estrategia sin
filtro, y señales que ninguna estrategia del pack usa (cada señal cargada
cuesta cómputo en cada corrida).

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
formato histórico; el JSON es el canónico para intercambio. Un pack JSON se
convierte con `python scripts/pack_from_json.py mi_pack.json`.

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
