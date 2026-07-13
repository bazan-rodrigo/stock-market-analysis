---
name: Servicio de base de datos es MariaDB
description: En el Codespace el servicio de base de datos es MariaDB, no MySQL
type: feedback
originSessionId: 72e4d4e7-35d5-4ee2-bcc4-5bfdf806cb9a
---
El servicio instalado en el Codespace es MariaDB, no MySQL.

**Why:** El usuario lo aclaró explícitamente al recordar que el comando correcto usa `mariadb`.

**How to apply:** Siempre usar `sudo service mariadb start` (no `mysql`) al dar instrucciones para levantar el entorno en el Codespace.
