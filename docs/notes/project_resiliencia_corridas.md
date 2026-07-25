---
name: project_resiliencia_corridas
description: "Resiliencia/monitoreo ante corte de contenedor a mitad de corrida — bug del rebuild ARREGLADO (R1), atomicidad total y monitoreo DIFERIDOS"
metadata: 
  node_type: memory
  type: project
  originSessionId: 4765a9e3-e13f-4763-b396-6ee2e289a3c6
  modified: 2026-07-25T14:18:23.419Z
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
- **Monitoreo:** el historial de corridas vive EN MEMORIA
  (`write_stats_service._runs` deque(20) + `_state` del Centro de Datos) → se
  pierde con el proceso; hoy no queda rastro consultable de que una corrida se
  cortó (solo los logs de Railway). Opciones NO hechas: **M1** tabla
  `run_history` persistida (op/alcance/inicio/fin/estado ok·error·abortada);
  **M2/R3** marcar "abortada" al detectar lock stale al arranque (hoy
  `run_lock_service.clear_stale` en `app/__init__.py` solo loguea y sigue);
  **M3** chequeo de cobertura (fechas de precios vs fechas evaluadas por
  estrategia) como detector independiente de huecos. `verification_service`
  verifica INDICADORES, no cobertura de fechas de señales.

**Nota operativa:** durante esta sesión había otra SESIÓN EN PARALELO activa
editando `cleanup_service`/`clean_data`/`admin_cleanup` (feature "reset to fresh
install") — los archivos de señales cambiaron bajo los pies (commit 1d5e2e8
removió `group_signal_value` del camino de rango). Refuerza el aviso de CLAUDE.md:
no `git add -A`, verificar el estado en disco antes de editar. Ver
[[project_pendientes]], [[feedback_entorno_verificacion]],
[[project_corridas_proceso_web]].
