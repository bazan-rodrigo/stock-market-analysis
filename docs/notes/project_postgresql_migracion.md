---
name: postgresql-migracion-futura
description: "El usuario planea migrar la base de datos de MariaDB/MySQL a PostgreSQL en algún momento futuro, sin fecha definida"
metadata: 
  node_type: memory
  type: project
  originSessionId: 3f4209f9-1b44-4cf9-9f19-80332541affc
---

El usuario mencionó (jul-2026) que en algún momento va a migrar la base de
datos del proyecto de MariaDB/MySQL a PostgreSQL. Sin fecha ni urgencia
definida — es un plan a futuro, no un trabajo en curso.

**Why:** no se dio una razón específica en la conversación; parece una
preferencia/decisión de infraestructura a largo plazo.

**How to apply:**
- Al proponer código nuevo que toque la capa de datos, tener en cuenta que
  hay bastante SQL específico de MySQL en el proyecto que habrá que migrar
  ese día: `sqlalchemy.dialects.mysql.insert` + `ON DUPLICATE KEY UPDATE`
  (aparece en `technical_service.py`, `fundamental_service.py`,
  `price_service.py`, `synthetic_service.py`, y en `_upsert_ind_asset_meta`/
  `_upsert_ind_stats_meta` agregadas en jul-2026) — en Postgres es
  `INSERT ... ON CONFLICT (...) DO UPDATE SET col = EXCLUDED.col`
  (`sqlalchemy.dialects.postgresql.insert`). También el driver
  (`mysqlclient`/`MySQLdb` → `psycopg2`/`psycopg`) y el `DATABASE_URL`.
  `TRUNCATE TABLE` es portable entre ambos motores.
- No es necesario evitar código MySQL-específico "por las dudas" hoy —
  simplemente tenerlo en mente si el usuario pregunta por el tema o pide
  ayuda para planificar la migración, y avisar si una decisión de diseño
  puntual haría esa migración más difícil de lo necesario.
- **Acordado (12-jul-2026):** cuando se haga esta migración, se encara en
  el mismo trabajo la migración del pool de indicadores a
  `ProcessPoolExecutor` con partición por activos — ver
  [[processpool-particion-por-activos]] para el diseño ya elegido.
- Ver también [[feedback_mariadb]] (cómo arrancar el servicio hoy) y
  [[project_decisions]] (decisiones técnicas generales del proyecto).
