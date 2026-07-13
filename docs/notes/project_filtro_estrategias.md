---
name: filtro-estrategias-y-roadmap-indicadores
description: "Filtro de elegibilidad + editor de señales + backfill de señales, todo pusheado y probado en vivo (12-jul-2026); roadmap diferido de indicadores por plantilla"
metadata: 
  node_type: memory
  type: project
  originSessionId: 44667c57-b1c8-440a-b3df-63205dec6695
---

**Estado al 12-jul-2026: todo pusheado y probado en vivo en el Codespace**
(migración 0061 aplicada; el pack Pullback importado y funcionando).

Features de la sesión 11/12-jul (ver git log para detalle):
- **Filtro de elegibilidad de estrategias**: árbol AND/OR en
  `Strategy.filter_conditions`, evaluador en `strategy_filter.py`,
  constructor visual, absorción de `asset_filter` (migración 0061).
- **Editor estructurado de params de señales** (sin JSON a mano) + vista
  previa gráfica en vivo de cada fórmula.
- **Card "Señales y Estrategias" en Centro de Datos**: Ejecutar (delta:
  huecos + última fecha) / Recalcular completo, horizonte en días.
  El scheduler nocturno usa la misma función delta.
- **Pack de importación** `strategy_packs/` (Pullback en tendencia) +
  validaciones de import de señales/estrategias endurecidas.

Decisiones de semántica (importantes para no romperlas después):
- Indicadores en filtro y señales se leen **as-of** (última fila <=
  target_date, tope 45 días — `query_values_asof` en indicator_store):
  los semanales/mensuales se guardan con fechas de fin de período y el
  match exacto dejaba todo en 0 (bug histórico de tendencia_w/m y
  volatilidad_w/m, arreglado). Las señales como operando usan fecha
  exacta (snapshot), igual que el scoring.
- Dato faltante = condición no cumplida. Indicadores sin keep_history en
  filtro → resolution=current explícito (badge "diagnóstico in-sample"
  con fecha pasada); en señales → solo puntúan en la fecha vigente.
- `SIGNAL` es palabra reservada en MariaDB: en SQL directo la tabla va
  con backticks.
- El validador plotly del Codespace no acepta hex de 8 dígitos
  (#RRGGBBAA) en shapes — usar rgba().
- `indicator_service` fue renombrado a `group_score_service` (solo
  agrega tendencia por grupo, no calcula indicadores).

**Visibilidad y dueño de señales/estrategias (12-jul-2026, PUSHEADO
commit `0b4a230`, sin verificar en vivo aún):** migración 0065 agrega
`owner_id` (edición: solo dueño o admin; NULL = solo admin) + `is_public`
(SOLO visibilidad, se publica/despublica sin perder propiedad) a `signal`
y `strategy` (`created_by` renombrada). Módulo nuevo
`app/services/visibility.py` (can_view/can_edit/can_reference/
parse_publica/current_viewer/visible_filter, 26 tests). Regla de refs:
pública solo referencia públicas; privada, públicas + propias; despublicar
falla si otros la referencian. ABMs abiertos a analistas (switch Pública,
columnas Dueño/Pública, botón "Calcular historia" con scope
signal:<key>/strategy:<id>, sincrónico); import/export y pipeline solo
admin; import respeta columna `publica` del xlsx (ausente = pública) y el
importador queda dueño de lo nuevo. Los 8 packs de strategy_packs/ llevan
`publica=si`. Todas las pantallas de consumo filtran públicas+propias.
El pipeline de cálculo NO filtra (calcula todo).
**PRÓXIMO PASO en el Codespace: `git pull` + `alembic upgrade head`
(0065 ownership + 0066 huérfanas→admin + 0067 signal_eval_log), y
probar en vivo: login como analista (crear señal privada, verla solo
él, "Calcular historia"), reimportar un pack, despublicar una señal
usada por otro (debe fallar).**

**Fixes de la tarde del 12-jul (todos pusheados):** GuestUser con acceso
público ES admin en toda la app (auth/manager.py) — current_viewer() lo
respetaba mal y el "admin" no podía editar (commit `3cbd473`); horizonte
vacío = toda la historia en backfill de señales, scheduler incluido
(`c8d351e`); fechas con 0 resultados se reprocesaban en cada backfill
con alcance → tabla signal_eval_log registra fechas evaluadas
(`de70290`, migración 0067; clean_data.py la trunca junto con
group_signal_value/group_scores que faltaban). Datos confirmados:
^GSPC desde 1927, blue chips (MMM/KO/PG/...) desde 1962 — historia
larga legítima para backtests.

**Overlay de estrategia en Análisis de Activo (12-jul-2026, PUSHEADO
commit `67b69e1`, sin verificar en vivo):** toggle "Estrategia" en la barra del gráfico
técnico (lightweight-charts) — dropdown de estrategia visible + 2 sliders
(entrada ≥ E / salida < X, con histéresis vía máquina de estados en JS).
Server manda solo los scores (`chart-strategy-data`); los sliders
recalculan en el browser sin round-trip. Markers `setMarkers` unificados
con los de drawdown (setMarkers REEMPLAZA — un solo call con todos).
Label con nº de entradas/cerradas/ret.medio. Verificar en vivo en el
Codespace (JS no testeable local).

**Modo rango del backfill de señales (12-jul-2026, PUSHEADO `3119b68`,
sin medir en vivo aún):** `signal_backfill_range.py` — barrido
cronológico por chunks de 250 fechas (ventana as-of de 45 días entre
chunks), contexto invariante por corrida, escrituras DELETE+INSERT en
bloque, un commit por chunk. Se activa desde `_signal_history_run` con
≥30 fechas (`_RANGE_MODE_MIN_DATES`); el camino por-fecha quedó intacto
para el scheduler. La matemática vive en evaluadores puros COMPARTIDOS
(`_evaluate_asset_signal_scores`/`_evaluate_group_signal_scores`/
`aggregate_group_scores`/`rank_strategy_assets`/`_prepare_signals`) —
cualquier cambio de fórmula debe hacerse ahí, nunca duplicar en el modo
rango. Paridad garantizada por tests/test_signal_range_parity.py (388
en verde). Divergencia deliberada: el DELETE por fecha limpia filas
zombie que el upsert por-fecha dejaría. Estimado 10-50x; **PRÓXIMO
PASO: medir una corrida real en el Codespace** (la corrida fundacional
de la noche del 12-jul corrió con el código viejo). Si algún día hace
falta más: paralelizar por chunks con procesos (cada chunk es
autosuficiente, sin caché compartido).

**Pendiente natural siguiente**: backtest automático de estrategias
(recorrer fechas, medir retorno posterior por decil del ranking) — el
usuario ya está evaluando el Pullback a mano con el historial poblado.

**Roadmap diferido (acordado, sin arrancar): módulo de creación de
indicadores por el usuario.** Niveles 1+2 (plantillas parametrizadas:
familia existente con parámetro N + combinador de dos series A⊕B con
/, -, % dist), NO lenguaje de fórmulas libre (riesgo perf para
[[objetivo-10000-activos]]). Mismo patrón estructural que los sintéticos.
Motivación: dist_sma20 existe porque el usuario lo programó; un usuario
final no puede crear su propio indicador.
