---
name: project-ia-mcp
description: "Capacidades de IA con cuenta propia del usuario — arquitectura decidida (MCP, sin panel in-app), hallazgos del código y qué queda pendiente"
metadata: 
  node_type: memory
  type: project
  originSessionId: 022a1659-e3a1-43ba-8580-b5a5499c6b9f
  modified: 2026-08-02T05:42:10.358Z
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

**LA LECCIÓN QUE SE REPITIÓ TRES VECES EN LA MISMA SESIÓN** — los tres bugs
reales los encontró **ejercitar el sistema a mano**, no los trinquetes, y los
tres fallaban en silencio (la llamada funcionaba y devolvía de menos):
1. El nivel del manual se resolvía con `manual_service.role_of()`, que deduce
   el rol de un `username` que esta capa no tiene; con `None` devolvía
   "invitado" y un analista veía **24 de 73 secciones**.
2. `MCP_PUBLIC_URL` sin esquema (ver abajo).
3. El verificador de tokens solo conocía el token directo, así que el recurso
   **rechazaba los tokens que emitía nuestro propio OAuth**. El flujo entero
   andaba y emitía tokens válidos: cada mitad funcionaba por separado.

Los trinquetes cubren forma y permisos, **no que el resultado sea el correcto**.
Los tres arreglos se movieron a `app/ai/` (no al caparazón) para que quedaran
cubiertos. Regla para lo que venga: ejercitar cada herramienta a mano al menos
una vez, y todo lo que pueda equivocarse va donde la suite lo vea.

**AUTENTICACIÓN HECHA (commit 43795e9, 1396 passed).** El usuario preguntó
"¿qué tabla de token? no quiero guardar credenciales de IA" — la confusión vale
anotarla porque va a volver: **son dos credenciales distintas.** La del
proveedor de IA se queda en el cliente y la app nunca la ve (eso es lo que se
decidió no guardar). El token es la identidad del USUARIO ante el servidor MCP,
equivalente a su contraseña, y sin él el gate de visibilidad no se puede aplicar
— las únicas alternativas eran un servidor público donde cualquiera lee lo
privado de todos, o no tener MCP.
- **Se reusó `users`** (decisión del usuario) en vez de tabla nueva: migración
  **0099** agrega `mcp_token_hash` (sha-256 hex, índice único) y
  `mcp_token_created_at`. Revocar = NULL.
- **SHA-256 y NO bcrypt**, a diferencia de `password_hash`: una contraseña es
  adivinable y conviene que verificarla sea lenta; un token de 256 bits no. Y
  bcrypt saltea, así que no permitiría BUSCAR por hash — habría que traer todos
  los usuarios y comparar uno por uno en cada llamada.
- `app/ai/tokens.py` + pantalla **«Conexión IA» (`/ia`)**, todos los roles, en el
  menú del usuario. El token en claro se muestra UNA vez.
- Un usuario desactivado no resuelve: dar de baja corta también su IA.

**PENDIENTE en Railway: `alembic upgrade head` (0099) + verificar la pantalla
viva.** Esta PC no levanta la app (falta `yfinance`), así que el layout no se
ejercitó; los callbacks sí se validaron importando el módulo (Dash rechaza al
importar los outputs duplicados). Ojo: `test_module_registration` solo mira el
TEXTO del código, no importa los módulos — no habría detectado un conflicto.

**TRANSPORTE HECHO (dac9287 + 9f8734e, 1424 passed). El MCP está COMPLETO.**
- `app/ai/mcp_adapter.py` — traducción y errores, **sin importar el SDK a
  propósito** (no está en la PC de desarrollo, como `yfinance`): así todo lo
  que se puede equivocar queda cubierto por la suite.
- `mcp_server.py` — caparazón. Servicio APARTE (proceso `mcp` del Procfile),
  no dentro de `web`, por el worker único de gunicorn con `--timeout 1800`.
- **Se instaló el SDK (`mcp` 2.0.0) en el venv para verificar en serio**, y
  apareció una diferencia con la documentación que habría roto el deploy: el
  `Server` de bajo nivel **NO toma `token_verifier` en el constructor** — va en
  `streamable_http_app()`. También: `Tool` acepta `inputSchema` por alias.
- **Verificado de punta a punta** levantando uvicorn contra sqlite sembrada y
  hablándole como cliente MCP: 7 herramientas, `list_strategies` devolvió **1
  de 2** estrategias (solo la pública), token inválido rechazado. El gate de
  visibilidad atraviesa el transporte.
- Auth por el `TokenVerifier` del SDK (no leyendo el header a mano); el rol
  viaja en `claims` para no reconsultar la base por herramienta.
- **`Session.remove()` después de cada llamada Y de cada verificación**: sin eso
  queda una transacción abierta por request y en PG se fija el xmin horizon.
- **`MCP_PUBLIC_URL` no es cosmético**: el SDK trae protección contra DNS
  rebinding y por defecto **solo acepta localhost** → sin esa variable Railway
  devuelve error a todo.

**FUNCIONANDO EN PRODUCCIÓN (1-ago-2026).** El usuario conectó el conector
desde la app de Claude y le respondió una consulta real sobre el catálogo. Es
el cierre del pendiente más grande: hasta ese momento todo lo de IA era código
sin verificar contra la app viva. Servicio `mcp` en Railway (start command
`uvicorn mcp_server:app --host 0.0.0.0 --port $PORT`), `DATABASE_URL` +
`MCP_PUBLIC_URL`, dominio propio, migraciones 0099 y 0100 aplicadas.

**DOS TROPIEZOS DEL DEPLOY, los dos por mi lado:**
1. `MCP_PUBLIC_URL` sin esquema tiraba abajo el contenedor. Railway entrega el
   dominio PELADO y es lo que uno pega; `AnyHttpUrl` lo rechaza con un
   traceback que no menciona que falta el `https://`. Arreglado normalizando
   (3b9b584) — y el arreglo se movió a `mcp_adapter`, que la suite sí ve.
2. **El conector remoto NO acepta un token pegado a mano**: hace registro
   dinámico de cliente y exige OAuth. Falló con "no se pudo registrar con el
   servicio de inicio de sesión". Hubo que implementar el servidor OAuth
   completo (396dbc6, migración 0100) — ver abajo.

**OAUTH (396dbc6):** la identidad de fondo NO cambió — la página de
autorización pide el **token de «Conexión IA»**, no una contraseña, así que el
servicio MCP nunca ve una y hay UN solo lugar para cortar el acceso (revocar el
token mata las sesiones OAuth porque `load_access_token` lo revalida en cada
llamada). Códigos de un solo uso de 60s, refresh rotativo, sin ampliación de
scopes al renovar, todo hasheado, purga al arrancar. PKCE lo valida el SDK.

**BACKTEST HECHO Y ANDANDO EN PRODUCCIÓN (2-ago).** 11 herramientas, cuatro de
backtest. Verificado por el usuario contra Railway.
- **Se separó computar de persistir** en `backtest_service`
  (`compute_backtest` / `save_backtest_run` / `run_backtest` sin cambios para
  la UI). No es un patrón nuevo: los niveles B y C ya lo hacían. Ojo:
  `run_backtest` NO es `save(compute(...))` — crea el run ANTES de computar para
  que un backtest que falla quede con `status='error'` visible.
- `run_backtest_preview` corre **sin guardar**; `backtest_strategy_variant`
  prueba otros pesos/componentes **sin materializar nada**. Persistir no está
  restringido: la herramienta no existe (+ lista negra en el trinquete).
- **La variante hereda la elegibilidad de la base**: los pares (fecha, activo)
  que la base tiene puntuados YA codifican su filtro. Sale gratis, es fiel, y
  aísla el efecto de los componentes. Sirve para pesos/componentes, NO filtro.
- El motor se partió en etapas (`leer_scores` / `_retornos_forward` /
  `_por_fecha` / `_agregar`) para que base y variante compartan **un solo panel
  de precios** — la parte cara se paga una vez.
- **Estabilidad por tramos** en la respuesta: el IC medio es in-sample y con
  muchas variantes está inflado. Partirlo hace visible el caso
  `0,40/0,01/0,01/0,01` (promedia 0,11 y no hay señal, hay un tramo con suerte).
  La guía de lectura viaja DENTRO de la respuesta: quien interpreta es el modelo.
- Retención `prune_old(180d)` al arrancar.

**DOS BUGS DE PRODUCCIÓN QUE DESTAPÓ, ninguno de la capa de IA:**
1. **Fechas**: la config guarda ISO y se comparaba contra la columna `date`.
   sqlite coerciona, PostgreSQL no (`operator does not exist: date >= character
   varying`). **La pantalla de Backtest tenía el mismo bug**: cualquiera que
   completara «desde» lo pegaba. Arreglado con `a_fecha()`.
   El test mira la EXPRESIÓN de SQLAlchemy y no el SQL ejecutado: el driver de
   sqlite convierte los `date` a texto antes de bindear, así que a nivel de
   cursor los dos casos se ven iguales y el test habría pasado siempre.
2. `list_strategies` devolvía los componentes con `signal_id` interno mientras
   `list_signals` identifica por `key`: **no se podían cruzar**. Lo encontró una
   pregunta del usuario, no un test.

**PENDIENTE — el único dato que falta: CUÁNTO TARDA** `run_backtest_preview`
sobre la historia completa. No se puede medir en la PC de desarrollo. Si tarda
minutos, el conector corta por timeout y hay que convertirlo en job asíncrono.

**CARTERAS HECHAS Y ANDANDO (2-ago, 9794f76).** 14 herramientas en total.
`list_portfolios`, `get_portfolio_performance` y `simulate_portfolio` — esta
última toma tickers+pesos y devuelve los KPIs **sin crear nada**. Se extrajo
`curated_equity_from_members()` de `curated_equity_series()`: lo único atado a
la base era `resolve_membership`. Pesos normalizados solos; sin pesos,
equiponderada.
- **El sobreajuste es MAYOR acá** que en señales: optimizar pesos contra una
  curva histórica es literalmente ajustar parámetros a datos pasados. Por eso
  los KPIs vienen **por tramo, reescalados a 1 en cada uno** — si arrastraran
  el nivel acumulado todos parecerían crecientes y el desglose no serviría
  (hay test). La guía de lectura viaja dentro de la respuesta.

**BUG PROPIO QUE SHIPEÉ Y NO VI:** le puse `title=` a un `dbc.Input` en el
commit del peso con signo; dbc 2.x lo rechaza con TypeError y, como se arma
dentro de un callback, **el modal de Estrategias mostraba la lista de
componentes VACÍA** — una estrategia con 4 señales se veía sin ninguna. Lo
arregló una sesión paralela. Ver [[project-render-dash-sin-red]]: la suite es
toda lógica pura y **nunca construye un componente Dash**, así que esa clase
entera de bug no tiene red.

**OJO — HAY SESIONES EN PARALELO en este repo.** Aparecieron cambios sin
commitear que no eran míos (el arreglo del modal, una reescritura de
`_fresh_install_wipe`). Commitear solo los archivos propios, nunca `git add -A`.

Relacionado: [[project-backtest]], [[feedback-entorno-verificacion]] (Railway es
producción, no hay entorno descartable), [[feedback-reflejar-en-ui-y-spec]].
