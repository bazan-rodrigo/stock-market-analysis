---
name: feedback_indicador_se_ve_en_el_grafico
description: "Un indicador nuevo NO está terminado hasta que se puede ver en el Gráfico Técnico; JS vs servidor es una decisión de eficiencia, no una frontera de alcance. Ya se perdió dos veces por mirar solo _SLOTS"
metadata: 
  node_type: memory
  type: feedback
  originSessionId: 1b45f51d-7422-49be-9e79-dbf346e4ef24
  modified: 2026-08-01T04:22:42.133Z
---

**Si el usuario agrega un indicador, es para verlo en el gráfico.** El panel de
indicadores, el posicionamiento histórico y los dropdowns de señales no
alcanzan: la pestaña **Gráfico Técnico** de Análisis de Activo es parte del
alcance de "agregar un indicador", no un trabajo separado y opcional.

**Why:** ya se discutió más de una vez y se volvió a perder. El error de fondo
es mirar `chart_callbacks._SLOTS` y concluir que el gráfico "solo dibuja cosas
calculadas en el navegador". **Es falso**: `_SLOTS` es la lista de los que se
calculan en JS, no la lista de lo que el gráfico dibuja. El gráfico ya trae
**cinco overlays servidos desde Python** (`chart_callbacks.py` ~253-342):

- `chart-regime-data` → `get_regime_zones_for_chart` (recalcula desde precios)
- `chart-vol-data` → `get_vol_zones_for_chart` (idem)
- `chart-dd-data` → `get_dd_events_for_chart` (idem)
- `chart-strategy-data` → scores de estrategia
- `chart-rs52w-data` → **lee la columna `relative_strength_52w` de `ind_daily`**

O sea que el régimen de tendencia —un indicador del pipeline— SÍ se ve en el
gráfico. Que MACD/Bollinger/ATR se calculen en el browser es una decisión de
eficiencia tomada para esos casos; no define hasta dónde llega el trabajo.

**How to apply:** al agregar un indicador, sumar desde el vamos el panel del
gráfico al plan y al alcance, sin esperar a que lo pidan. Para un indicador ya
persistido el molde correcto es **`rs52w`** (`load_rs52w_overlay`,
`chart_callbacks.py:306`), que lee de `ind_daily` con `get_ind_table(code)` en
vez de recalcular ni duplicar la fórmula en JS — duplicarla trae el costo de
homologación que en este proyecto ya se paga con el simulador de trades. El
cableado por indicador es: entrada en `_SLOTS` (hereda el checkbox) + checkbox
en `asset_analysis.py` + `dcc.Store` (+ dummy) + callback lazy + argumento en
`_JS_RENDER` + `activeSeps.push(...)` + clientside callback que actualiza
`_lwcState`.

Relacionado: [[project_indicadores_0098]], [[project_indicadores_con_historia]]
(el hilo donde se documentó el "solo-JS" de `_SLOTS`, que es cierto para esos 8
paneles pero NO es el criterio de alcance), [[feedback_reflejar_en_ui_y_spec]].
