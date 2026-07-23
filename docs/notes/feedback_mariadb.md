---
name: Motor de base de datos del proyecto
description: "El motor es una elección de INSTALACIÓN (PostgreSQL o MySQL), no una propiedad del entorno; hoy Railway+PostgreSQL, pero el soporte dual se mantiene a propósito"
type: feedback
originSessionId: 72e4d4e7-35d5-4ee2-bcc4-5bfdf806cb9a
modified: 2026-07-23T02:40:34.103Z
---
**El motor de base de datos es una elección de INSTALACIÓN**: PostgreSQL o
MySQL/MariaDB, elegida una vez y válida en cualquier entorno donde corra la app.
No es una propiedad del entorno — que hoy sea Railway no implica PostgreSQL, y
que mañana sea un Codespace no implica MySQL. Esa confusión existe en el código
(`.devcontainer/devcontainer.json` fija `DB_ENGINE: mysql`, Railway lo deduce de
`DATABASE_URL`) y es lo que hay que desenredar.

**Hoy: Railway sobre PostgreSQL**, y el usuario no tiene motivos para cambiar.
Pero **el soporte dual se mantiene a propósito** (decisión del 23-jul-2026, tras
evaluar retirarlo y descartarlo): la posibilidad de MySQL y de Codespace se
conserva "por cualquier cosa que pase en el futuro". Ver
[[project-postgres-only-estudio]].

Corolario del usuario: **no está bien que se instalen los dos motores si solo se
va a usar uno.** → **RESUELTO el 23-jul** (`29fbb5f`, `e43e281`): `DB_ENGINE` es
el eje y la app lo lee; el driver vive en `requirements-<motor>.txt` y se
instala aparte; `both` se retiró de los scripts de setup; la elección se
persiste en `conf.properties`. Si `db_engine` y `database_url` se contradicen,
la app **no arranca**.

Nota histórica: mientras el Codespace estuvo en uso, el servicio instalado ahí
era **MariaDB, no MySQL** — el comando era `sudo service mariadb start`.

**Why:** el usuario decidió conservar la optionalidad de motor en vez de
consolidar, y separar esa decisión del entorno de despliegue.

**How to apply:** no proponer borrar la rama MySQL ni "simplificar" `db_compat`
por inercia porque hoy se use PostgreSQL. Al tocar SQL con sabor a motor,
mantener las dos ramas. Aviso honesto que conviene repetir: la rama MySQL **no
se ejercita hace semanas** (el refactor de tablas anchas nunca corrió contra
MariaDB), así que "soportado" significa que el código está, no que esté
validado. Ver [[entorno-de-verificacion]] para dónde se prueba hoy.
