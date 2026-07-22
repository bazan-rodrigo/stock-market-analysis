---
name: Motor de base de datos del proyecto
description: DESACTUALIZADA desde el 22-jul-2026 — la base es PostgreSQL (Railway y Codespace), MariaDB ya no se usa
type: feedback
originSessionId: 72e4d4e7-35d5-4ee2-bcc4-5bfdf806cb9a
modified: 2026-07-22T13:50:04.392Z
---
**El motor es PostgreSQL.** El 22-jul-2026 el usuario confirmó que la
instalación MariaDB **ya no se usa**: la única base es PostgreSQL en Railway
(producción desde el 17-jul) y en el Codespace se levanta con
`sudo service postgresql start`.

Nota histórica: mientras hubo soporte dual, el servicio instalado en el
Codespace era **MariaDB, no MySQL** — el comando era `sudo service mariadb
start`. Eso sigue valiendo solo si alguien levanta a propósito el modo
`DB_ENGINE=mysql`, que la etapa B del corte va a eliminar.

**Why:** el usuario aclaró en su momento que el servicio era `mariadb` y no
`mysql`; después decidió consolidar todo en PostgreSQL.

**How to apply:** al dar instrucciones para levantar el entorno, usar
`sudo service postgresql start`. No proponer arrancar MariaDB ni asumir que
hay un segundo motor disponible. Ver [[project-postgres-only-estudio]] para
el plan de retiro del soporte dual.
