# Guía de deploy — Codespace y Railway

Guía operativa de los dos entornos donde corre la app y de las tareas puntuales
más frecuentes (traer el head, armar pruebas, conectar a otra base, apagar sin
perder datos, recrear la base). Todo sale de convenciones ya acordadas
(ver `CLAUDE.md`) y de decisiones tomadas al montar Railway.

> Regla de oro: **la app no cambia entre entornos.** Mismo código, mismo
> `Procfile`. Lo único que cambia son las **variables de entorno** que resuelve
> `app/config.py` (prioriza env vars sobre `conf.properties`).

---

## 1. Panorama de los dos entornos

| | **Codespace** (dev) | **Railway** (prod) |
|---|---|---|
| Arranque | `python run.py` (servidor Dash de dev, :8050) | `gunicorn` (`web`) + `python worker.py` (`worker`) |
| Base | MariaDB/MySQL local (o PostgreSQL con `DB_ENGINE`) | PostgreSQL (servicio del proyecto) |
| Scheduler | en el mismo proceso (`run.py`) | **solo** en el servicio `worker` (`RUN_SCHEDULER=0` en `web`) |
| Config | env vars del `devcontainer.json` | Variables de cada servicio en el panel |

**Por qué el `worker` separado en Railway:** APScheduler corre en el proceso que
lo arranca. Con `gunicorn` (aunque sea 1 worker) + posibles réplicas, el job
diario se dispararía N veces. Solución: el `web` va con `RUN_SCHEDULER=0` y el
scheduler vive en un proceso dedicado (`worker.py`, que fuerza `RUN_SCHEDULER=1`).
El lock de corrida persistido (`run_lock`) coordina ese scheduler con las
corridas manuales del Centro de Datos. Ver `worker.py` y `Procfile`.

**`Procfile`** (raíz del repo, lo lee Railway):
```
web:    gunicorn wsgi:application --bind 0.0.0.0:$PORT --workers 1 --timeout 120
worker: python worker.py
```
- `wsgi:application` → entrypoint WSGI existente (`wsgi.py` expone `application`).
- `--workers 1` → un solo proceso web (refuerza el modelo de proceso único).
- `--timeout 120` → margen para requests con cálculo pesado.

---

## 2. Codespace (desarrollo)

### 2.1 Primer arranque
El devcontainer corre `.devcontainer/setup.sh` en `postCreateCommand`: instala el
motor (según `DB_ENGINE`), las deps, e inicializa la base (`scripts/init_db.py`).
Al terminar:
```bash
python run.py            # levanta la app en http://localhost:8050  (admin/admin123)
```

Motor de base (variable `DB_ENGINE` del devcontainer, default `mysql`):
- `mysql` → MariaDB local, usa los `DB_*` del entorno.
- `postgres` → PostgreSQL; el setup exporta `DATABASE_URL` en `~/.bashrc`.
- `both` → los dos lado a lado (paridad del soporte dual). La app corre contra
  MySQL salvo que exportes `DATABASE_URL` (ver §4.3).

Arrancar el motor a mano si hiciera falta (el servicio es **mariadb**, no mysql):
```bash
sudo service mariadb start          # MySQL/MariaDB
sudo service postgresql start       # PostgreSQL
```

### 2.2 Traer los cambios del head (§ caso frecuente)
Después de cada push desde la PC local:
```bash
git pull
```
Si el pull trae **migraciones nuevas**, aplicarlas sobre la base existente:
```bash
python scripts/init_db.py           # base existente → alembic upgrade head
```
Si trae cambios en `requirements.txt`:
```bash
pip install -r requirements.txt
```
Reiniciar `run.py` (Ctrl-C y volver a lanzar) para tomar el código nuevo.

### 2.3 Correr la suite (antes de cada push que toque servicios)
```bash
./venv/Scripts/python.exe -m pytest      # (en la PC local Windows)
python -m pytest                         # (en el Codespace)
```

---

## 3. Railway (producción)

### 3.1 Estructura de servicios
Un proyecto con tres servicios: **`web`** (gunicorn), **`worker`** (scheduler) y
**`Postgres`** (base). `web` y `worker` salen del mismo repo/`Procfile`.

### 3.2 Deploy inicial desde cero
1. **Crear la base:** `+ New → Database → Add PostgreSQL`.
2. **Conectar `DATABASE_URL`** en **ambos** servicios de app (`web` y `worker`),
   pestaña *Variables*:
   ```
   DATABASE_URL = ${{Postgres.DATABASE_URL}}
   ```
   Usar la **referencia** (Railway autocompleta al escribir `${{`). No hay que
   corregir el prefijo: `app/config.py` normaliza `postgres://` /
   `postgresql://` → `postgresql+psycopg://` solo (el proyecto usa psycopg3).
3. **Otras variables** (en ambos):
   - `SECRET_KEY` → valor propio de prod.
   - `LOG_LEVEL` → `INFO`.
   - `RUN_SCHEDULER` → **`0` en `web`**, **`1` (o sin definir) en `worker`**.
4. **Crear el esquema** (la base nace vacía). Desde una shell del servicio `web`:
   ```
   python scripts/init_db.py
   ```
   Crea tablas (create_all + stamp head) + datos de referencia + admin
   `admin/admin123`. Idempotente.
5. **Reiniciar** `web` y `worker` (Deployments → ⋮ → Restart).
6. **Verificar:** URL pública en `web` → *Settings → Networking → Public Domain*
   (o *Generate Domain*). Login `admin/admin123` → cambiar la contraseña.
   Revisar logs del `worker` (scheduler arrancado sin error).

---

## 4. Casos específicos

### 4.1 Traerse el head
- **Codespace:** §2.2 (`git pull` + `init_db.py` si hay migraciones + reiniciar).
- **Railway:** un `git push` a la rama que sigue el environment dispara deploy
  automático (si está activo). Para deploy manual, ver §4.6. Si el push trae
  migraciones, correr `python scripts/init_db.py` en la shell del `web` **antes**
  de que el tráfico use el esquema nuevo (o incluirlo como paso de release).

### 4.2 Armar ambiente de pruebas (staging)
Railway → **Environments** (un proyecto, varios environments aislados: cada uno
con su Postgres, sus variables y su URL). Decidido: **promoción manual**.
1. Nuevo environment `staging` (duplicando `production` como plantilla).
2. Su propio plugin **PostgreSQL** + variables (`SECRET_KEY` de prueba,
   `DATABASE_URL = ${{Postgres.DATABASE_URL}}`, `LOG_LEVEL=DEBUG`,
   `RUN_SCHEDULER` 0/1 como en prod).
3. `python scripts/init_db.py` una vez en esa base nueva.
4. **Auto-deploy** (Settings → Deploy de cada servicio):
   - `staging` → auto-deploy **activado** (rama `master`).
   - `production` → auto-deploy **desactivado** → se publica a mano
     (Deployments → Redeploy) al mismo commit ya validado en staging.

Flujo: push a `master` → staging deploya solo → probás → promovés a prod a mano.

### 4.3 Conectarse a otra base
La base la decide **`DATABASE_URL`** (o los `DB_*` si no hay URL). Casos:

- **Apuntar el Codespace a otro Postgres** (p. ej. el de Railway, para inspección
  o para correr `init_db.py` remoto):
  ```bash
  DATABASE_URL="postgresql+psycopg://user:pass@host:puerto/db" python scripts/init_db.py
  DATABASE_URL="postgresql+psycopg://user:pass@host:puerto/db" python run.py
  ```
  (En Railway, la URL externa está en el servicio Postgres → *Connect* →
  *Public Networking*; la interna `*.railway.internal` solo resuelve dentro de
  Railway.) El prefijo `postgres://` de Railway lo normaliza `config.py`, pero
  al pasarlo a mano conviene ponerlo ya como `postgresql+psycopg://`.

- **Cambiar de motor** (MySQL ↔ PostgreSQL): setear `DATABASE_URL` completo.
  - MySQL: `mysql+mysqldb://user:pass@host:3306/db?charset=utf8mb4`
  - PostgreSQL: `postgresql+psycopg://user:pass@host:5432/db`
  El soporte dual está en `app/services/db_compat.py`; la base nueva se crea con
  `scripts/init_db.py` en cualquier motor.

- **En Railway**, cambiar a otra base = editar `DATABASE_URL` en `web` y `worker`
  y reiniciar ambos.

> Recordatorio: `DATABASE_URL` de un Postgres externo pega contra datos reales.
> Para pruebas destructivas, usar una base descartable (staging o local).

### 4.4 Apagar por un día sin perder datos
- **No es obligatorio** apagar nada; saltarse la corrida diaria es inocuo (el
  **delta** llena el hueco en el próximo run).
- Para **ahorrar créditos**: detener el deploy de `web` y `worker`
  (Deployments → ⋮ → **Remove**/stop). Los datos viven en el **volumen** del
  Postgres y sobreviven. **Parar ≠ borrar:** no usar *Delete service* sobre el
  Postgres (destruye el volumen).
- Alternativa cómoda: **App Sleeping** en `web` (duerme sin tráfico, despierta con
  el primer request). El `worker` y el Postgres no se benefician de sleeping.

### 4.5 Recrear la base desde cero
1. Si borraste el **servicio** Postgres: recrearlo (`+ New → Database →
   PostgreSQL`); si el nombre cambió, ajustar la referencia
   `${{Postgres.DATABASE_URL}}` en `web` y `worker`.
   Si solo vaciaste la base (servicio intacto): no tocar variables.
2. `python scripts/init_db.py` (base vacía → esquema + semilla + admin).
3. Reiniciar `web` y `worker`.

### 4.6 Desactivar auto-deploy en push
Por servicio y por environment: **Settings → Deploy** (o *Source/Triggers*) →
apagar **Automatic Deploys** de la rama. A partir de ahí, publicar es manual
(Deployments → Redeploy). Típico del esquema elegido: `staging` auto,
`production` manual (§4.2).

### 4.7 Reiniciar servicios
Deployments → ⋮ → **Restart** (mismo build) o **Redeploy** (build limpio desde el
último commit). Tras cambiar variables que afectan la conexión, reiniciar
**`web` y `worker`**.

---

## 5. Checklist rápido

**Codespace (retomar sesión):**
```bash
git pull
sudo service mariadb start          # o postgresql, según DB_ENGINE
python scripts/init_db.py           # solo si el pull trajo migraciones
python run.py                       # http://localhost:8050
```

**Railway (deploy inicial / base nueva):**
1. `+ New → Database → PostgreSQL`.
2. `DATABASE_URL = ${{Postgres.DATABASE_URL}}` en `web` y `worker`.
3. `SECRET_KEY`, `LOG_LEVEL=INFO`, `RUN_SCHEDULER` (0 en web / 1 en worker).
4. `python scripts/init_db.py` (shell del `web`).
5. Restart `web` + `worker`.
6. Generar dominio, login `admin/admin123`, cambiar contraseña.
