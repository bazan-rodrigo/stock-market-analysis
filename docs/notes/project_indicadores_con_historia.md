---
name: project_indicadores_con_historia
description: "27-jul: por qué Drawdown %/ATR no estaban en Posicionamiento Histórico (3 grupos distintos de ausencia) + atr_pct_* y drawdown_pct_daily nuevos con historia (migración 0097), VERIFICADO en Railway; el hueco silencioso de los chequeos de cordura y su trinquete"
metadata: 
  node_type: memory
  type: project
  originSessionId: 5a6b294e-bd78-485a-ac97-8a11073167d2
  modified: 2026-07-27T20:23:26.311Z
---

Sesión 27-jul-2026 (commit 14b124c, 1181 passed). Arrancó como pregunta —"¿por
qué no hay drawdown en la pantalla de posicionamiento histórico?"— y el
diagnóstico resultó más interesante que el arreglo.

## El hallazgo: hay TRES motivos distintos de ausencia, no uno

El tab de Posicionamiento Histórico (`distribution_callbacks.py`) filtra por
`type == "num"` **y** `keep_history == True`. Un indicador puede faltar por
razones que no se parecen en nada entre sí:

1. **Series que solo existen en JS, no en el pipeline.** Los 8 toggles del
   gráfico (`chart_callbacks._SLOTS`) se calculan en el navegador sobre la serie
   ya cargada. **Drawdown %, MACD, Estocástico, Bollinger y ATR absoluto no son
   `IndicatorDefinition` en absoluto** — existen únicamente en
   `window._lwc.*`. RSI es la única excepción (sí está en el pipeline).
   *La primera respuesta que di fue incompleta acá: atribuí la ausencia de
   Drawdown % al `keep_history=False` de la familia `drawdown_*`, cuando el
   "Drawdown %" que el usuario veía era el panel JS, que es otra cosa.*
2. **Indicadores del pipeline con `keep_history=False`** (12): los 4
   `drawdown_*`, `resistance_pct`/`support_pct` y los 6 `best_*`. Existen como
   definición pero no tienen tabla `ind_*`, solo `current_indicator_values`.
   Los `best_*` no molestan; **`resistance_pct`/`support_pct` sí** (son
   distancias %, el posicionamiento histórico es exactamente su pregunta).
3. **Los que SÍ tienen historia pero el filtro `type=="num"` descarta**:
   `trend_*` y `volatility_*` (6). Las tablas están llenas —alimentan el Mapa
   de Tendencia—, no falta ningún dato: falta el modo de graficarlo. Para un
   categórico la distribución es más simple que para un numérico (una barra por
   régimen, sin binning; el "percentil" pasa a ser "% del historial en ese
   régimen"). **Es el pendiente con mejor relación valor/costo que quedó.**

## Lo implementado (migración 0097)

`drawdown_pct_daily` (solo diaria) y `atr_pct_{daily,weekly,monthly}`, con
historia, en las tablas anchas por cadencia. Aparecen solos en la pestaña.

- **ATR se persiste NORMALIZADO (`ATR/close*100`), no absoluto.** Decisión
  explícita: el ATR en unidades de precio no es comparable entre activos ni a
  lo largo de la historia de uno que cambió de escala — inútil justo en un
  histograma. El test que lo fija es la invariancia a la escala.
- Drawdown solo diaria: es acumulativo desde el máximo histórico, resamplear a
  W/M submuestrea la misma curva. La fórmula ya existía en Python
  (`_cur_drawdown_max1`), idéntica al espejo JS — no hubo que inventarla.
- **Los dos entran en `_CHECKSUM_DEP_CODES`.** `drawdown_pct_daily` porque el
  máximo acumulado tiene **memoria ilimitada hacia atrás**: corregir un precio
  viejo corre todos los valores posteriores sin dejar hueco de calendario que
  el modo `"series"` pueda detectar (RSI/dist_sma no están ahí porque su
  ventana es acotada). `atr_pct_*` porque Wilder es recursivo sobre toda la
  historia y su período sale de `vol_cfg`, editable por el admin — *esto lo
  corregí sobre la marcha: en el plan había dicho que no lo necesitaba*.

**Trampa de nombres que se desactivó:** `_atr_pct_series_v` en el código NO era
ATR% sino el **percentil** de ATR. Renombrado a `_atr_percentile_series_v`,
junto con `_bf_atr_*` → `_bf_atr_percentile_*` e `ind_atr_pct_*` →
`ind_atr_percentile_*`. Sin eso, `atr_pct_*` quedaba al lado de un homónimo que
significa otra cosa.

## El hueco silencioso de Verificación de datos

Lo destapó una pregunta del usuario ("¿se agregaron casos en Verificación de
datos?"), y la respuesta era mitad y mitad:

- La comparación **guardado-vs-recalculado** toma los códigos nuevos
  AUTOMÁTICAMENTE (`codes = list(_DELTA_TAIL_MODE)` filtrado por
  `_BACKFILL_FNS`) — basta con cablearlos bien.
- Los **chequeos de cordura** son un dict explícito (`_NUMERIC_BOUNDS`) y
  `check_sanity` devuelve `None` **en silencio** para un código sin límites: no
  falla, no avisa, simplemente no chequea. Un indicador nuevo queda sin
  auditar por omisión.

Se agregaron los 4 límites (`drawdown_pct_daily: (-100, 0)` es una **identidad
matemática**, no una heurística como el resto de esa tabla: el precio no puede
superar su propio máximo acumulado) **y un trinquete** que ata `_NUMERIC_BOUNDS`
al catálogo de indicadores con historia — 40 indicadores, ninguno sin chequear;
verifiqué que no pasa en vacío. Patrón igual al de
`test_wide_cubre_exactamente_los_tecnicos_keep_history`.

## VERIFICADO en Railway (27-jul-2026)

El usuario aplicó `alembic upgrade head` (0097), corrió el recálculo y confirmó
"probado y ok".

## Pendientes que quedaron de este hilo

1. **Distribución de categóricos** (`trend_*`/`volatility_*`): datos ya
   guardados, solo falta la rama de renderizado. El más barato y el más útil.
2. `resistance_pct`/`support_pct` con historia: el más caro (footprint), pero
   es donde la ausencia realmente duele.
3. MACD/Estocástico/Bollinger: descartados a propósito — al vuelo son posibles
   pero cada uno arrastra sus parámetros y la pestaña dejaría de ser "elegí un
   indicador" para volverse un configurador.

Relacionado: [[project_ind_wide_tables]] (las tablas anchas donde viven las
columnas nuevas), [[project_reduccion_footprint]] (el costo en disco: ~20 MB
hoy, ~400 MB a 10.000 activos), [[project_scaling_target]], [[project_testing]].
