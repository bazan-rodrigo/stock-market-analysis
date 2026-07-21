---
name: tablas-por-senal-diseno
description: "IMPLEMENTADO (16-jul-2026, commit 992fe3e) — tabla por señal (sig_{id}) y por estrategia (strat_res_{id}); pendiente verificar en Codespace (migración 0075) y medir; siguiente etapa: paralelización estilo indicadores"
metadata: 
  node_type: memory
  type: project
  originSessionId: 4db31ed2-6727-4196-9e4e-a45306ca9cb0
---

**IMPLEMENTADO 16-jul-2026 (commit `992fe3e`, 504 tests, pusheado).**
Idea del usuario ("¿y si tenemos una tabla por señal, al igual que por
indicador?"), plan presentado y aprobado con "sí"; el usuario decidió NO
esperar la medición de strategy_only ("avanzo con el cambio"). Solución
de RAÍZ al problema del 15-16 jul: la unidad de recálculo no coincidía
con la unidad de almacenamiento (monolíticas signal_value/
strategy_result, DROPEADAS en la migración 0075) → todo recálculo
acotado pagaba borrar-e-insertar en tablas pobladas (3-5× más caro que
en vacías, medido). Ahora recalcular una unidad = TRUNCATE de su tabla +
insertar en vacío; cero contención entre unidades.

**Qué quedó:**
- `app/models/signal_store.py`: sig_{id}/strat_res_{id} por ID INMUTABLE
  (la key es editable y el DDL de MySQL no es transaccional — renombrar
  es metadata puro), PK (date, asset_id) + índice (asset_id, date), sin
  FK (purga explícita). Esquema declarado en código (sin autoload).
- Ciclo de vida: save_* crea la tabla TRAS el commit, delete_* dropea
  TRAS el commit (cada crash deja el lado benigno); borrar señal con
  historia pasó de DELETE cascade de millones de filas a DROP TABLE.
  Reconciliador bidireccional (huérfana→drop, definición sin tabla→crear
  vacía) corre EN CADA ARRANQUE (startup_service) + ensure(checkfirst)
  en todos los accesos. Tests: test_signal_store_lifecycle.py.
- Backfill: whole_history → TRUNCATE por tabla del alcance (también
  señal/estrategia suelta); con horizonte → delete_by_ranges por tabla;
  strategy_only = TRUNCATE strat_res_{id} + lee las sig_{id};
  group_signal_value/group_scores siguen monolíticas (chicas, ventanas
  alcanzan). Escritor asíncrono sigue ÚNICO (a propósito).
- Migración 0075 COPIA la historia (INSERT…SELECT hacia vacías) — sin
  recálculo obligatorio; downgrade simétrico.
- OJO sqlite tests: los ids se REUSAN tras borrar definiciones → los
  fixtures dropean sig_%/strat_res_% entre tests (_drop_dynamic).

**PENDIENTE CODESPACE: pull + `alembic upgrade head` (0074+0075, la
copia tarda minutos) + reiniciar; medir recálculo de una estrategia
(con/sin "Incluir señales") y de una señal suelta.**

**MEDICIONES REALES (16-17 jul, Codespace):** completo 12min → **6m18s**;
estrategia con señales 5m10s / 1m53s (∝ señales que usa — el filtro NO
reduce el cálculo de señales, por diseño); strategy_only **3m00s** con
desglose de la instrumentación (commit `5f23915`, sale en el panel):
**lectura 158s / cómputo 19s / espera escritor 0s** → READ-BOUND.
Escritores paralelos DESCARTADOS con datos (espera 0s). Implementado en
cambio (commit `6d4c676`, elegido por el usuario): **lectores paralelos
por tabla** — pool de 8 threads, fan-out único por chunk, sesión propia
por thread limpiada por task; activo en MySQL y PostgreSQL vía db_compat
(integrado con las fases duales de la otra sesión), sqlite inline.
**LECCIÓN MEDIDA (17-jul): sobre-paralelización con 8 lectores.** La
corrida CON señales pasó de 5m10s a 6m50s: en el Codespace (2 vCPU) los
8 lectores le sacaban CPU/disco al PROPIO servidor MariaDB mientras
insertaba — desglose: lectura 143s / cómputo 89s / espera al escritor
178s / escritura solapada 406s (+30%). En la era densa (post-1995, casi
todo el dato) la lectura es ancho de banda del servidor: más streams no
aceleran, solo compiten con las inserciones (en la era rala sí volaban:
12s hasta 1996). Fix `20a82c4`: _READ_WORKERS 8 → 3. **PENDIENTE:
re-medir AMBOS modos (con/sin señales) con 3 lectores**; si conviene,
hacerlo configurable en conf.properties para tunear en producción (más
cores). El panel de señales muestra filas por etapa con segundos vivos
+ desglose final (commits `bcaafb2` `75ff3c4` `20a82c4`). ProcessPool
sigue como palanca del cómputo (89s con señales — no urge). Ver
[[project_processpool_particion_activos]], [[project_postgresql_migracion]].
