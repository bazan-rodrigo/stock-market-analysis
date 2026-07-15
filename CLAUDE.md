# Stock Market Analysis — Guía para trabajar en el proyecto

App web interna de análisis técnico y fundamental de activos financieros, con
usuarios admin (acceso total) y analista (visualización). Este archivo lo lee
Claude Code automáticamente: resume las convenciones y la arquitectura para
poder retomar el proyecto sin la memoria de sesiones previas.

> Contexto detallado (decisiones, pendientes sesión por sesión, historia de
> features) en **`docs/notes/`** — copiado de la memoria de Claude Code.
> Empezá por `docs/notes/MEMORY.md` (índice).

## Cómo trabajar (convenciones acordadas — respetar siempre)

- **Responder en español.**
- **Pedir confirmación antes de aplicar cambios de código/CSS/config.** Presentar
  la solución y esperar el "sí" explícito antes de editar. Una PREGUNTA
  ("¿se puede…?", "¿cómo se…?") pide explicación, no implementación — responder
  primero. El ritmo de aprobaciones previas no convierte una pregunta en orden.
- **Correr la suite antes de cada push** que toque servicios, sin que lo pidan:
  `venv\Scripts\python.exe -m pytest` (Windows) / `./venv/Scripts/python.exe -m
  pytest` (bash). El venv local ya tiene las deps (todas menos `mysqlclient` y
  `yfinance`, que no están en esta PC de desarrollo).
- **Flujo de trabajo:** se edita en la PC local (Windows, **sin base de datos**)
  → `git commit` + `git push` → `git pull` en el GitHub Codespace, donde corre la
  app con **MariaDB** (`sudo service mariadb start`, no `mysql`). Recordarle al
  usuario el `git pull` tras cada push.
- **`git push` actualiza TRES remotes a la vez** (bazan-rodrigo, rodrigoqw33,
  rodrigoba77). Si falla en uno, revisar el PAT de esa cuenta (`git remote -v`).
- **Verificación:** esta PC no levanta la app (sin MariaDB/yfinance). La red de
  seguridad automatizada es pytest. Todo lo que toca la app viva (callbacks Dash,
  migraciones, corridas reales) se prueba en el Codespace — dejarlo anotado.
- **Modales ABM:** no se cierran ante error de guardado (solo el callback de save
  cierra, y solo en éxito) — así el usuario no pierde lo cargado.
- **Pantalla nueva = registrarla en `app/__init__.py`** (listas `_PAGES` y
  `_CALLBACKS`) — la app NO auto-descubre páginas (`pages_folder=""`); sin
  registro la ruta da 404. `tests/test_module_registration.py` lo verifica
  (falla la suite si un módulo queda sin registrar). Sumar también el link
  en `app/components/navbar.py`.
- **Estrategias:** cuando el usuario pide una estrategia, entregarla como archivos
  de import en `strategy_packs/` (`<pack>_senales.xlsx` + `<pack>_estrategia.xlsx`),
  no como pasos manuales. Validar offline con `signal_engine.validate_params` y
  `strategy_filter.validate_tree`; documentar en `strategy_packs/README.md`.
- **HOMOLOGACIÓN del simulador de trades (regla principal del módulo):** la
  semántica de entrada/salida vive DUPLICADA a propósito —
  `app/services/trade_simulator.py` (contrato, testeado) y su espejo JS
  `window._lwc.simulateTrades` en `app/callbacks/chart_callbacks.py`
  (interactividad del gráfico sin round-trip). Cualquier cambio de semántica
  se hace en AMBOS archivos en el mismo commit, junto con los casos de
  `tests/fixtures/trade_simulator_cases.json` (el contrato ejecutable). La
  fase 2 del backtest (simulación de cartera) consume el motor Python.

## Stack

- Python + **Dash** (UI) + **Flask-Login** (auth con roles) + SQLAlchemy + **Alembic**.
- Base: **MariaDB/MySQL** (prod: Linux + Apache2 + mod_wsgi, un solo proceso WSGI).
- **APScheduler** en el proceso principal (sin cron externo) para tareas diarias.
- Fuente de precios: **Yahoo Finance** (yfinance) — arquitectura extensible.
- Config: `conf.properties` (INI) con prioridad a variables de entorno.
- Admin inicial hardcodeado admin/admin123 (se cambia tras el primer login).

## Arquitectura clave

**Pipeline de indicadores → señales → estrategias** (todo pre-calculado, no
on-the-fly, para escalar a miles de activos):

1. **Indicadores** por activo: tablas dinámicas `ind_{codigo}` (serie histórica) +
   `current_indicator_values` (valor vigente). Se calculan por activo, independientes
   entre sí. Delta "tail-mode": solo reescribe la cola cuando es seguro (checksum/
   stats cacheados en `ind_asset_meta`); un activo nuevo (sin filas) cae al camino
   completo y se llena entero en el próximo **delta**.
2. **group_scores**: agregados de tendencia por grupo (sector/market/industry/
   country/instrument_type). Insumo de las señales de grupo. En el modo rango solo
   se escriben los grupos que alguna estrategia consume (ver `docs/notes/project_group_scores_scope.md`).
3. **Señales** (`SignalDefinition`): fórmulas `discrete_map`/`threshold`/`range`
   sobre indicadores (source=asset) o sobre group_scores (source=group). La fórmula
   `composite` se **removió** (combinar señales se hace en la estrategia).
   Resultados en `signal_value` / `group_signal_value`.
4. **Estrategias**: filtro de elegibilidad (árbol AND/OR, `strategy_filter`) +
   score ponderado de componentes (señales, con scope de activo o de grupo) →
   ranking en `strategy_result`. El ranking es **transversal** (cross-sectional):
   depende de todos los activos en la fecha.

**Deltas vs rebuild:**
- `update_*_history` = delta (llena huecos + recalcula siempre la última fecha,
  porque el último precio es preliminar).
- `rebuild_*_history` = borra y recalcula todo (para cambios de definición).
- Indicadores/precios: el delta es **por-activo** → un activo nuevo se llena solo.
- Señales/estrategias: el delta es **por-fecha global** → incorporar un activo
  nuevo a la historia requiere **"Recalcular completo"** (el ranking y los
  agregados de grupo son transversales). Ver `docs/notes/project_group_scores_scope.md`.

**Sintéticos y conversión de moneda:** `synthetic_service` calcula precios de
activos calculados (ratio/index). La conversión de divisas
(`currency_conversion_service`) crea un sintético `BASE_DIVISOR = base / divisor`
por cada activo en una moneda; heredan los grupos de su base.

**Concurrencia/BD:** escrituras concurrentes contra las mismas tablas pueden dar
lock timeout (1205) / deadlock (1213) de InnoDB — reintentar la transacción
(patrón en `fundamental_service._fund_worker` y `signal_backfill_range._flush`).
**DELETE masivo = SIEMPRE por ventanas que avanzan** (`db_utils.delete_by_ranges`):
una sentencia única sobre millones de filas retiene locks/undo por minutos
(medido 400s+ en `signal_value`), y el loop `DELETE ... LIMIT` sobre el rango
completo es PEOR — cada lote re-escanea desde el inicio los tombstones de los
lotes anteriores (O(n²), medido 17min+ sin terminar). El patrón LIMIT de
`purge_assets` solo es tolerable para conjuntos chicos por asset_id.
El GIL limita paralelizar cómputo con threads (medido); el escalado grande
pendiente es ProcessPool (ver `docs/notes/project_processpool_particion_activos.md`).

## Testing

- `tests/` con pytest (~400 tests de **lógica pura**, nunca tocan la base real).
- `tests/conftest.py` apunta `DATABASE_URL` a un stub **sqlite** antes de importar
  `app`. Los tests que necesitan tablas hacen `Base.metadata.create_all(engine)`.
- Al agregar lógica de cálculo, agregar tests (codifican reglas de negocio:
  29-feb, "último precio preliminar", shares TTM más reciente, etc.).
- Para orquestación que toca BD sin romper "no tocar la base": monkeypatch de las
  funciones pesadas y verificar solo el ORDEN (ver `test_indicator_pipeline_order.py`).

## Objetivo y pendientes

- **Escalar a ~10.000 activos** (hoy ~500 de prueba); priorizar perf de indicadores
  full_sample (ver `docs/notes/project_scaling_target.md`).
- **Backtest de estrategias — MVP hecho** (`/backtest`, jul-2026): análisis por
  cuantiles con IC/spread, runs persistidos como snapshots (`backtest_run`,
  migración 0070), gate de lectura (solo fechas con precio propio, ver
  `backtest_service.py`). Fase 2 pendiente: simulación de cartera con
  `trade_simulator` + costos + curva de equity; fase 3: comparación de runs
  lado a lado + walk-forward.
- Diferido: migración a **PostgreSQL** (`docs/notes/project_postgresql_migracion.md`),
  **ProcessPool** para el pool de indicadores, módulo de creación de indicadores
  por el usuario (plantillas, no fórmula libre).
- **`docs/notes/project_pendientes.md`** tiene el detalle sesión por sesión y los
  pasos de verificación pendientes en el Codespace.
