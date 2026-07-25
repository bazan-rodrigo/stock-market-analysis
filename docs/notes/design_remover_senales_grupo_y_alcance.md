---
name: design-remover-senales-grupo-y-alcance
description: "Plan archivo-por-archivo para remover las señales de grupo (source=group) y el Alcance de grupo en estrategias (own_group/specific_group), CONSERVANDO group_scores y el Mapa de Mercado. Decidido el 24-jul-2026."
metadata:
  node_type: design
  type: project
---

# Remover señales de grupo + Alcance en estrategias

**Estado:** IMPLEMENTADO (24-jul-2026). Paso 1 (UI gate, commit 19ac3c7) y paso 2
(remoción de raíz + migración 0090) hechos, suite 904 verde. Decisiones tomadas:
(1) dropear `source`/`group_type`; (2) el import RECHAZA grupo/scope; (3) rollout
en 2 pasos. Opción (a): el backfill conserva group_scores de la última fecha para
el Mapa de Mercado (no se tocó ningún archivo del mapa). **PENDIENTE: aplicar la
0090 (`alembic upgrade head`) en Railway** — ver [[remover-senales-grupo-y-alcance]].

## Por qué

Hoy la funcionalidad es barata **solo porque nadie la usa** (cero señales de
grupo definidas → `group_signal_value` vacía, `group_scores` escribe solo la
última fecha). En cuanto un usuario real cree la primera señal de grupo o
estrategia con Alcance:

- **Espacio:** se enciende la escritura de **historia completa** de
  `group_scores` (~200 grupos × miles de fechas) — el mismo bloat de "millones
  de filas muertas" que hubo que contener en f5b396f — y empieza a llenarse
  `group_signal_value`.
- **Fallos:** las ramas de grupo del backfill por rango (las más sutiles del
  repo) pasan de dormidas a ejecutarse con datos reales.
- **Testing:** cada caso habilitado es superficie nueva a cubrir.

Decisión del usuario: **no ofrecer la capacidad**, para que no crezca a un
centro de costo. Como bonus, se elimina toda la maquinaria de derivación
(`_derive_needed_groups` y cía.) que existe SOLO para contener ese bloat.

## Qué SOBREVIVE (no tocar)

`group_scores` **se calcula desde los indicadores de tendencia** (`ind_trend_*`
→ `_REGIME_SCORE` → promedio por grupo), **no** desde señales. Alimenta el
**Mapa de Mercado** (`technical_service.get_market_map_data`, última fecha) y el
Explorador de Datos. Por lo tanto se conservan intactos:

- `app/services/group_score_service.py` (compute_group_scores, aggregate_group_scores, _REGIME_SCORE, get_default_target_date)
- `app/services/technical_service.py` → `_refresh_group_scores`, `get_market_map_data`
- `app/pages/market_map.py`, `app/callbacks/market_map_callbacks.py`
- El dataset `group_scores` del Explorador de Datos.
- El **filtro de elegibilidad por atributo** (`country in [...]`, `sector = X`)
  en `strategy_filter` — es `type="attribute"`, independiente del Alcance.

> ⚠️ **COORDINACIÓN — 24-jul: otra sesión está tocando el cálculo del Mapa de
> Mercado.** Todos los archivos de la lista de arriba son de esa sesión. Mi
> remoción NO los edita. Hay **un solo punto de roce**: el backfill por rango
> escribe la última fecha de `group_scores` para el mapa (ver "Punto de roce").

## Alcance de la remoción (mi territorio)

### Modelos
- **`app/models/group_signal_value.py`** → se elimina el modelo. Tabla dropeada
  por migración.
- **`app/models/__init__.py`** → quitar el export de `GroupSignalValue`.
- **`app/models/signal_definition.py`** → quitar `source` y `group_type`
  (quedaban constantes: todas las señales serían `asset`). *Sub-decisión abajo.*
- **`app/models/strategy_component.py`** → quitar `scope`, `group_type`,
  `group_id`. El componente queda: `strategy_id`, `signal_id`, `weight`.

### Servicios
- **`app/services/signal_service.py`**
  - Eliminar: `compute_group_signal_values`, `_evaluate_group_signal_scores`,
    `_get_group_indicator_value`, `_VALID_GROUP_INDICATOR_KEYS`,
    `signals_and_strategies_affected_by_new_assets` (queda siempre vacía →
    desaparece el aviso de "recalcular por agregados de grupo" al alta de
    activos; **queda** el aviso por ranking transversal, que es otro mecanismo).
  - `_prepare_signals`: quitar la clasificación `group_signals` / `bad_group`.
  - `_evaluate_asset_signal_scores`: quitar el loop de `group_signals` y el memo
    de scores de grupo; el evaluador queda solo con señales de activo.
  - `save_signal` / `import_signals_excel`: quitar la validación de `source=group`
    y `group_type`. Import debe **rechazar** filas `source=group` con error claro
    (no importar silenciosamente como asset).
  - `run_daily`: dejar de llamar `compute_group_signal_values`; el dict de
    retorno pierde `group_signal_values`.
- **`app/services/strategy_service.py`**
  - `_compute_asset_score` y `get_strategy_results_with_breakdown`: quitar las
    ramas `own_group` / `specific_group` (queda solo el score por activo).
  - `export_strategies_excel` / `import_strategies_excel`: quitar columnas
    `scope`, `group_type`, `group_id`. Import las ignora (o rechaza si vienen con
    valor, para no perder configuración en silencio).
  - Dejar de cargar `GroupSignalValue` (imports y queries `gsv_map`).
- **`app/services/strategy_filter.py`**
  - Eliminar `restricted_attribute_ids` y `_leaf_attribute_ids` — **único uso**
    es la derivación de grupos (confirmado por grep). El resto del módulo
    (parseo, evaluación, atributos como operando del filtro) queda igual.
- **`app/services/signal_backfill_range.py`** — el mayor destripe:
  - Eliminar `_load_derivation_inputs`, `_derive_needed_groups`, `_group_needed`,
    `needed_groups`, `needed_group_types`, `types_with_signals`.
  - Eliminar la escritura/limpieza de `group_signal_value` (`gsv_rows`,
    `_load_stored_group_scores`, `stored_gsv_by_date`, ramas de `group_sig_ids`).
  - Eliminar `_evaluate_group_signal_scores` del cómputo por fecha.
  - **Punto de roce (ver abajo):** decidir el destino de la escritura de
    `group_scores`.
- **`app/services/data_explorer_service.py`** → quitar el dataset `signal_group`
  y su función `group_signal_value(...)`. **Conservar** `group_scores`.
- **`app/services/cleanup_service.py`** → quitar `"group_signal_value"` de
  `_LEAF_TABLES` y ajustar `TABLES_INFO` (la línea "group_scores /
  group_signal_value" → solo group_scores). **Conservar** `group_scores`.
- **`app/services/maintenance_service.py`** → quitar `"group_signal_value"` de
  la tupla de familia "Señales" (`classify_table`). `group_scores` queda en su
  familia "Scores de grupo".

### UI
- **`app/pages/admin_signals.py`** → quitar `{"label":"Grupo (group)"}` de
  `_SOURCE_OPTS` (queda solo asset; evaluar si el dropdown de fuente sigue
  teniendo sentido o se fija en asset); quitar la columna group-type y su
  styling condicional por `source`.
- **`app/callbacks/admin_signals_callbacks.py`** → quitar `toggle_group_col`,
  `indicator_opts_by_source` (rama group), los outputs/states de
  `sig-f-source` / `sig-f-group-type`; ajustar `save` (sin source/group_type);
  el mensaje de "Recalcular" ya no muestra `group_signal_values` (línea 352).
- **`app/callbacks/admin_strategies_callbacks.py`** → quitar el selector de
  Alcance (`str-comp-scope`), el dropdown de group-type, `_SCOPE_TEXT`, la
  fórmula en vivo con `[grupo propio/fijo: ...]`, y los campos scope/group_type
  del store de componentes.

### Migración
- **`alembic/versions/0090_*.py`** (siguiente número; última es 0089).
  **Portable dual MySQL/PG** (convención desde la 0076;
  `test_bootstrap_portability.py` la renderiza offline contra ambos dialectos).
  - `DROP TABLE group_signal_value` (tiene FK a signal ON DELETE CASCADE — el
    drop de la tabla la limpia sola).
  - `strategy_component`: drop de columnas `scope`, `group_type`, `group_id`.
  - `signal`: drop de `group_type` (y `source` si se decide dropearla).
  - `downgrade`: recrear tabla y columnas (nullable), sin datos.
  - **No** tocar `group_scores`.

### Tests (podar / eliminar)
- **Eliminar:** `tests/test_group_scope_derivation.py` (cae con
  `restricted_attribute_ids` / `_derive_needed_groups`).
- **Podar** las porciones de grupo en: `test_affected_by_new_assets.py`,
  `test_composites_y_estrategias.py`, `test_signal_range_parity.py`
  (casos de group_scores/group_signal_value), `test_data_explorer_service.py`
  (dataset signal_group), `test_maintenance_size_report.py` (familia),
  `test_db_utils_y_escritor.py` (si toca group).
- Revisar `test_strategy_filter_ui.py` y los de import/export de señales y
  estrategias (columnas scope/source).

### Manual
- `docs/manual/720-configuracion-senales.md` (fuente grupo),
  `730-configuracion-estrategias.md` (Alcance),
  `200-conceptos-pipeline.md` y menciones sueltas. `test_manual_coverage.py`
  ata el manual al código — la suite falla si queda algo colgado.

## Punto de roce con el Mapa de Mercado (decidir + coordinar)

Hoy el backfill por rango escribe la **última fecha** de `group_scores` completa
para que el mapa no quede desactualizado tras un rebuild
(`write_all_groups = d == latest_price_date`). Dos caminos:

- **(a) Conservador — recomendado como default:** el backfill por rango SIGUE
  escribiendo solo la última fecha de `group_scores` (agregada desde los
  barridos `ind_trend_*`, que no dependen de señales). Se elimina todo lo demás
  de grupo, pero se mantiene ese write y su DELETE de la última fecha. Blast
  radius mínimo, el seam del mapa queda idéntico.
- **(b) Más limpio pero invade territorio del mapa:** sacar `group_scores` del
  backfill por rango y confiar en `_refresh_group_scores` / camino diario para
  la última fecha. Cambia el comportamiento que sirve al mapa → **coordinar con
  la otra sesión antes de tocarlo.**

**Propuesta:** ir con (a) ahora; dejar (b) como follow-up a coordinar cuando la
otra sesión cierre su cambio del mapa.

## Sub-decisiones para confirmar

1. **¿Dropear `signal.source` o dejarla fija en `'asset'`?** Dropearla es más
   limpio; dejarla evita romper import/export viejos que traen la columna.
   Recomiendo **dropear** `group_type` seguro; `source` dropear también y que el
   import rechace `source=group` con mensaje claro.
2. **Import con datos de grupo:** ¿rechazar (error visible) o ignorar silencioso?
   Recomiendo **rechazar** — perder configuración en silencio es peor.
3. **Rollout:** ¿1 paso (todo junto) o 2 pasos (primero gate de UI sin
   migración → merge; después backend + migración 0090)? El de 2 pasos corta el
   uso ya con riesgo casi nulo y deja la parte de producción (DDL) para un
   commit propio con la suite verde.

## Verificación

- `venv\Scripts\python.exe -m pytest` verde antes de cada push.
- La migración 0090 se prueba con `test_bootstrap_portability.py` (offline,
  ambos dialectos). El `alembic upgrade head` real corre **en Railway = prod**
  → anotar en `project_pendientes.md` como paso de verificación, no darlo por
  hecho.
- Confirmar en Railway que el Mapa de Mercado sigue mostrando datos tras el
  cambio (lee `group_scores`, que no se toca).

## Cuidados de repo (memoria)

- **Sesiones en paralelo:** NO `git add -A`. Stagear archivo por archivo.
- Hook pre-push avisa si `docs/notes/` quedó desfasado de la memoria de Claude.
