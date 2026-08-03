---
name: project_grillas_10k
description: "DevExtreme DESCARTADO; el problema eran las grillas camino a 10.000 activos — TODA la app migrada a ag-grid (20 grillas, cero DataTable), render verificado en Railway el 27-jul; la etapa 3 espera medición"
metadata: 
  node_type: memory
  type: project
  originSessionId: 8b4c25e3-14d8-4e35-98b2-896513d5e1b5
  modified: 2026-08-03T04:28:00.630Z
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
- **Etapas 1 y 2 — HECHAS (26-jul, commit c1cdd12, 1071 passed):** 6 pantallas
  a ag-grid. Ver "La migración" más abajo.
- Etapa 3 (Infinite Row Model): SIGUE PENDIENTE y sigue condicionada a medir.
  Con la virtualización puesta, el cuello que queda es el tamaño de lo que
  viaja por la red, no el dibujado — medir antes de encararlo.
- ~~FUERA de alcance: los ABMs de catálogo y `app/components/abm.py`~~ —
  **esta previsión salió mal y conviene recordar por qué**: se descartaron por
  "genérico, impacta 15 pantallas sin beneficio", pero al migrarlos (27-jul)
  resultó que ser genérico los hacía BARATOS —un solo archivo resolvió 8
  pantallas— y el beneficio era la consistencia visual, que sí importaba.

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

---

## La migración a ag-grid (26-jul-2026, commit c1cdd12)

`dash-ag-grid` 35.3.0 (ag-grid 35.3.1). Seis pantallas: `/senales`, `/assets`,
`/prices`, actualización fundamental, import de activos e import de eventos.
Config compartida en **`app/components/grids.py`**.

**Lo que costó averiguar (y no está en la doc de Dash):**
- **ag-grid 35 arranca con la Theming API nueva, que es CLARA y se configura
  desde JavaScript.** Sin hacer nada, la grilla se ve blanca sobre la app
  oscura. La salida es `dashGridOptions={"theme": "legacy"}`, que vuelve a los
  temas por hoja de estilos y ahí sí se configura por variables CSS desde
  Python/CSS. Verificado que el paquete npm 35.3.1 todavía publica los CSS
  legacy y que dash-ag-grid tiene una rama explícita para `theme` string.
- El CSS legacy va por `external_stylesheets` usando `dash_ag_grid.themes.BASE`
  y `.QUARTZ` — las arma el propio paquete con su `grid_version`, así que no
  desincronizan al actualizar.
- **`linkTarget` NO existe más** (react-markdown 9 lo sacó): el cellRenderer
  markdown abriría los enlaces en la misma pestaña. Por eso el ticker usa un
  renderer propio, que además evita parsear markdown sobre nombres que vienen
  de Yahoo.
- Los renderers propios se registran en `window.dashAgGridComponentFunctions`
  (`assets/dashAgGridComponentFunctions.js`) y NO necesitan
  `dangerously_allow_code`; los `{"function": "..."}` sueltos SÍ, y por eso no
  se usan. `styleConditions` (conditional formatting) tampoco lo necesita.
- API de selección: la vigente desde v33 es el objeto
  `{"mode": "multiRow", "checkboxes": True, "headerCheckbox": True,
  "enableClickSelection": False}`.

**Decisiones:**
- **El JS no decide nada.** Colores y umbrales (±20 score, ±0,5 delta) viajan
  desde `ui_constants` por `cellRendererParams`. El renderer solo pinta — así
  no se repite el problema de semántica duplicada del simulador de trades.
- `custom.css` y `dark_theme.js` NO se tocaron (zona intocable del sistema de
  diseño, ver [[project_sistema_diseno_ui]]): todo lo de ag-grid vive en
  `assets/ag_grid.css`.
- `floatingFilter: True` en el colDef default para no perder el casillero de
  filtro que la DataTable mostraba siempre (ag-grid lo esconde en el menú).
- **Se removió el dropdown "Ordenar por" del screener**: ahora ordena cualquier
  cabecera, incluidas las columnas de señal, que antes no se podían ordenar.
- `data`→`rowData` y `selected_rows` (índices) → `selectedRows` (las filas):
  saca de encima los índices contra el array original, que no coincidían con
  lo que el usuario veía ordenado/filtrado.
- `/assets` necesita `getRowId="params.data.id"`: sin eso la selección se
  pierde cada vez que un callback reescribe las filas.

**Red de tests (33 nuevos):** `test_screener_grid.py` (columnas/filas + ata los
nombres de renderer al archivo JS: un typo ahí deja celdas en blanco sin
romper ningún import) y `test_grids_migration.py` (frena una migración a
medias: props viejas de DataTable o indexado de filas por posición).

**PENDIENTE en Railway = producción — es UI, no hay forma de probarla acá.**
Por orden de riesgo: (1) que las grillas se vean OSCURAS (si salen blancas,
falló el `theme: "legacy"`); (2) que los checkboxes aparezcan en `/prices`,
fundamental y `/assets` (si no, la API de selección cambió — el modo de falla
es seguro: sin selección los botones quedan deshabilitados y no se puede
disparar nada destructivo); (3) que la barra de score y los enlaces del ticker
se dibujen; (4) editar/borrar/masiva en `/assets`.

---

## Migración COMPLETA: ya no queda ninguna DataTable (27-jul-2026, commit 0af810d)

El usuario vio la grilla nueva en Railway, **le gustó más que la anterior** y
pidió reemplazar TODAS. Quedaron **20 grillas en 19 pantallas** y se borró
`app/components/table_styles.py` (era el dark mode de la DataTable, sin
consumidores). Esto revierte el "FUERA de alcance: los ABMs de catálogo" que
decía el plan original: `components/abm.py` es genérico, así que migrarlo
resolvió 8 pantallas de una sola vez y salió barato.

`grids.to_column_defs()` traduce el formato viejo ({name, id}) al de ag-grid,
para las pantallas que declaran las columnas en un solo lugar (el ABM, el
explorador de datos, la consola SQL); lo que ya viene en formato nuevo pasa
intacto, así una pantalla puede migrar de a poco.

**Dos acoplamientos que la migración destrabó (no eran traducción):**
- **Sintéticos ataba la selección a un array paralelo de ids indexado por
  posición** (`syn-formula-ids`: la fila N de la tabla ↔ el id N del store).
  Ahora la fila lleva su `id` y el store se removió. Con el array paralelo,
  cualquier cambio de orden en la tabla borraba o recalculaba el sintético
  equivocado.
- El visor de precios formateaba decimales en el cliente; ahora redondea en el
  servidor dejando los valores NUMÉRICOS. Como texto, ordenar por precio
  ponía "9" después de "10".

`single_selection()` para /carteras (elegir cartera = ver detalle, el click SÍ
selecciona) vs `multi_selection()` (checkbox obligatorio) donde la selección
dispara borrados o redescargas.

**Verificación local que vale la pena repetir:** un script descartable que
instancia la app contra el stub sqlite, hace `create_all` y **construye el
layout de las 47 pantallas registradas**, reportando por grilla: cantidad de
columnas, modo de selección, que el tema sea `legacy` y que toda columna tenga
`field`. Es la única red local para props de UI — la suite no arma layouts.

Tests: el ratchet cubre las 22 grillas (props viejas de DataTable, indexado de
filas por posición) y falla si vuelve a aparecer una `DataTable`. 1155 passed.

**VERIFICADO en Railway (27-jul-2026):** el usuario confirmó que la app se ve
bien con las 20 grillas. O sea que quedan descartados los dos riesgos de
render que se habían anotado: el tema **sí** aplica (`theme: "legacy"` +
`assets/ag_grid.css` funcionan: las grillas salen oscuras, no blancas) y los
renderers propios dibujan (barra de score y enlaces del ticker).

**BORRAR Y EDITAR: VALIDADO (3-ago-2026)** — el usuario lo confirmó en Railway.
Era lo único que la verificación visual del 27-jul no cubría: el mapeo fila→id
de los caminos de selección (checkbox + botones destructivos, los ABMs de
catálogo, y el borrado/recálculo de /admin/synthetic, donde hubo cambio
estructural — se removió el array paralelo de ids indexado por posición).
**El hilo de las grillas queda cerrado**: render y caminos funcionales, los dos
ejercitados contra la app viva.
