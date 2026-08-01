---
name: project-ia-mcp
description: "Capacidades de IA con cuenta propia del usuario — arquitectura decidida (MCP, sin panel in-app), hallazgos del código y qué queda pendiente"
metadata: 
  node_type: memory
  type: project
  originSessionId: 022a1659-e3a1-43ba-8580-b5a5499c6b9f
  modified: 2026-08-01T18:10:04.244Z
---

Análisis del **1-ago-2026** (solo diseño, sin código). Objetivo del usuario: que
cada usuario conecte **su propia cuenta** de IA (Claude/ChatGPT/compatibles)
para consultar en lenguaje natural todo lo de la plataforma y además diseñar,
inyectar, backtestear y mejorar señales y estrategias — **sin mover la lógica
cuantitativa fuera de la app**.

**DECIDIDO por el usuario:**
- **MCP con el cliente del usuario.** El **panel in-app queda descartado por
  ahora** — era el único camino que obligaba a custodiar credenciales, y por
  MCP la clave nunca toca la plataforma. Revisar recién si se ve que los
  usuarios reales no tienen cliente MCP.
- **Servicio aparte en Railway** (mismo repo, mismo `DATABASE_URL`, otro start
  command; no llama a `create_app()`), no un blueprint dentro del web.
- **Todos los roles** pueden conectar su cuenta → el gate de visibilidad es LA
  funcionalidad crítica, no una precaución.
- **Escritura solo por packs** (`validate_pack` → `preview_pack` → confirmación
  humana → `import_pack`), nunca INSERT directo. Ver [[project-packs-estandar]]:
  el contrato ya está pensado para que lo escriba un modelo, así que el 80%
  estaba construido.

**Hallazgos del código que condicionan el diseño (verificados, no supuestos):**
1. **El control de acceso vive en la UI, no en los servicios** — 101 usos de
   `current_viewer()`/`get_visible_*` en callbacks/pages, y `current_viewer`
   depende de `flask_login.current_user`, **que no existe fuera de un request**.
   `data_explorer_service.fetch()` no filtra nada (el gate es que la pantalla
   sea admin-only). Cualquier superficie nueva **re-implementa el gate; no lo
   hereda**. Es el mayor riesgo de corrección del proyecto.
2. **El proceso web tiene estado en memoria y 1 worker** (consola SQL guarda
   conexiones en un dict de módulo; progreso de corridas en threads) → agregar
   workers no es gratis, y por eso el servicio va aparte.
3. **Backtest y "basura en la base"** (preocupación explícita del usuario):
   niveles **B (reglas) y C (cartera) YA son efímeros** — computan y devuelven,
   `save_portfolio_run` es una función separada. Solo el **nivel A persiste**
   (`BacktestRun` + `BacktestIcPoint` por fecha×horizonte + `BacktestQuantileStat`),
   y su cómputo arma las filas en memoria y recién al final hace `s.add_all` →
   separar cómputo de escritura es un refactor chico.
   **Pero el problema real NO son los runs**: los tres motores leen por
   `read_strat_table()`, y **backtestear exige materializar la estrategia +
   correr el backfill real en producción**. Iterar variantes con IA deja
   esquema y corridas, no filas.
   **OJO (corregido el 1-ago, el usuario dudó y tenía razón): las
   `sig_{id}`/`strat_res_{id}` YA NO EXISTEN** — cutover hecho, flag
   `USE_WIDE_SIGNAL_TABLES` default **ON**, dropeadas por la 0094. Hoy es
   `signal_values_wide` (col `sig_{id}`) + `strategy_results_wide` (cols
   `strat_{id}_score`/`_pct`). Los motores no se enteran (la subquery es
   equivalente), **pero materializar pasó de `CREATE TABLE` a `ALTER TABLE ADD
   COLUMN` sobre una tabla compartida y viva** — DDL con lock sobre lo que usa
   todo el pipeline, y en PG el `DROP COLUMN` deja la columna muerta hasta un
   rewrite. Ensuciar ahora es ensuciar el ESQUEMA, no dejar tablas descartables:
   refuerza la salida conservadora y encarece un "espacio de borradores".
   Salida elegida: la IA backtestea **solo estrategias que ya existen**; para
   las nuevas entrega el pack y el humano decide. Ver [[project-sig-wide-tables]].
4. No hay ninguna API HTTP hoy (solo `/login`, `/do-login`, `/logout`, `/health`).

**Arquitectura acordada:** una sola capa de capacidades (`app/ai/`: registro de
herramientas tipadas + identidad + topes + allowlist) sobre `app/services/*`
intactos; el servidor MCP es un adaptador delgado encima. Herramientas escritas
UNA vez. Tokens personales hasheados con scopes (`read`/`write:packs`/`run:jobs`),
diseñado para sumar OAuth después. Topes de filas mucho menores que los de la UI
(`MAX_ROWS=5000` es una barbaridad para el contexto de un modelo). Sin SQL libre.
Todo job pesado toma el `run_lock` con `op` prefijado `ai:` y queda en la
bitácora. Nada destructivo entra al registro (lista negra con test).

**DECIDIDO E IMPLEMENTADO el 1-ago (commit f9337ca, 1277 passed):**
- **Ninguna IA escribe señales, ni la de un admin.** Se crean solo por la
  pantalla (alta manual o import). Cualquier IA VE la definición completa y
  puede recomendar cambios; aplicarlos es un acto humano. El gate es por ROL
  (no por propiedad) en los CUATRO caminos, vía `require_signal_admin`; ojo que
  `import_signal_rows` **no pasa por `save_signal`** (escribe directo) y era la
  puerta lateral. El default de `acting_is_admin` se invirtió a `False`.
- **Peso de componente con SIGNO** (divisor Σ|peso|). Es la pieza que hace que
  el catálogo curado no sea una limitación: una señal "al revés" se usa con
  peso negativo, sin duplicarla ni gastar una columna.
- Consecuencia grande para este proyecto: **el backtest efímero se abarató
  mucho**. El paso caro era evaluar señales nuevas desde los indicadores sobre
  toda la historia; como la IA ya no puede crear señales, ese paso DESAPARECE y
  solo queda la capa de estrategia (leer columnas de señal → filtro → ponderar
  → rankear), que es la mitad barata.

**Persistencia del backtest, medido en el código:** nivel A (cuantiles)
persiste SIEMPRE como efecto secundario de correr (`backtest_run` +
`backtest_quantile_stat` + `backtest_ic_point`, esta última fechas×horizontes);
**B (reglas) y C (cartera) NO persisten** — en C `save_portfolio_run` es una
función SEPARADA; walk-forward tampoco. Recomendación acordada: alinear A con
el patrón que el repo ya usa en C (computar y devolver / guardar aparte), y así
el modo IA sale gratis sin ruta paralela. Falta retención por antigüedad en
`backtest_run`/`portfolio_run` (precedente: `run_history_service.prune_old`).

**Carteras = el terreno barato para la IA.** `portfolio` + `portfolio_member`
son filas planas: sin ALTER TABLE, sin backfill, borrado limpio por CASCADE, y
`run_portfolio_backtest`/`curated_equity_series` no persisten. Las CURADAS solo
dependen de precios; las derivadas de estrategia heredan todos los costos de la
estrategia. Advertencia dada al usuario: una IA optimizando pesos contra la
curva histórica sobreajusta — toda optimización de cartera por IA debe pasar por
`walk_forward` y reportar out-of-sample.

**FASE 1a HECHA (commit 9f82d12, 1376 passed): la capa de capacidades, sin
transporte.** Se partió la fase 1 en dos y se hizo primero la mitad donde vive
el riesgo — sin dependencias nuevas, sin servicio en Railway, sin red.
- `app/ai/caller.py`: `AiCaller(user_id, is_admin, scopes)` reemplaza a
  `current_viewer()` fuera de Flask. Sin default: que una llamada sin identidad
  no compile es más barato que descubrirla en producción.
- `app/ai/registry.py`: allowlist + scopes + topes. **Tope global 200 filas**
  (los 5000 de `data_explorer` son para una grilla).
- 7 herramientas de lectura: `get_catalog`, `list_signals`, `list_strategies`,
  `strategy_ranking`, `strategy_score_history`, `search_manual`,
  `read_manual_section`. **`get_catalog` filtra por visibilidad** — `build_catalog()`
  enumera TODO porque lo escribió un botón admin-only.
- Trinquetes en `test_ai_registry.py` + los de visibilidad en
  `test_ai_visibilidad.py` (un analista no llega a lo ajeno ni listando ni por
  id, y **el mensaje de error es el mismo exista o no** para que no sea un
  oráculo de enumeración).

**Lección de esa fase:** el bug que apareció NO lo agarró ningún trinquete sino
un smoke test a mano. El nivel del manual se resolvía con
`manual_service.role_of()`, que deduce el rol de un `username` que esta capa no
tiene; con `None` devolvía "invitado" y un analista veía **24 de 73 secciones**.
Falla silenciosa: la llamada funcionaba y devolvía de menos. Moraleja para lo
que viene: los trinquetes cubren forma y permisos, no que el resultado sea el
correcto — hay que ejercitar cada herramienta a mano al menos una vez.

**PENDIENTE — fase 1b:** transporte MCP (`mcp_server.py`), tabla de tokens con
su migración, pantalla para generarlos/revocarlos, servicio aparte en Railway.
Ahí entran una dependencia nueva y la decisión de infra. Después: que la IA arme
y simule **carteras** (filas planas, sin DDL ni backfill; ver la sección de
arriba, y que toda optimización pase por `walk_forward`).

Relacionado: [[project-backtest]], [[feedback-entorno-verificacion]] (Railway es
producción, no hay entorno descartable), [[feedback-reflejar-en-ui-y-spec]].
