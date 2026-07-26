---
name: project_grillas_10k
description: "DevExtreme DESCARTADO; el problema real son las grillas camino a 10.000 activos — etapa 0 (topes) HECHA el 26-jul, etapas 1-3 (dash-ag-grid) pendientes"
metadata: 
  node_type: memory
  type: project
  originSessionId: 8b4c25e3-14d8-4e35-98b2-896513d5e1b5
  modified: 2026-07-26T21:16:49.346Z
---

Sesión 26-jul-2026. Arrancó como pregunta ("¿tendríamos algún beneficio usando
gráficos DevExtreme?") y terminó en la primera etapa de un plan de grillas.

**DevExtreme: DESCARTADO** (para gráficos el beneficio es ~nulo).
1. Dash no consume componentes JS arbitrarios: o se empaqueta un componente React
   propio, o se monta con `external_scripts` + div + clientside callbacks — que es
   el camino que ya se paga con Lightweight Charts y es la raíz de la regla de
   HOMOLOGACIÓN del simulador (semántica duplicada Python/JS).
2. No cubre mejor ningún caso: lo financiero ya lo hace Lightweight Charts (mejor)
   y lo estadístico Plotly (mejor). DevExtreme es fuerte en gráficos "de negocio".
3. Licencia comercial (la gratuita es solo uso no comercial; una app interna de
   empresa no califica). Verificar precio antes de reconsiderar.

**El problema real son las GRILLAS, no los gráficos.** Todas las
`dash_table.DataTable` usan `page_action` default (= `"native"`): el dataset
COMPLETO viaja al navegador y `page_size=30` es solo cosmético.

Ranking de riesgo a 10.000 activos (relevado, no medido):
1. **Screener `/senales` — el peor.** No era una DataTable: es un `html.Table`
   armado a mano, sin tope ni paginación ni virtualización, y cada celda de score
   es un árbol de divs con estilos inline. Los datos viajaban DOS veces (store +
   árbol renderizado).
2. `/assets` (10k × 15 columnas), `/prices` y actualización fundamental (1 fila
   por activo procesado), import masivo.
3. `/admin/synthetic` (la conversión de moneda crea 1 sintético por activo en
   moneda), `/price-viewer` (ya hoy sin tope).
4. Sin problema: explorador y SQL (ya topeados en 5.000), ABMs de catálogo y
   definiciones, carteras.

**Plan acordado — `dash-ag-grid`, NO DevExtreme.** Componente oficial de Dash,
Community es MIT y trae virtualización, orden, filtros, Infinite Row Model y
export CSV. OJO: agrupamiento de filas, pivot, export a Excel y el Server-Side Row
Model completo son **Enterprise (pago)** — la Community alcanza porque lo que hace
falta es virtualización y carga por demanda.
- **Etapa 0 — HECHA (26-jul):** topes, sin dependencia nueva. Ver abajo.
- Etapa 1: ag-grid en el screener (la peor, y no arrastra modal ABM).
- Etapa 2: `/assets` + resultados de corrida (tienen selección múltiple y modal).
- Etapa 3: Infinite Row Model, solo si la medición lo justifica.
- FUERA de alcance: los ABMs de catálogo y `app/components/abm.py` (genérico:
  tocarlo impacta 15 pantallas sin beneficio).

**Etapa 0, lo que se implementó** (952 tests passed):
- Screener: selector "Mostrar" (Top 100/500/1000/2000/Todos, default 500). El tope
  es un LIMIT real en SQL dentro de `get_strategy_results_with_breakdown`, que
  ahora devuelve `(rows, comp_meta, total)` — no es recorte en Python: achica
  también el `IN (asset_ids)` de las lecturas por señal y del día anterior. El
  contador avisa en ámbar ("500 de 10.000 activos"). El **Excel sigue completo** y
  ahora exporta la consulta congelada en un store (antes usaba los selectores
  vivos → la planilla podía no coincidir con la pantalla).
- Visor de precios: tope 1.000 en modo "último precio" (con `LIMIT n+1` para saber
  si hay más sin pagar un COUNT) y últimos 2.000 en modo historia, pero el conteo
  y el rango de fechas siguen siendo los COMPLETOS. `get_prices_df` NO se tocó
  (lo comparten gráficos e indicadores).

**Dos hallazgos del camino:**
- **Los layouts no tienen red automatizada.** `dbc.Col` NO acepta `title=`
  (`dbc.Button` sí) y eso rompía `/senales` al renderizar;
  `tests/test_module_registration.py` no lo agarra porque valida por regex sobre
  el fuente, no construye layouts. Se verificó instanciando la app contra el stub
  sqlite en un script descartable (patrón reusable: stub de `yfinance` +
  `DATABASE_URL` sqlite + `create_app()` + llamar `layout()`).
- `screener_signals_callbacks` importaba `_th`/`_td` desde el módulo de la PÁGINA,
  cuyo import dispara `register_page` y exige la app instanciada → el módulo era
  intesteable. Ahora los toma de `app/components/ui_constants.py`, su origen real.

**PENDIENTE en Railway = producción** (nada de esto se probó contra la app viva):
que "Top 500" y "Todos" den la misma cabeza de ranking, que el contador ámbar
aparezca, y que el Excel baje completo.

Relacionado: [[project_scaling_target]] (el objetivo de 10.000 activos y el método
de medición), [[project_manual_usuario]] (las dos secciones tocadas).
