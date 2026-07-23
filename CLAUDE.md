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
  → `git commit` + `git push` → la app corre en **Railway sobre PostgreSQL**.
  El **Codespace ya no se usa** (jul-2026): la verificación contra la app viva
  es directo en Railway, así que todo lo que toque la base real es *producción*
  — no hay entorno intermedio descartable. Tenerlo en cuenta al proponer
  scripts que escriban.
- **`git push` actualiza DOS remotes a la vez** (bazan-rodrigo, rodrigoqw33).
  Si falla en uno, revisar el PAT de esa cuenta (`git remote -v`).
- **Hook pre-push** (solo en la PC con la memoria de Claude): frena el push si
  `docs/notes/` quedó desfasado respecto de la memoria — es modo AVISO, no
  modifica nada; sincronizar es siempre una acción deliberada. Tras un re-clon,
  reinstalarlo: `cp scripts/git-hooks/pre-push .git/hooks/pre-push`. En
  Railway es un no-op (no hay memoria). Saltarlo: `--no-verify`.
- **Verificación:** esta PC no levanta la app (sin base/yfinance). La red de
  seguridad automatizada es pytest. Todo lo que toca la app viva (callbacks Dash,
  migraciones, corridas reales) se prueba **en Railway, que es producción** —
  dejarlo anotado como pendiente en `docs/notes/project_pendientes.md` en vez de
  darlo por verificado. Los scripts de medición que ESCRIBEN (`profile_*.py` con
  backfill real) corren contra esa misma base: tomar el `run_lock` como hace el
  Centro de Datos, y avisar que es una corrida real.
- **Soporte dual MySQL/PostgreSQL:** todo SQL con sabor a motor (upserts,
  quoting, TRUNCATE vs DELETE, retry de locks, information_schema) va por
  `app/services/db_compat.py` — nunca ramas por dialecto sueltas en los
  servicios, y PostgreSQL NUNCA cae al camino de sqlite/tests. La rama MySQL
  emite el SQL byte-idéntico al histórico (`tests/test_db_compat.py` lo fija).
  Migraciones desde la 0076: **portables** (la cadena 0001–0075 quedó
  congelada solo-MySQL; `tests/test_bootstrap_portability.py` renderiza las
  nuevas offline contra ambos dialectos). Bases nuevas nacen con
  `scripts/init_db.py` (create_all + stamp head, cualquier motor).
- **Modales ABM:** no se cierran ante error de guardado (solo el callback de save
  cierra, y solo en éxito) — así el usuario no pierde lo cargado.
- **Pantalla nueva = registrarla en `app/__init__.py`** (listas `_PAGES` y
  `_CALLBACKS`) — la app NO auto-descubre páginas (`pages_folder=""`); sin
  registro la ruta da 404. `tests/test_module_registration.py` lo verifica
  (falla la suite si un módulo queda sin registrar). Sumar también el link
  en `app/components/navbar.py`.
- **Pantalla nueva = documentarla en el manual.** Toda ruta registrada exige su
  sección en `docs/manual/` (un `.md` con `page: <ruta>` en el front-matter) y
  su ícono de ayuda: `page_header("Título", "<slug>")` o `help_link("<slug>")`,
  o `help_slug=` si usa `make_abm_layout`. `tests/test_manual_coverage.py` ata
  el manual al código y falla la suite si una pantalla queda sin documentar, si
  un `?` apunta a un slug inexistente, o si un `page:`/enlace apunta a una ruta
  que no existe. Convenciones del contenido: español rioplatense (vos/tenés),
  cero menciones a archivos/tablas/IDs de componentes (el lector no programa),
  y `roles:` jerárquico (`invitado` < `analista` < `admin`; ausente = visible
  para todos). El servicio y el diseño están en `app/services/manual_service.py`.
  Rutas utilitarias sin sección van a la lista `excluidas` del test.
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
- Base: **MariaDB/MySQL** (prod: Linux + Apache2 + mod_wsgi, un solo proceso
  WSGI) **o PostgreSQL** — soporte dual: el motor lo decide `DATABASE_URL`
  (`mysql+mysqldb://` / `postgresql+psycopg://`). Estudio y estado por fase
  en `docs/notes/design_postgresql_dual.md`.
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
En PostgreSQL ese retry solo funciona porque `db_lock_timeout` (30s, por la
opción `-c` de libpq en `app/database.py`) convierte la espera indefinida en un
`55P03`; sin tope, un escritor bloqueado no falla, no reintenta y cuelga la
corrida en silencio.
**El runner SUELTA su sesión antes de toda fase larga** (`Session.remove()`
después de las lecturas de setup, antes de la red/el pool): una transacción
`idle in transaction` fija el *xmin horizon* y **paraliza autovacuum en toda la
base** justo cuando la corrida borra millones de filas. Patrón en
`price_service._bulk_download_assets` y `fundamental_service._run_fund_batch`.
Después del `remove()` solo viajan datos planos —nada de objetos ORM— y meter
una query nueva entre el `remove()` y el pool reabre la transacción y anula el
arreglo (lo fijan `tests/test_price_bulk_download.py` y
`tests/test_fundamental_bulk_download.py`).
**DELETE masivo = SIEMPRE por ventanas que avanzan** (`db_utils.delete_by_ranges`):
una sentencia única sobre millones de filas retiene locks/undo por minutos
(medido 400s+ en `signal_value`), y el loop `DELETE ... LIMIT` sobre el rango
completo es PEOR — cada lote re-escanea desde el inicio los tombstones de los
lotes anteriores (O(n²), medido 17min+ sin terminar). El patrón LIMIT de
`purge_assets` solo es tolerable para conjuntos chicos por asset_id.
El GIL limita paralelizar cómputo con threads (medido); por eso el pool de
indicadores usa **ProcessPool con partición por activos** —ya implementado—
(`app/services/process_pool.py`, `run_asset_batches` en technical/
fundamental_service; diseño en `docs/notes/project_processpool_particion_activos.md`).

## Testing

- `tests/` con pytest (~740 tests de **lógica pura**, nunca tocan la base real).
- `tests/conftest.py` apunta `DATABASE_URL` a un stub **sqlite** antes de importar
  `app`. Los tests que necesitan tablas hacen `Base.metadata.create_all(engine)`.
- Al agregar lógica de cálculo, agregar tests (codifican reglas de negocio:
  29-feb, "último precio preliminar", shares TTM más reciente, etc.).
- Para orquestación que toca BD sin romper "no tocar la base": monkeypatch de las
  funciones pesadas y verificar solo el ORDEN (ver `test_indicator_pipeline_order.py`).

## Objetivo y pendientes

- **Escalar a ~10.000 activos** (hoy ~500 de prueba); priorizar perf de indicadores
  full_sample (ver `docs/notes/project_scaling_target.md`).
- **Backtest de estrategias — niveles A-D hechos** (`/backtest`, jul-2026):
  A) cuantiles con IC/spread (snapshots en `backtest_run`, migración 0070, gate
  de lectura por precio propio, `backtest_service.py`); B) reglas
  (`rules_backtest_service.py`); C) simulación de cartera con costos + curva de
  equity (`portfolio_backtest_service.py`, `portfolio_sim_engine.py`);
  D) comparación de runs + **walk-forward** (`walk_forward`). Módulo de
  **Carteras** (`/carteras`, reales y teóricas) también hecho.
- Diferido: módulo de creación de indicadores por el usuario (plantillas, no
  fórmula libre). El **soporte dual MySQL/PostgreSQL ya está** (Railway corre
  sobre PostgreSQL); el **ProcessPool ya está** — ambos salieron de "diferido".
- **`docs/notes/project_pendientes.md`** tiene el detalle sesión por sesión y los
  pasos de verificación pendientes en Railway.
