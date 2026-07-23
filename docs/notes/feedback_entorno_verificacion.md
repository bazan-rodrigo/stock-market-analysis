---
name: entorno-de-verificacion
description: "El Codespace ya no se usa (jul-2026) — la verificación contra la app viva es directo en Railway, o sea producción; no hay entorno descartable"
metadata: 
  node_type: memory
  type: feedback
  originSessionId: ce2c92a6-5815-4c2c-b0c9-690aac8c1b76
  modified: 2026-07-23T01:44:39.197Z
---

**El GitHub Codespace ya NO se usa.** Desde el 22-jul-2026 el usuario lo
confirmó explícitamente: la única base y el único entorno donde corre la app
es **Railway (PostgreSQL)**. No proponer `git pull` en el Codespace, ni
`sudo service postgresql start`, ni "probalo en el Codespace primero".

**Matiz importante (23-jul):** "no se usa" ≠ "se elimina". El usuario aclaró
que **mantiene la posibilidad del Codespace a propósito**, igual que la de
MySQL, "por cualquier cosa que pase en el futuro". O sea: no proponerlo como
lugar donde verificar, pero **tampoco borrar su configuración** ni tratar el
soporte como muerto. Ver [[feedback-mariadb]].

**Why:** el usuario lo dijo directo ("ya te avisé que no uso más Codespace")
después de que se le sugiriera correr ahí un script de medición. Antes el
Codespace era el entorno intermedio descartable donde se probaba todo lo que
tocaba la app viva; ese escalón desapareció.

**How to apply:** la consecuencia importante no es el nombre del entorno sino
que **ya no hay red de contención entre el push y producción**. Al proponer
cualquier cosa que toque la base real:

- Decir explícitamente que es producción, no un experimento aislado.
- Los scripts de medición que ESCRIBEN (`profile_pool_batch.py`,
  `profile_indicator_delta_real.py`, cualquier `profile_*` con backfill real)
  deben tomar el `run_lock_service.HEAVY_WRITE` igual que el Centro de Datos,
  para no pisar el job diario del scheduler ni una corrida lanzada desde la UI.
- Nunca sugerir `--rebuild` / "recalcular completo" a la ligera: borra y
  recalcula historia real.
- Los pasos de verificación siguen anotándose como pendientes en
  [[pendientes-proxima-sesion]] — pero como pendientes *en Railway*.

Ver también [[feedback-mariadb]] (el motor es PostgreSQL) y
[[project-corridas-proceso-web]] (las corridas del Centro de Datos viven en el
proceso web de Railway, con `--timeout 1800`).
