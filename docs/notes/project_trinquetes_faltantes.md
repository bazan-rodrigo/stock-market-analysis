---
name: project-trinquetes-faltantes
description: "Los cuatro huecos de trinquete que quedaron sin cubrir (1-ago-2026), medidos en el código, con el arreglo propuesto de cada uno"
metadata: 
  node_type: memory
  type: project
  originSessionId: 022a1659-e3a1-43ba-8580-b5a5499c6b9f
  modified: 2026-08-02T16:30:43.736Z
---

Relevado el **1-ago-2026** a pedido del usuario ("los trinquetes sirven para
detectar bugs, ¿dónde faltarían?"). El #2 se implementó ese mismo día
(`test_permisos_fallan_cerrado.py`, commit 4c87edc); **estos cuatro quedaron
como pendientes deliberados** para retomar después del MCP.

**El patrón que explica los cuatro:** un trinquete funciona cuando **deriva**
lo que espera del código, y se pudre cuando **codifica a mano una lista** que
hay que mantener en paralelo. Caso testigo del mismo día: `cleanup_service`
tenía `test_cubre_todos_los_logs` y `test_cubre_snapshots_*` en verde **mientras
la limpieza estaba rota** — enumeran tablas en un `set` escrito a mano y nadie
agregó las anchas cuando aparecieron. En cambio `test_pack_spec.py` sí agarró
un ejemplo JSON inválido, porque parsea el artefacto.

---

### 1. El espejo JS del simulador de trades — EL MÁS GRAVE

CLAUDE.md llama a la homologación "la regla principal del módulo" y **no tiene
red automatizada**. Verificado: `tests/test_trade_simulator.py` corre
`fixtures/trade_simulator_cases.json` contra **Python solamente**;
`chart_callbacks.py:1616` solo tiene un *comentario* que menciona el archivo;
no hay `package.json` ni jest ni intérprete JS en las dependencias.

Una divergencia en `window._lwc.simulateTrades` produce un gráfico que miente
sobre los trades y nada la detecta. Depende enteramente de que la persona se
acuerde de tocar los dos archivos.

**Arreglo:** extraer la función JS del string de Python y correrla con un
intérprete embebido (`dukpy`, `quickjs`) sobre los mismos fixtures. Dependencia
de test, no de producción. Es el más caro de los cuatro.

### 3. Nombres de tablas dropeadas que sobreviven en el código

Nueve referencias vivas a `sig_{id}` / `strat_res_{id}` en docstrings y
comentarios: `asset_service`, `maintenance_service`, `portfolio_backtest_service`,
`rules_backtest_service`, `signal_backfill_range` (y las de `cleanup_service`,
que ahora son deliberadas). Son comentarios, **pero la misma clase de resto sí
fue bug** en `cleanup_service`, donde el nombre viejo estaba en la lógica.

**Arreglo:** un test que grepee el código por nombres de tablas dropeadas por
una migración. Feo pero efectivo — habría encontrado el bug de Limpieza el día
del cutover de la 0094.

### 4. La cobertura de limpieza, derivada en vez de escrita a mano — **CERRADO**

**HECHO el 2-ago-2026, y en el camino aparecieron TRES bugs vivos** que la
predicción de este hueco anticipaba con exactitud. Disparador: el usuario
preguntó si la limpieza dropea las columnas de las tablas anchas (no: vacía
filas, y está bien — `clean_data` preserva las definiciones, así que las
columnas tienen que quedar para que "Recalcular completo" las repueble; quien
sí dropea columnas es el ABM al borrar una definición y `reconcile_wide_columns`
en el arranque). Mirando eso saltó que el **reinicio a fábrica** sí estaba roto:

1. `_fresh_install_wipe` derivaba su alcance de `Base.metadata` + prefijos
   dinámicos → **no vaciaba `signal_values_wide` ni `strategy_results_wide`**
   (no son modelos ORM y no empiezan con `sig_`/`strat_res_`). El botón
   prometía "base como recién instalada" y dejaba adentro los valores de
   señales y los rankings. Exactamente el mismo hueco que la 0094 abrió en
   `clean_data`, arreglado allá y no acá.
2. Por el camino del CLI (`scripts/clean_data.py --reset` importa **solo**
   `cleanup_service`) `Base.metadata` está **vacío**: el reset no vaciaba ni
   `assets`, y el script informaba igual que había reiniciado la base.

**Arreglo aplicado:** el alcance del reset sale ahora del **catálogo**
(`inspect(conn).get_table_names()` menos `_RESET_KEEP_TABLES = {alembic_version}`).
Elimina la clase entera de bug: nada puede quedar afuera y el resultado no
depende de qué módulos estén importados. Dos tests nuevos en
`tests/test_cleanup_service.py`; verificado que **fallan contra el código
viejo**, señalando las dos anchas por nombre. 1585 passed.

**Y el tercer bug, el que el trinquete estaba buscando:** `run_history` (la
tabla del Historial de corridas, 0096) **no estaba ni en el alcance ni
preservada** — nació después de que se escribiera la lista y quedó sin vaciar
sin que nadie lo decidiera. El usuario resolvió **vaciarla**, coherente con el
resto de los registros de corrida que la limpieza ya borra.

**Arreglo de la parte de `clean_data`:** acá enumerar es correcto por diseño (la
limpieza *distingue* qué preserva; el reset no tiene nada que decidir), así que
lo que se derivó es la **verificación**, no la lista. Nuevo `_PRESERVED_TABLES`
en el servicio: dict {tabla: motivo} con las 30 que se conservan a propósito.
El test recorre el esquema REAL (`Base.metadata` + las anchas, que viven fuera
del ORM) y exige que cada tabla esté de un lado o del otro; otro test verifica
que la clasificación sea una partición (sin solapes, sin entradas fantasma, sin
motivos vacíos). No decide nada por vos: **te impide olvidarte de decidir**.
Verificado que muerde (una tabla nueva ficticia y el estado real de ayer con
`run_history` afuera). 1666 passed.

Reflejado en los tres lados como pide CLAUDE.md: `TABLES_INFO` (la pantalla),
`docs/manual/830-limpieza-de-datos.md` y el aviso de `scripts/clean_data.py`.

### 5. El SPEC en prosa

Ya estaba anotado en [[project-packs-estandar]] y sigue vigente:
`test_pack_spec.py` ata las **listas** (fórmulas, operadores, columnas) pero no
la **prosa**, y por eso §1 quedó describiendo un flujo viejo durante 4 días. El
1-ago se le agregó a §8 la regla de que las señales exigen admin, y esa frase
**tampoco tiene quién la verifique**: si mañana se revierte el gate, el SPEC va
a seguir afirmándolo.

---

Relacionado: [[project-ia-mcp]] (la capa de IA es el consumidor que más se
beneficia de estos trinquetes: llama a los servicios desde fuera de un request
Flask, sin `current_user` del que deducir nada).
