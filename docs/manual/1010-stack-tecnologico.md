---
slug: stack-tecnologico
title: Stack: que hace cada pieza y que restriccion impone
chapter: Anexo tecnico
order: 1010
roles: admin
---

Dieciséis dependencias de runtime en `requirements.txt` y dos de test en
`requirements-dev.txt`. Lo interesante no es la lista: es que **cada pieza dejó
una marca visible en la forma del código**. Si te preguntás por qué existe
`worker.py`, o por qué los caminos calientes esquivan el ORM, la respuesta casi
siempre es una restricción del framework, no una preferencia de estilo.

## Dash: todo es un callback sobre un componente

Dash no expone rutas: expone componentes con IDs y funciones que reaccionan a
ellos vía `Input`/`Output`/`State`. La consecuencia es medible: **309 decoradores
`@callback` contra apenas 5 rutas HTTP Flask**. No hay API REST ni capa de
controladores, y no la hay por diseño del framework.

**No hay auto-discovery de páginas.** Dash se instancia en `create_app()`
(`app/__init__.py`) con `use_pages=True` pero `pages_folder=""`. Los 46 módulos
de páginas y los 46 de callbacks se importan a mano con `importlib.import_module`
desde las listas `_PAGES` y `_CALLBACKS`. Si un import falla, el loop hace
`raise` a propósito: un módulo roto tiene que voltear el arranque, no dejar una
ruta muerta.

> Crear un archivo en `app/pages/` **no crea la ruta**. Si no lo agregás a
> `_PAGES`, la pantalla da 404 en silencio — sin error, sin log. Ya pasó con
> `/backtest`. `tests/test_module_registration.py` existe por eso.

**No hay server-push.** Toda operación larga usa el mismo patrón: un
`threading.Thread(daemon=True)`, el estado en un dict módulo-global (`_state` en
`data_center_callbacks.py`) y un `dcc.Interval` que la UI pollea — 2000 ms el
progreso, 30.000 ms el estado. Ese estado en memoria solo funciona con un
proceso; de ahí el lock persistido de `app/services/run_lock_service.py`. Los
background callbacks nativos de Dash no se usan: exigirían Celery o un caché en
disco.

La válvula de escape son los `clientside_callback`: 23 en total, 16 en
`app/callbacks/chart_callbacks.py`, donde el gráfico calcula los indicadores en
el browser para evitar el round-trip. Se resigna el tooling: ese JavaScript viaja
como string de Python y ningún linter lo mira. La única red son los tests de
paridad (`test_paridad_grafico.py`, `test_paridad_seleccion.py`,
`test_paridad_zonas.py`) y la regla de homologación del
[simulador de trades](/manual/simulador-de-trades).

## Flask y Flask-Login: cinco rutas y un portero global

El proyecto usa el server Flask crudo (`dash_app.server`) para sus cinco rutas:
`/login`, `/do-login`, `/`, `/logout` y `/health`. `wsgi.py` expone ese objeto
como `application` para mod_wsgi.

La protección de acceso no usa decoradores por vista, y no puede: las páginas
Dash no son vistas Flask decorables, las sirve el `page_container`. La única
forma de cubrir todo —incluidos los endpoints internos de Dash— es un
`before_request` global con whitelist de prefijos (`/_dash-`, `/_reload-hash`,
`/assets/`) más las rutas públicas.

De Flask-Login sale una pieza no obvia: `GuestUser` (`app/auth/manager.py`),
registrado como `login_manager.anonymous_user`, cuyas properties
`is_authenticated` e `is_admin` devuelven `is_public_access_enabled()`. Así se
implementa el modo público sin tocar las decenas de lugares que consultan
`current_user`. bcrypt hace el hashing en `User.set_password` y
`User.check_password`. Más en [la capa web](/manual/capa-web-y-registro).

## SQLAlchemy: ORM para el ABM, SQL crudo para el camino caliente

Hay un único engine global en `app/database.py` (pool de 30 más 20 de overflow,
`pool_pre_ping`, `pool_recycle=3600`) y una `scoped_session` thread-local, cuya
liberación cuelga del `teardown_appcontext` de Flask.

> El teardown **solo dispara en requests Flask**. Todo thread de background —los
> de los callbacks, los workers de los pools, los jobs del scheduler— tiene que
> llamar `Session.remove()` a mano o retiene conexión y objetos indefinidamente.
> Hay 32 call sites explícitos en `app/`: son obligatorios, no higiene opcional.

Los caminos calientes de escritura **no usan el ORM ni el Core compilado**:
emiten SQL crudo con `conn.exec_driver_sql(sql, rows)` y tuplas, o sea
executemany del DBAPI. Las razones están medidas en el código. En
`signal_backfill_range._bulk_insert`, la compilación de SQLAlchemy por fila
pesaba **~15% de la corrida**; en `technical_service._write_ind_series`, escribir
con tuplas evita construir un dict de Python por fila, **54 millones en un
rebuild**. El ORM sigue siendo el camino del ABM y de la configuración.

SQLAlchemy tampoco abstrae las diferencias que importan entre motores —upsert,
NULLS LAST, case-sensitivity, TRUNCATE—: eso vive en
`app/services/db_compat.py`. Ver
[Soportar dos motores de base de datos](/manual/soporte-dual-de-base-de-datos).

## Alembic: 85 migraciones y un freeze

La cadena 0001–0075 está **congelada como solo-MySQL** (backticks,
`AUTO_INCREMENT` crudo, `DATABASE()`): no compila contra PostgreSQL. Las bases
nuevas no la replayan, nacen con create_all + stamp head vía `scripts/init_db.py`,
y solo las migraciones desde la 0076 deben ser portables —
`tests/test_bootstrap_portability.py` las renderiza offline contra ambos
dialectos, sin base ni driver.

`alembic/env.py` filtra además las tablas dinámicas (`ind_*`, `sig_N`,
`strat_res_N`) con `_include_object`: viven a propósito fuera de `Base.metadata`,
y sin el filtro autogenerate las ve solo en la base y propone dropearlas todas.
Ver [modelo de datos](/manual/modelo-de-datos).

## APScheduler: la pieza que define la topología del deploy

Un único `BackgroundScheduler(timezone="UTC")` con dos jobs: `daily_price_update`
y `weekly_verification` (apagado por default). Los defaults se sobreescriben con
motivo escrito en `scheduler_service.py`: `misfire_grace_time` pasa de 1 segundo
a 3600, porque con el default el job se saltea **en silencio** si el thread timer
despierta más de un segundo tarde, cosa que pasa con los pools GIL-bound.

Que corra in-process es la restricción que ordena todo el deploy: el scheduler
vive en el proceso que lo arranca, así que con gunicorn multi-worker el job
diario se dispararía N veces. De ahí salen `--workers 1` en el `Procfile`, un
process type `worker: python worker.py` dedicado, y el flag `Config.RUN_SCHEDULER`
que se pone en 0 en el servicio web.

> `--workers 1` no es tuning de performance: es parte del contrato de corrección.
> Y el scheduler no se duplica por réplicas, se duplica por **cada proceso que
> ejecute `create_app()`** con `RUN_SCHEDULER` activo.

`worker.py` setea `os.environ["RUN_SCHEDULER"] = "1"` **antes** de importar `app`,
y el orden importa: `Config` es una clase cuyo cuerpo lee `os.environ` al
importarse. El mismo patrón explica por qué `process_child.py` vive fuera del
paquete `app`. Ver [despliegue](/manual/despliegue-y-configuracion).

## pandas, numpy y el techo del GIL

Son el motor de cálculo, y el GIL es la restricción reconocida y medida. Los
`ThreadPoolExecutor` ganan velocidad real porque el I/O de base y la parte
vectorizada liberan el GIL, pero no al nivel de multiprocessing puro. Subir
workers se probó y **empeoró**: cores+6 en el pool de indicadores llevó la
corrida de 3m08s a 3m42s (contención de disco, no falta de workers). El plan
escrito en `verification_service.py` es migrar a `ProcessPoolExecutor`; el pool
que ya existe usa spawn y no fork, porque el padre está lleno de threads. Ver
[concurrencia](/manual/concurrencia-y-multihilo).

## Lo que baja del navegador

**lightweight-charts no es una dependencia Python**: entra como `external_scripts`
desde el CDN de unpkg. Los estilos igual — `dbc.themes.DARKLY` y Font Awesome
como `external_stylesheets`, más Bootstrap 5.3.3 desde jsdelivr en la plantilla
de login. Nada está vendorizado en `assets/`, que solo tiene `custom.css` y
`dark_theme.js`.

> Sin internet en el navegador del cliente, la app se ve rota aunque el servidor
> esté perfectamente sano.

plotly sí es dependencia declarada y lo usan 14 módulos de visualización (RRG,
evolución, backtest, mapa de mercado); el gráfico técnico principal deliberadamente
no. openpyxl cubre el import/export Excel de 6 módulos, formato de los
`strategy_packs/`.

## yfinance y las fuentes de precios

yfinance descarga precios y fundamentales, pero **no es la única fuente**, pese a
lo que dicen las notas del proyecto. `app/sources/registry.py` registra tres
implementaciones de `PriceSourceBase`: `YahooFinanceSource`, `AmbitoSource`
(Riesgo País Argentina) y `CalculatedSource` (sintéticos). El contrato es
`download_history(ticker, start) -> pd.DataFrame`: sumar una fuente es
implementar la clase base y registrarla.

Detalle con causa concreta: `app/logging_setup.py` fija en WARNING los loggers de
yfinance, urllib3 y requests sin importar el `LOG_LEVEL`, porque en DEBUG cada
request a Yahoo emitía varias líneas y **reventaron el rate limit de logs de
Railway, 500 por segundo, durante un backfill de precios**.

## gunicorn, las versiones y cómo condicionan la forma de probar

gunicorn solo aparece en el `Procfile`. El `--timeout 120` da margen a los
requests que disparan cómputo pesado, donde el default de 30 segundos los
mataría. En dev y en el Codespace la app se levanta con `python run.py` y
`use_reloader=False`, para evitar el doble arranque que duplicaría el scheduler y
los estados en memoria.

Sobre las versiones hay deuda real: **las dieciséis dependencias se declaran con
`>=` y sin techo, no hay lockfile y no hay CI**. Nada las congela entre la PC de
desarrollo, el Codespace y Railway; el venv local corre varios majors por encima
del mínimo (dash 4.4.0 contra `>=2.14.0`, pandas 3.0.3 contra `>=2.1.0`) y dos
entornos instalados en fechas distintas pueden diferir sin que nada lo detecte.

La PC de desarrollo tampoco tiene **cuatro de las dieciséis dependencias**:
mysqlclient, psycopg, yfinance y gunicorn. Ahí no se levanta la app contra
ninguna base, así que la única red automatizada es pytest —una suite de cientos
de tests, todos de lógica pura contra un stub sqlite—. Que la suite corra sin
yfinance no es casualidad: ningún test importa `app/services/price_service.py`,
que hace `import yfinance` a nivel de módulo. Todo lo que toca la app viva se
verifica en el Codespace; ver
[Cómo se prueba y cómo se mide el rendimiento](/manual/pruebas-y-medicion).
