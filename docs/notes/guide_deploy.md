# Guía de instalación y deploy — elegir motor, Codespace y Railway

Guía operativa: qué motor de base elegís al instalar, los dos entornos donde
puede correr la app, y las tareas puntuales más frecuentes (traer el head,
armar pruebas, conectar a otra base, apagar sin perder datos, recrear la base).
Todo sale de convenciones ya acordadas (ver `CLAUDE.md`) y de decisiones
tomadas al montar Railway.

> Regla de oro: **la app no cambia entre entornos.** Mismo código, mismo
> `Procfile`. Lo único que cambia son las **variables de entorno** que resuelve
> `app/config.py` (prioriza env vars sobre `conf.properties`).

---

## 0. Lo primero: elegir el motor

**El motor de base es una elección de INSTALACIÓN, no una propiedad del
entorno.** Que corras en Railway no implica PostgreSQL, y que corras en un
Codespace no implica MySQL: elegís una vez, con `db_engine`, y de ahí salen
solos el driver de Python, el puerto y el usuario por defecto.

| | `db_engine = postgres` (default) | `db_engine = mysql` |
|---|---|---|
| Driver | `requirements-postgres.txt` (`psycopg`, con wheels) | `requirements-mysql.txt` (`mysqlclient`, compila) |
| Puerto / usuario por defecto | 5432 / `postgres` | 3306 / `root` |
| Servicio | `sudo service postgresql start` | `sudo service mariadb start` (es mariadb, no mysql) |

Instalar las dependencias es siempre el archivo común **más** el del motor:

```bash
pip install -r requirements.txt -r requirements-postgres.txt   # o -mysql
```

**Nunca se instalan los dos motores.** Montar uno que no se va a usar es puro
costo: `mysqlclient` es una extensión en C que hay que compilar. Si alguna vez
hace falta comparar motores, se levanta el segundo a mano — es un
procedimiento de laboratorio, no una forma de instalar.

`database_url`, si la definís, **gana** sobre todo lo anterior (es lo que usa
Railway). Y si contradice a `db_engine` —por ejemplo `db_engine = mysql` con
una URL de PostgreSQL— **la app no arranca** y te dice cuál es la
contradicción, en vez de fallar más tarde con un error de driver. Si la URL es
la buena, borrá `db_engine` y el motor se deduce de ella.

> Hoy corre **PostgreSQL en Railway**. El soporte de MySQL se mantiene como
> opción, pero **no se ejercita hace tiempo**: el refactor de tablas anchas
> nunca corrió contra MariaDB. "Soportado" significa que el código está, no
> que esté validado — revivirlo costaría una corrida de verificación.

---

## 1. Panorama de los dos entornos

| | **Codespace** (dev) | **Railway** (prod, hoy) |
|---|---|---|
| Arranque | `python run.py` (servidor Dash de dev, :8050) | `gunicorn` (`web`) + `python worker.py` (`worker`) |
| Base | la que elegiste al instalar (§0) | PostgreSQL (servicio del proyecto) |
| Scheduler | en el mismo proceso (`run.py`) | **solo** en el servicio `worker` (`RUN_SCHEDULER=0` en `web`) |
| Config | `conf.properties` + env vars del `devcontainer.json` | Variables de cada servicio en el panel |

**Por qué el `worker` separado en Railway:** APScheduler corre en el proceso que
lo arranca. Con `gunicorn` (aunque sea 1 worker) + posibles réplicas, el job
diario se dispararía N veces. Solución: el `web` va con `RUN_SCHEDULER=0` y el
scheduler vive en un proceso dedicado (`worker.py`, que fuerza `RUN_SCHEDULER=1`).
El lock de corrida persistido (`run_lock`) coordina ese scheduler con las
corridas manuales del Centro de Datos. Ver `worker.py` y `Procfile`.

**`Procfile`** (raíz del repo, lo lee Railway):
```
web:    gunicorn wsgi:application --bind 0.0.0.0:$PORT --workers 1 --timeout 1800
worker: python worker.py
```
- `wsgi:application` → entrypoint WSGI existente (`wsgi.py` expone `application`).
- `--workers 1` → un solo proceso web (refuerza el modelo de proceso único).
- `--timeout 1800` → **no es "margen para requests pesados": es lo que mantiene
  vivas las corridas del Centro de Datos.** Viven en un thread daemon ADENTRO
  del proceso web, y la fase de indicadores es cálculo puro que no le da
  señales de vida al árbitro de gunicorn: con `--timeout 120` el worker moría
  con SIGKILL (sin traceback, sin log) y la corrida "desaparecía". Con
  `--workers 1` el timeout bajo tampoco protegía de nada — matar al único
  worker es apagar la app igual. Medido: 113 s de fase de indicadores con 499
  activos, o sea el 94 % del presupuesto viejo. **Es un parche con fecha de
  vencimiento**: extrapolando lineal, 10.000 activos dan ~2.265 s y vuelven a
  cruzar el tope; el arreglo real es sacar las corridas a `worker.py`.

---

## 2. Codespace (desarrollo)

### 2.1 Primer arranque
El devcontainer corre `.devcontainer/setup.sh` en `postCreateCommand`: instala
**un** motor, su driver, el resto de las deps, e inicializa la base
(`scripts/init_db.py`). Al terminar:
```bash
python run.py            # levanta la app en http://localhost:8050  (admin/admin123)
```

**Elegir el motor** (§0): por defecto instala **PostgreSQL**. Para MySQL, crear
el Codespace con `DB_ENGINE=mysql` en el entorno (secreto/variable del
Codespace). El setup **persiste la elección en `conf.properties`**, que está
gitignoreado porque es la config de esa instalación: de ahí en más la app deriva
sola el driver, el puerto y el usuario, sin depender de que alguien exporte
variables en la shell.

El motor **no** se fija en `devcontainer.json` a propósito. Si `DB_PORT` o
`DB_USER` estuvieran ahí, le ganarían a lo derivado por ser variables de
entorno, y la instalación quedaría apuntando al motor equivocado — que era
exactamente el enredo que tenía este proyecto.

Arrancar el motor a mano si hiciera falta:
```bash
sudo service postgresql start       # PostgreSQL
sudo service mariadb start          # MySQL/MariaDB (el servicio es mariadb)
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
Si trae cambios en las dependencias (siempre el común **más** el del motor):
```bash
pip install -r requirements.txt -r requirements-postgres.txt   # o -mysql
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

### 3.1b Cómo se instala el driver en el build (`railpack.json`)

Railway construye con **Railpack**, que detecta `requirements.txt` y corre
`pip install -r requirements.txt`. Como el driver ya **no** está ahí (§0), hace
falta decirle que instale también el del motor. Eso lo declara `railpack.json`
en la raíz del repo, extendiendo el paso de install en vez de reemplazarlo:

```json
{
  "$schema": "https://schema.railpack.com",
  "steps": {
    "install": {
      "commands": [
        "...",
        "pip install -r requirements.txt -r requirements-${DB_ENGINE:-postgres}.txt"
      ]
    }
  }
}
```

Tres detalles que explican por qué está escrito así:

- El `"..."` es la sintaxis de Railpack para **extender** un array en vez de
  pisarlo: conserva el install por defecto y le suma el nuestro.
- El comando igual instala `requirements.txt` **además** del driver, aunque el
  paso por defecto ya lo haya hecho. Es deliberado: si el `"..."` no se
  aplicara, este comando solo alcanza para dejar el entorno completo. Repetirlo
  es casi gratis (pip ve todo satisfecho); quedarse corto sería una app sin
  dependencias.
- El fallback `:-postgres` hace que el build funcione aunque `DB_ENGINE` no
  esté definida. Conviene igual **definirla explícitamente** en las variables
  de los servicios `web` y `worker`, para que la elección de motor esté a la
  vista en un solo lugar.

> **Pendiente de verificar en el primer deploy:** que la interpolación
> `${DB_ENGINE:-postgres}` se expanda de verdad (depende de si Railpack corre
> los comandos a través de un shell, cosa que no está documentada). Si no
> expandiera, el build **falla** buscando un archivo con ese nombre literal —
> y un build fallido no despliega, así que la versión anterior sigue corriendo.
> El arreglo sería poner el nombre literal (`requirements-postgres.txt`) y
> anotar que cambiar de motor toca esa línea.

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
   - `DB_ENGINE` → `postgres`. No es obligatoria (el default de la app y el
     del build son PostgreSQL), pero definirla deja la elección de motor
     explícita y en el mismo lugar que el resto. Si la ponés, tiene que ser
     coherente con la `DATABASE_URL` o la app no arranca (§0).
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

- **Cambiar de motor** (MySQL ↔ PostgreSQL): son **tres** cosas, porque el
  motor es una elección de instalación (§0) y no solo una cadena de conexión.
  1. `db_engine` en `conf.properties` (o la variable `DB_ENGINE`).
  2. Instalar el driver del motor nuevo:
     `pip install -r requirements.txt -r requirements-<motor>.txt`.
  3. Si tenés `database_url` explícita, actualizarla — o borrarla y dejar que
     se derive. Si queda apuntando al motor viejo, **la app no arranca** y te
     dice cuál es la contradicción.

  El soporte dual está en `app/services/db_compat.py`; la base nueva se crea con
  `scripts/init_db.py` en cualquier motor. Ojo: cambiar de motor **no** migra
  los datos; es una instalación nueva salvo que los trasvases aparte.

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
