---
name: project-sistema-diseno-ui
description: "Sistema de diseño único + trinquete de consistencia de UI (26-jul-2026), y por qué NO se migra de Dash"
metadata: 
  node_type: memory
  type: project
  originSessionId: e3f1600b-4c11-4bc1-8487-1f2922f3beea
  modified: 2026-07-26T22:24:37.160Z
---

**26-jul-2026 (commit e37da72).** El usuario preguntó por alternativas a Dash; al
indagar, el dolor real era **heterogeneidad de estilos entre pantallas**, no el
framework. Cambiar de framework no lo arreglaba.

**Acoplamiento a Dash, medido** (por si vuelve el tema): de 45.819 líneas en
`app/`, ~22.000 (48%) son portables casi sin tocar — `services/` tiene **1 solo**
archivo que importa dash (`pair_analysis_service`), `models/` y `sources/`
tienen **0**, y de 76 archivos de test **1** importa dash. Los ~23.000 de UI
(callbacks + pages + components) se reescribirían enteros: 314 callbacks, 115
usos de `ALL`/`MATCH`, 368 `no_update`/`PreventUpdate`. Migrar = meses.
Alternativa más barata si algún día hace falta: **Flask + Jinja + HTMX**, y
**puede ser incremental** — `app/__init__.py` ya define rutas Flask nativas
(`/login`, `/do-login`, `/health`) sobre el mismo `server`, así que se pueden
montar pantallas Jinja al lado de las Dash sin big-bang.

**Lo que se hizo en su lugar:** `ui_constants.py` pasó de "constantes del módulo
de señales" (lo usaban 16 de 93 archivos de UI) a sistema de diseño de toda la
app. Colores sueltos 544 → 178. `page_header()` perdió el parámetro `level`
—que estaba documentado como "para respetar el tamaño que ya usaba cada
pantalla", o sea que **codificaba la inconsistencia como feature**— y las 30
pantallas lo adoptaron. `COLOR_POSITIVE`/`COLOR_NEGATIVE` pasaron de Material
(#4caf50/#ef5350) a Tailwind-400 (#4ade80/#f87171), que es la familia del resto
de la paleta.

**Why:** sin el trinquete (`tests/test_ui_consistency.py`, 4 reglas) la deriva
vuelve en meses — la causa es "evolución por partes", no un descuido puntual.

**How to apply:**
- **`assets/custom.css` y `assets/dark_theme.js` son ZONA INTOCABLE** en
  cualquier trabajo de estilos. Ahí viven los arreglos de legibilidad que el
  usuario fue pidiendo (dropdowns, date pickers, sliders, progress bars) y están
  **ganados a fuerza de especificidad contra el CSS interno de Dash** — el
  datepicker costó 5 intentos (9f33b53 → a4cb43a → c15d06c → 6d5ac80 → 5a63cac),
  el dropdown otros 5. Tocarlos es volver a pelear esa pelea. La regla del
  trabajo fue: **se toca Python (colores, `style=`, encabezados), no el CSS.**
- **Antes de "unificar" un color, averiguá de dónde salió.** Método que funcionó:
  `git blame` de cada aparición cruzado contra los commits `fix:` de legibilidad
  → clasificar en *intocable* (nació de un pedido, es requisito) vs *deriva*
  (copy-paste). Solo el 7% resultó intocable, pero incluía justo lo que el
  usuario temía perder. Los intocables se **promueven a constante con nombre
  conservando su valor** (`BG_INPUT`=#2c2c2c, `BG_CHART_ALT`=#1e2126,
  `BG_CODE`=#1e1e1e), nunca se reemplazan.
- **No todo color repetido es deriva:** la escala de tendencia
  (#2e7d32/#66bb6a/#a5d6a7) y las paletas de series codifican un DATO — el tono
  es información. El JS de velas usa convención de mercado. Todo eso queda fuera.
- **Sustitución masiva de constantes: verificá importando.** Compilar no alcanza
  — un import top-level faltante da `NameError` recién al abrir la pantalla.
  Pasó de verdad en `signal_params_ui`. La regla 3 del trinquete importa los 98
  módulos de UI por eso.

**PENDIENTE:** `screener_signals.py`, `screener_signals_callbacks.py` y
`price_viewer_callbacks.py` quedaron sin consolidar (otra sesión los tenía
modificados en paralelo). Están listados en `PENDIENTES_DE_CONSOLIDAR` dentro de
`tests/test_ui_consistency.py` — pasarles los tres paquetes y borrarlos de ahí.

**PENDIENTE de verificar en Railway:** el cambio de tono de verde/rojo y el
título unificado en h4 son cambios visuales reales que esta PC no puede ver
(ver [[feedback-entorno-verificacion]]).

Relacionado: [[feedback-confirmacion-cambios]], [[project-manual-usuario]],
[[project-pendientes]].
