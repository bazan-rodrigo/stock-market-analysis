---
slug: despliegue-y-configuracion
title: Despliegue, configuracion y tareas programadas
chapter: Anexo tecnico
order: 1090
roles: admin
---

La app corre hoy en dos entornos reales: el Codespace de desarrollo
(`python run.py`, MariaDB o PostgreSQL) y Railway como producción (gunicorn más
un proceso worker dedicado, PostgreSQL). **Corren el mismo código y el mismo
`Procfile`: lo único que cambia son las variables de entorno que resuelve
`app/config.py`.** Esa es la regla de oro, y explica por qué acá casi no hay
archivos de despliegue: la parametrización vive afuera del artefacto.

Hay cuatro entrypoints, cada uno con un rol explícito. `run.py` es el servidor
de desarrollo de Dash (puerto 8050, sin debug ni reloader; su docstring dice "no
usar en producción"). `wsgi.py` expone la variable `application` que buscan
tanto mod_wsgi como gunicorn. `worker.py` corre el scheduler y no sirve HTTP. Y
el `Procfile` son dos líneas, que es todo el modelo de proceso de producción:

```text
web:    gunicorn wsgi:application --bind 0.0.0.0:$PORT --workers 1 --timeout 120
worker: python worker.py
```

El `--timeout 120` da margen a requests con cálculo pesado. El `--workers 1` no
es un default: es una decisión, y la que sigue la explica.

## Por qué el scheduler vive en su propio proceso

APScheduler corre **en el proceso que lo arranca**. Con gunicorn multi-worker o
con réplicas, cada proceso levantaría el suyo y el job diario se dispararía N
veces. El lock de corrida persistido lo deduplicaría, sí, pero esa alternativa
se descartó por desperdicio: N schedulers, N misfires. Se prefirió separar el
trabajo.

```text
   Railway
   ├── web     gunicorn  ─ RUN_SCHEDULER=0 ─ sirve HTTP
   ├── worker  worker.py ─ RUN_SCHEDULER=1 ─ solo APScheduler
   └── Postgres
                    ambos coordinados por run_lock
```

`worker.py` llama `create_app()` (que arranca APScheduler en threads daemon) y
mantiene vivo el proceso con `threading.Event().wait()`. El interruptor final
está en `create_app()`: si `Config.RUN_SCHEDULER` es verdadero llama
`start_if_enabled()`, si no loguea que el scheduler lo corre el worker dedicado.
El default es `1` para no romper el dev local ni el Codespace, que son de
proceso único.

Hay un detalle de orden que parece cosmético y no lo es: `worker.py` setea
`os.environ["RUN_SCHEDULER"] = "1"` **antes** de importar `create_app`.

> `Config` es una clase cuyos atributos se evalúan al importar el módulo.
> Cualquier override por entorno tiene que estar seteado antes del primer
> `import app.*`; cambiar una variable en caliente no afecta a `Config`. Es la
> misma trampa por la que `process_child.py` vive en la raíz del repo y no
> dentro de `app/` (ver
> [Concurrencia](/manual/concurrencia-y-multihilo)).

El modelo histórico de producción era Linux + Apache2 + mod_wsgi con
`WSGIDaemonProcess` de un solo proceso, y buena parte del diseño de concurrencia
asume ese modelo. Conviene decirlo con todas las letras: **en el repo no hay
ninguna configuración de Apache versionada** — ni `.conf`, ni Dockerfile, ni
archivos de plataforma. Todo lo que se sabe de mod_wsgi sale de docstrings y de
notas de diseño. Quedan vestigios vivos igual: `create_app()` limpia locks de
corrida muertos al arranque pensando en los reciclados del proceso WSGI, y
`process_pool.spawn_executable_ok()` degrada el pool a threads cuando
`sys.executable` no parece un intérprete de Python (bajo mod_wsgi embebido
apunta a `httpd`, y spawn lanzaría `httpd` como intérprete).

## Configuración: tres capas distintas

La primera es `Config`, resuelta por `_get(key, default)` con esta precedencia:
variable de entorno con el nombre en MAYÚSCULAS, después la clave en minúsculas
bajo `[settings]` de `conf.properties`, después el default del código. Si no hay
default, levanta un `RuntimeError` que nombra la variable y la clave faltantes.

> Ese último escalón hoy está muerto: las 16 claves pasan un default, así que
> **ninguna variable es obligatoria de verdad**. Una base mal configurada no
> falla al arrancar con un mensaje claro: falla más tarde, al conectar.

| Tema | Claves tunables |
|---|---|
| Conexión | `secret_key`, `db_host`, `db_port`, `db_name`, `db_user`, `db_password`, `database_url` |
| Pool | `db_pool_size` (30), `db_max_overflow` (20) |
| Proceso | `run_scheduler` (1) |
| Logging | `log_level` (INFO), `log_file` |
| ProcessPool | `ind_pool_procs` (0 = auto), `ind_pool_max_procs` (12), `ind_pool_min_assets` (1500), `ind_child_db_pool` (2) |

Los defaults del ProcessPool salen de un presupuesto de conexiones explícito: 12
procesos × 2 conexiones + 50 del padre = 74, por debajo del límite de 100 que
PostgreSQL trae de fábrica (MySQL da 151). Y `_normalize_db_url()` convierte
`postgres://` y `postgresql://` a `postgresql+psycopg://`, porque Railway entrega
la cadena sin driver y SQLAlchemy, sin el prefijo explícito, busca psycopg2 —que
no está instalado— y falla.

> `conf.properties.example` documenta `scheduler_hour` y `scheduler_minute`,
> pero `Config` **nunca las lee**: son las únicas dos apariciones de esas claves
> en todo el repo. El horario vive en la tabla `scheduler_config` y se cambia
> desde [Scheduler de tareas](/manual/scheduler). Editar el archivo no hace nada.

Esa es justamente la segunda capa: **configuración persistida en BD, que
sobrevive a los deploys**. `scheduler_config` guarda `enabled`, `hour`, `minute`
y los campos del job semanal; `app_settings` guarda el flag de acceso público,
que `app_config_service` cachea 30 segundos por proceso para no pegarle a la
base en cada request (el precio: en multi-proceso, los demás ven el cambio hasta
30 segundos tarde). La tercera capa es un flag suelto: `USE_WIDE_IND_TABLES` se
lee con `os.environ.get` en cada llamada, no pasa por `Config` y por eso no se
puede poner en `conf.properties`. El admin inicial, en cambio, es literal de
clase (`admin` / `admin123`): no se puede sobreescribir por entorno, y lo crea
`scripts/init_db.py` avisando por log que hay que cambiarlo.

## Los dos jobs y el lock

El scheduler es un único `BackgroundScheduler(timezone="UTC")` con dos jobs
independientes. `_daily_update_job` encadena precios, delta de indicadores,
fundamentales y scores de grupo, y después señales y estrategias — es la misma
función que el botón "Ejecutar" del [Centro de Datos](/manual/centro-de-datos),
así que si la app estuvo apagada unos días, el delta los completa solos.
`_weekly_verification_job` recalcula todo en memoria y marca discrepancias en
`asset_verification_flag`; es semanal porque esas marcas no necesitan estar al
minuto, y nace deshabilitado con su propio toggle. Ambos terminan con
`Session.remove()` en el `finally`, porque el thread del scheduler se reutiliza
entre corridas y no hay que arrastrar conexión ni objetos de un día al otro.

Los dos `add_job` sobreescriben tres defaults de APScheduler:
`misfire_grace_time=3600`, `coalesce=True` y `max_instances=1`. El que importa es
el primero: **el default de la librería es 1 segundo**, y saltea el job en
silencio si el thread timer despierta más tarde que eso, cosa que pasa con pools
que compiten por el GIL. Una hora de gracia tolera un arranque demorado sin
cancelar la corrida nocturna.

Antes de arrancar, el job diario toma el lock persistido con
`rl.guarded_acquire(rl.HEAVY_WRITE)`. Si otro lo tiene vivo, loguea
"Actualización diaria salteada" y retorna sin hacer nada. `HEAVY_WRITE` es una op
única compartida por el Centro de Datos, los botones de Precios, la limpieza y la
corrida nocturna: son mutuamente excluyentes, una sola corrida pesada a la vez.

> Si un admin deja corriendo un "Recalcular completo" a la hora de la corrida
> nocturna, la nocturna **no espera: se saltea entera**. El hueco lo tapa el
> delta del día siguiente, no un reintento.

APScheduler no persiste jobs: el jobstore es el default en memoria. Lo que
sobrevive al reinicio es la fila de `scheduler_config`, que `start_if_enabled()`
lee al arrancar la app para reconstruir los jobs.

## Bootstrap de la base y migraciones

`scripts/init_db.py` es idempotente y decide solo: si la base no tiene ninguna
tabla hace `Base.metadata.create_all(engine)` más `alembic stamp head`; si ya
tiene tablas hace `alembic upgrade head`. Nacer por `create_all` es el único
camino que funciona en PostgreSQL, porque la cadena 0001–0075 quedó congelada
como solo-MySQL. Hay 85 migraciones en total; desde la 0076 tienen que ser
portables, y `tests/test_bootstrap_portability.py` las renderiza offline contra
`mysql://` y `postgresql://` sin base ni driver (ver
[Soporte dual](/manual/soporte-dual-de-base-de-datos)). El replay de la cadena
completa quedó detrás de `--via-migrations`, y solo para comparar esquemas en
MySQL.

> La detección mira si la base tiene **cero** tablas. Una base con una sola tabla
> suelta, creada a mano, cae al camino de migraciones y va a fallar contra la
> cadena congelada si el motor es PostgreSQL.

Una base nacida por `create_all` no tiene las tablas dinámicas `ind_{code}`,
porque no están en `Base.metadata`: las materializa `ensure_builtin_data()` al
arrancar la app, salteando los códigos que ya viven en las tablas anchas. Y
`alembic.ini` deja `sqlalchemy.url` vacía a propósito, para que `env.py` la
inyecte desde `Config` solo si falta y los tests de portabilidad puedan pasar una
URL explícita por dialecto. En la misma línea, `_include_object` de `env.py`
filtra las tablas dinámicas del autogenerate: sin ese filtro, alembic las ve solo
en la base y propone dropearlas todas.

## Dónde se verifica qué

El flujo del equipo condiciona todo lo anterior: se edita en la PC local Windows,
que **no tiene base de datos**, se hace push, y se hace `git pull` en el
Codespace, donde la app corre contra MariaDB (`sudo service mariadb start`, no
`mysql`) o PostgreSQL según `DB_ENGINE` —una variable que solo leen los scripts
de setup, nunca la app—. Como esa PC no levanta la app, la red de seguridad
automatizada es pytest, corrido a mano antes de cada push: no hay CI versionado.
Todo lo que toca la app viva —callbacks, migraciones, corridas reales— se prueba
en el Codespace, y hay un botón en `/admin/verify` que corre la suite como
subproceso con el mismo Python de la app, con 300 s de timeout.

Esa suite es además una salvaguarda de deploy: `tests/conftest.py` **fuerza**
`DATABASE_URL` a un stub sqlite (no usa `setdefault`) y aborta en
`pytest_sessionstart` si el engine no quedó en sqlite. Varios fixtures hacen
`DELETE FROM assets`, y `prices` e `ind_*` cuelgan con `ON DELETE CASCADE`: un
`pytest` distraído en el Codespace o en Railway vaciaría la base entera. Ver
[Pruebas y medición](/manual/pruebas-y-medicion).

> Dos asimetrías para tener presentes. El conftest fuerza
> `USE_WIDE_IND_TABLES=0`, el opuesto del default de producción: un test que
> pasa no prueba el camino de tablas anchas. Y `/health` no está en
> `_PUBLIC_PATHS`, así que un healthcheck externo sin sesión recibe un redirect a
> `/login`, no un 200 — cosa que hoy no molesta a nadie porque no hay ningún
> healthcheck configurado en el repo.
