---
name: project-postgres-only-estudio
description: "Estudio + plan (22-jul-2026) para retirar el soporte dual y quedarse solo con PostgreSQL — MariaDB CONFIRMADA fuera de uso, se corta; el corte es higiene, la performance está en la cosecha posterior"
metadata: 
  node_type: memory
  type: project
  originSessionId: 26b2a194-5f13-4ef4-8a67-87db3554ba16
  modified: 2026-07-22T12:57:13.512Z
---

**MariaDB ya NO se usa: la única base es PostgreSQL en Railway** (confirmado por
el usuario el 22-jul-2026). Se retira el soporte dual.

Documentos: **`docs/notes/design_postgres_only.md`** (el estudio: beneficio,
pérdida, features PG mapeadas a call sites) y **`docs/notes/plan_corte_pg_only.md`**
(el checklist ejecutable, verificado archivo por archivo). Nada programado aún.

**Orden acordado: 0 (precondiciones en Railway) → A (bugs vivos, 0,5 sesión) →
B (el corte, 1,5-2) → C (esquema PG-only, 1-1,5) → D (cosecha medida, 3-5).**

**Lo más importante de recordar: el corte NO acelera nada por sí solo.** La
performance está en la etapa D (COPY, CLUSTER, fillfactor, LATERAL, UNLOGGED), y
el "3-10x de COPY" es un número de folleto: no está medido acá, y las dos
últimas victorias de perf vinieron de *escribir menos*, no de escribir más
rápido. Ahorro real del corte en código de PRODUCCIÓN: ~130 líneas sobre 44.900
(de ~1.130 totales, ~65% son tests y verificación). **El ahorro grande es otro:
se CANCELA la fase 5 del plan dual** (gate de paridad), que bloqueaba todo desde
el 16-jul y cuyo comparador además estaba roto para tablas anchas.

**Por qué cortar ANTES de cosechar** (contraintuitivo): el seam de escritura
genérico lo exige **sqlite**, no MySQL (`conftest.py:31-46`), así que no se
escribe despacho que después se tire. Lo que justifica el orden es que B es un
refactor inerte sobre el motor vivo (las 10 ramas MySQL son ramas no-tomadas
bajo PG) y que B mata la regla de paridad byte a byte, que es el impuesto de
cada edición de camino caliente en D.

**BUGS VIVOS a arreglar primero (etapa A):**
- **La red de retry está inerte bajo PG**: sin `lock_timeout` (y
  `app/database.py:6-13` crea el engine sin `connect_args`), 55P03 nunca se
  emite → escritor bloqueado **se cuelga en silencio** con el heartbeat de
  `run_lock_service` latiendo, o sea *parece* que corre. **MariaDB era el único
  motor que hacía visible ese escenario: el corte remueve el testigo del bug.**
- `users.username`: en PG conviven 'Admin' y 'admin' y el login usa `.first()`
  sin ORDER BY → autenticación no determinista. Antes de la migración 0088, hay
  que buscar duplicados en Railway o el CREATE UNIQUE INDEX aborta.
- `set_bulk_load_checks` es código muerto en los tres motores; `"1146"` en
  `run_lock_service._MISSING_TABLE_MARKERS` matchea por substring.

**Trampas del corte (las 3 que la suite NO detecta):**
- `signal_backfill_range.py:636` elige una **arquitectura de concurrencia**, no
  SQL: tiene que quedar `is_postgres(s)`, nunca `True` ni `not is_sqlite`.
- `app/config.py:57-61` + `requirements.txt` + `.devcontainer/devcontainer.json`
  (que es quien inyecta el valor efectivo): si no van juntos, la app no arranca
  con `ModuleNotFoundError`.
- Borrar `docs/manual/1060` rompe pytest: 8 capítulos lo enlazan. **Reescribirlo
  conservando el slug**, no borrarlo.

**NO borrar por inercia:** el seam PG↔sqlite entero (esta PC no tiene ningún
driver; sqlite es el motor de la suite), `_dedupe_last` (su docstring dice
"semántica de MySQL" pero protege de un bug real de producción, `946fc6d`),
`_conflict_cols` con su fallback, `is_postgres`.

**Método (repetible):** la v1 del estudio se escribió leyendo `db_compat` + el
diseño dual, y se verificó DESPUÉS con 8 agentes contra el código. La
verificación encontró una **cita truncada que invertía el argumento central**
(el diseño dual decía que las ventajas PG "se posponen **o van detrás del mismo
despacho**", y yo cité solo "se posponen"), 3 afirmaciones falsas y ~20
imprecisiones. Lección: un estudio de arquitectura escrito sobre documentación
previa hereda sus recortes — verificar las citas contra la fuente antes de
construir encima.

Relacionado: [[project-postgresql-migracion]], [[project-scaling-target]],
[[project-ind-wide-tables]], [[project-pendientes]].
