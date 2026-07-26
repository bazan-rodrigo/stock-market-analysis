---
name: project_resiliencia_corridas
description: "Resiliencia/monitoreo ante corte de contenedor a mitad de corrida — bug del rebuild ARREGLADO (R1) y monitoreo M1+M2 HECHOS (run_history); atomicidad total y M3 DIFERIDOS"
metadata: 
  node_type: memory
  type: project
  originSessionId: 4765a9e3-e13f-4763-b396-6ee2e289a3c6
  modified: 2026-07-26T18:35:14.797Z
---

25-jul: evaluación de **resiliencia y monitoreo** ante un corte de contenedor
(Railway o cualquier contenedor: se puede reemplazar sin aviso, no solo en
deploy) a mitad de una corrida.

**Bug REAL encontrado y ARREGLADO (opción "R1", el toque en la tabla de log):**
el rebuild ("Recalcular completo") de señales/estrategias interrumpido dejaba un
**hueco permanente y silencioso**. `_initial_cleanup` en
`app/services/signal_backfill_range.py` vaciaba las tablas del alcance pero
PRESERVABA `signal_eval_log` (comentario viejo: "signal_eval_log NO se toca"),
así que las fechas ya vaciadas pero no reescritas quedaban marcadas como
evaluadas → el delta las tomaba por hechas y NO las reparaba. Fix: borrar los
markers del alcance `(eval_kind, eval_ref)` en la limpieza inicial + re-marcar
SIEMPRE en `force` (`if force or d not in logged`). Invariante nuevo: marcado ⇔
escrito. Test de regresión `test_rebuild_interrumpido_no_deja_markers_de_fechas_no_escritas`
en `tests/test_signal_range_parity.py` (simula el corte fallando `_load_sweep`
pasado el primer chunk; falla en el código viejo, pasa con el fix). **907 passed.
NO verificado en Railway todavía — es producción** (dejar como pendiente).

**Contexto que acota el bug:** el DELTA normal NO lo tiene (cada fecha es
DELETE+INSERT atómico por fecha; los indicadores son atómicos por-activo, un
activo incompleto lo completa el próximo delta). Solo pega en el rebuild sobre
historia YA evaluada + corte a mitad (= el flujo real "edité la fórmula y aprí
Recalcular completo").

**DIFERIDO por el usuario:**
- **Atomicidad total (build-and-swap):** R1 hace el hueco REPARABLE pero NO
  elimina el estado transitorio "parte vieja / parte nueva" MIENTRAS corre el
  rebuild. Para "nunca mezclado ni un instante" haría falta construir en tabla
  sombra `sig_{id}`/`strat_res_{id}` y hacer swap atómico al final (RENAME en
  MySQL / DROP+RENAME transaccional en PG, vía `db_compat`; readers ven la vieja
  completa hasta el flip). Arruga: `group_scores`/tablas compartidas no se
  swappean por-id, y disco transitorio 2x. El usuario priorizó cerrar el hueco,
  no la atomicidad total.
- **Monitoreo M1+M2 — HECHOS (26-jul, commit 7663e75 pusheado, migración 0096,
  936 passed).** Antes el historial vivía EN MEMORIA (`write_stats_service._runs`
  deque(20) + `_state`) → se perdía con el proceso. Ahora: tabla `run_history`
  (`app/models/run_history.py` + `run_history_service.py`, best-effort/fail-open
  con latch como run_lock). **M1**: `start_run`/`finish_run` cableados en
  `data_center_callbacks._run` y `scheduler._daily_update_job` → cada corrida deja
  fila durable (op/scope/estado running·ok·error·aborted/tiempos/total·ok/first_error);
  UI = sección "Historial de corridas" en el reporte del Centro de Datos (reusa
  `dc-writes-report`, abortadas resaltadas). **M2**: `abort_orphans()` al arranque
  (en `app/__init__.py`, junto a `clear_stale`) marca 'aborted' toda fila 'running'
  remanente (proceso que murió; supone 1 worker); `prune_old()` poda a 180 días.
  Aviso: la suite (pura) NO importa `data_center_callbacks`/`scheduler`/`create_app`
  → esos call sites se verificaron por smoke import, solo el servicio tiene tests
  (7). **PENDIENTE: `alembic upgrade head` en Railway** (hasta entonces el servicio
  corre en fail-open y no registra; no rompe).
- **Monitoreo M3 — DIFERIDO:** chequeo de cobertura (fechas de precios vs fechas
  evaluadas por estrategia) como detector independiente de huecos.
  `verification_service` verifica INDICADORES, no cobertura de fechas de señales.
  Detectaría el síntoma del bug del rebuild aunque el registro de corridas fallara.

**Nota operativa:** durante esta sesión había otra SESIÓN EN PARALELO activa
editando `cleanup_service`/`clean_data`/`admin_cleanup` (feature "reset to fresh
install") — los archivos de señales cambiaron bajo los pies (commit 1d5e2e8
removió `group_signal_value` del camino de rango). Refuerza el aviso de CLAUDE.md:
no `git add -A`, verificar el estado en disco antes de editar. Ver
[[project_pendientes]], [[feedback_entorno_verificacion]],
[[project_corridas_proceso_web]].
