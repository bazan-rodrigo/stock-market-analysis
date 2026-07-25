---
name: project_reset_fabrica
description: Botón/CLI de reinicio TOTAL a estado de fábrica en Limpieza de datos; verificación pendiente en Railway
metadata: 
  node_type: memory
  type: project
  originSessionId: 76d3c116-8127-41f3-9e25-a15541d55c8c
  modified: 2026-07-25T14:08:53.098Z
---

25-jul: se agregó a `/admin/cleanup` (y a `scripts/clean_data.py --reset`) un
**reinicio TOTAL a estado de fábrica** — deja la base como recién instalada.
Decisión del usuario: alcance = reset total (borra TODO, incluido lo que
`clean_data` preserva: activos, precios, catálogos, definiciones de
señales/estrategias, sintéticos, conversión, carteras+operaciones) y usuarios =
**solo admin/admin123**. Es la contracara del borrado suave de [[project_cleanup_commiteado_por_error]].

Cómo funciona (`cleanup_service.reset_to_fresh_install`): vacía TODAS las tablas
+ dinámicas vía `db_compat.truncate_all_tables` (PG: un `TRUNCATE ... RESTART
IDENTITY CASCADE`, resuelve el ciclo FK assets↔markets; MySQL:
FOREIGN_KEY_CHECKS=0 alrededor; sqlite: DELETE) → `ensure_builtin_data()`
resiembra lo integrado y su reconciliador dropea las sig_/strat_res_ huérfanas →
recrea admin. NO toca `alembic_version` (no re-estampa). UI con doble
confirmación (checkbox + tipear REINICIAR). Corre bajo el lock HEAVY_WRITE
(`_launch_locked`, ya son 3 botones). 906 tests passed.

**Why:** el usuario necesitaba un borrado más profundo que el operativo, para
empezar de cero.

**How to apply:** PENDIENTE VERIFICAR EN RAILWAY (= producción, esta PC no
levanta app/DB): (1) el path PG real `TRUNCATE ... CASCADE` sobre el grafo
completo; (2) los callbacks Dash del modal doble-confirmación; (3) la ventana en
que el wipe trunca `run_lock` mientras seguimos seedeando bajo el lock — mismo
patrón aceptado que `clean_data`, confiar en el heartbeat que re-inserta, pero
observar. Anotarlo en `docs/notes/project_pendientes.md` antes de darlo por
bueno. Ver [[feedback_entorno_verificacion]].
