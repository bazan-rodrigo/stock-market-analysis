---
name: project-trinquetes-faltantes
description: "Relevamiento de huecos de trinquete (1-ago-2026): #2, #3, #4, #5 y #6 CERRADOS (destaparon 4 bugs vivos); queda abierto solo el #1, el espejo JS de simulateTrades"
metadata: 
  node_type: memory
  type: project
  originSessionId: 022a1659-e3a1-43ba-8580-b5a5499c6b9f
  modified: 2026-08-03T02:39:48.010Z
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

### 3. Nombres de tablas dropeadas que sobreviven — **CERRADO (2-ago, da06060)**

**Y destapó un bug vivo, el que este hueco predecía**: `purge_assets` barría la
historia por prefijo (`ind_`, `sig_`, `strat_res_`) más una lista fija, y **las
anchas no caen en ninguna de las dos** — no empiezan con esos prefijos y no
tienen FK a assets (deliberado). Borrar un activo le dejaba los scores y los
rankings adentro **para siempre**, en las dos tablas más grandes de la base. El
docstring de `ensure_wide_signal_tables` afirmaba lo contrario ("purge_assets
limpia estas tablas explícitamente"): el contrato estaba escrito y nunca
implementado. Mismo hueco que la 0094 abrió en `cleanup_service`, en otro
servicio. Arreglado en d384ad0 con `tablas_de_historia_por_activo()`.

**El grep de nombres a secas se evaluó y se DESCARTÓ**: la prosa que explica que
una tabla ya no se usa es legítima y abunda ("group_scores ya no se escribe
acá"), así que el trinquete moriría de ruido en una semana. Lo que se hizo:

1. Nombres muertos **solo en código EJECUTABLE** — literales de string, con los
   docstrings excluidos por construcción vía `ast`. La lista de muertas se
   deriva de las migraciones (dropeadas en algún `upgrade()` que nadie vuelve a
   crear, menos `Base.metadata`). Encontró 6 restos, **dos de ellos texto en
   PANTALLA** nombrando `indicator_values`.
2. **Conciencia de las anchas**: quien usa los accesores per-entidad o barre por
   prefijo tiene que nombrar también las anchas. Esta es la forma exacta del bug
   de `cleanup_service` — y es el chequeo que agarró a `purge_assets`
   (verificado contra el archivo viejo).

Cada chequeo trae su test de que MUERDE. Ojo con el sabor MySQL: el LIKE escapa
el guión bajo (`'sig\_%'`), así que sin normalizar la barra justo la rama que
barre por prefijo se escapaba del control.

### 3-bis. La versión original de este hueco (histórico)

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

### 5. El SPEC en prosa — **CERRADO (2-ago, da06060)**

`tests/test_pack_spec_prosa.py`: cada afirmación normativa se registra **dos
veces** —el texto que tiene que seguir en el documento y el hecho del código que
la vuelve verdad— y se verifica en los **dos sentidos**. Si se revierte el gate
de admin falla el verificador; si alguien reescribe la frase falla el patrón y
hay que volver a registrarla. Siete afirmaciones: divisor Σ|peso|, peso ≠ 0,
peso negativo, señales solo admin, `spec_version: 1`, versión desconocida se
rechaza entera, y composite/`source:group`/`scope` removidos.

**Decisión de diseño a respetar: NO se marcan las frases dentro del SPEC.** Se
evaluó anclarlas con comentarios HTML y se descartó — el SPEC es un documento
**publicado**, que se le entrega a personas y modelos que no ven este repo, y
llenarlo de andamiaje de test lo ensucia para su lector real. El costo aceptado:
cubre lo registrado, **no promete una partición** (a diferencia de
`_PRESERVED_TABLES`, donde enumerar todo sí era posible).


### 6. El inventario de herramientas de IA vs el manual — CERRADO (2-ago)

**Hueco que el relevamiento del 1-ago no vio**, y lo encontró el usuario
preguntando "¿dónde se consulta el catálogo de herramientas de la IA? me parece
que el manual está desactualizado". Lo estaba: describía **8 de 15**
herramientas. Faltaban las dos familias más nuevas y más consecuentes —backtest
y carteras—, así que el usuario no se enteraba de que la IA **corre backtests y
simula carteras**.

**Por qué se escapó:** `test_manual_coverage.py` ata PANTALLAS ↔ manual, y las
herramientas de IA no son pantallas. Quedaban fuera de toda red, y la única
garantía era que la persona se acordara.

**El arreglo tuvo una restricción propia:** el manual no puede enumerar
herramientas por su nombre técnico (lo lee alguien que no programa). Así que el
puente son **familias de capacidad**: cada `@tool` declara `familia=`
(obligatoria, sin default, validada contra `registry.FAMILIAS`) y la sección
Conexión IA declara las suyas en `familias_ia` del front-matter — que no se
muestra al lector. `test_contract_coverage.py` exige que las dos listas
coincidan **en los dos sentidos**: capacidad sin documentar, y capacidad
documentada que ya no existe (peor, porque el usuario la pide y no está).

El `familias_ia` va en el front-matter y no como comentario HTML en el cuerpo:
el cuerpo se renderiza y el comentario podría verse.

---

Relacionado: [[project-ia-mcp]] (la capa de IA es el consumidor que más se
beneficia de estos trinquetes: llama a los servicios desde fuera de un request
Flask, sin `current_user` del que deducir nada).
