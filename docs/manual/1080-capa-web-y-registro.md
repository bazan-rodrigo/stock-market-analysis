---
slug: capa-web-y-registro
title: La capa web: pantallas, callbacks y permisos
chapter: Anexo tecnico
order: 1080
roles: admin
---

La UI es Dash montado sobre Flask, con una particularidad que se nota apenas
agregás la primera pantalla: **el auto-discovery de páginas está apagado**. La
app se crea con `use_pages=True` pero `pages_folder=""`, así que Dash no mira
`app/pages/`. Todo se importa a mano desde `create_app()`, en `app/__init__.py`.

Esa decisión, el modelo de autorización y el de visibilidad son las tres cosas
que hay que entender de esta capa, y las tres tienen una consecuencia
contraintuitiva.

## El registro manual y su red de seguridad

Hay dos listas literales en `create_app()`: `_PAGES` con **46 módulos** y
`_CALLBACKS` con otros **46**, que coinciden exactamente con los archivos de
`app/pages/` y `app/callbacks/`. Esos 46 módulos de página producen **47 rutas**,
porque `app/pages/manual.py` llama a `dash.register_page` dos veces: una para
`/manual` y otra, con `__name__ + "_slug"` para evitar la colisión de nombre,
para `/manual/<slug>`.

El precio del registro manual es un error recurrente: crear el archivo no
alcanza, y **sin la línea en `_PAGES` la ruta da 404 en silencio** — pasó con
`/backtest` en julio de 2026. La mitigación no fue volver al auto-discovery sino
`tests/test_module_registration.py`, un meta-test de 2 casos que ni siquiera
importa la app: lee `app/__init__.py` como texto y busca la string
`"app.pages.<nombre>"` para cada archivo del filesystem.

Los dos loops de import usan `importlib.import_module` con un `try/except` que
loguea y hace `raise`. No hay tolerancia a fallos, y es deliberado: **se prefiere
que la app no arranque antes que servir una app a medias**.

La separación páginas/callbacks se respeta al pie de la letra: hay **0
decoradores `@callback` en `app/pages/`**. Las páginas solo definen `layout()`;
la reactividad vive en `app/callbacks/`, con 302 `@callback` a nivel de módulo
(309 contando los de funciones fábrica como `_register_select_all`). El layout
raíz es una función, `serve_layout`, no un árbol estático: se evalúa en cada
carga y decide si incluir la navbar según haya sesión o no.

## Autenticación: un `before_request`, no un decorador por pantalla

La protección de rutas es un único `@server.before_request` con dos whitelists:
`_DASH_INTERNAL_PREFIXES` (`/_dash-`, `/_reload-hash`, `/assets/`) y
`_PUBLIC_PATHS` (`/login`, `/do-login`, `/`). Lo demás sin sesión redirige a
`/login`. La ventaja es que el chequeo es imposible de olvidar en una pantalla
nueva. Lo que se resignó es el rol:

> El endpoint de callbacks de Dash es `/_dash-update-component`, que matchea el
> prefijo `/_dash-` y por lo tanto **no pasa por el chequeo de login**. Tiene que
> estar whitelisteado o la app no funcionaría. La única barrera efectiva de un
> callback es lo que ese callback verifique por su cuenta.

De ahí que el `is_admin` esté repetido a mano: **101 líneas con `is_admin` en 45
archivos** de `app/pages/` y `app/callbacks/`. En páginas es un early-return
dentro de `layout()`; en callbacks, un helper tipo `_require_admin()`.

> `/health` no está en `_PUBLIC_PATHS`: un GET anónimo con el acceso público
> deshabilitado recibe un 302 a `/login` en vez del JSON. Un health check externo
> que espere 200 falla.

El modelo `User` tiene dos roles en un Enum con `name="user_role"`: `admin` y
`analyst`; `is_admin` es una property derivada, no una columna. El login busca
con `db_compat.ci_equals` y no con `==`, para preservar en PostgreSQL el match
case-insensitive que la collation de MySQL daba gratis (ver
[Soportar dos motores de base de datos](/manual/soporte-dual-de-base-de-datos)).

## No hay usuario invitado: login siempre

El modo invitado **se eliminó** (jul-2026). Antes existía un `GuestUser` como
`anonymous_user` de Flask-Login que, con el acceso público habilitado
(`app_settings.public_access`), aparecía autenticado **y como admin** — un
visitante anónimo operaba todas las pantallas de administración. Se quitó
completo: la clase, la pantalla Configuración de app, el servicio del flag
(`app_config_service`) y la tabla `app_settings` (migración 0086).

Hoy el anónimo es el default de Flask-Login (`is_authenticated = False`), así
que el `before_request` de `app/__init__.py` redirige toda ruta no pública al
login. Las únicas rutas públicas son `/login`, `/do-login`, `/` y `/acerca`.

La lógica de visibilidad conserva el manejo de `user_id None` en
`current_viewer()` por robustez (un viewer sin id nunca es dueño de nada), y
las definiciones con `owner_id NULL` que un invitado haya creado en su momento
siguen la regla de siempre: solo un admin las edita.

## Visibilidad: dos ejes ortogonales

`app/services/visibility.py` separa dos cosas que suelen ir juntas:

| Campo | Qué controla | Al publicar |
|---|---|---|
| `owner_id` | La **edición**: dueño o admin; NULL = solo admin | No cambia nunca |
| `is_public` | Solo la **visibilidad** | Es lo único que cambia |

Publicar es compartir, no ceder la propiedad. El código lo respalda: en
`signal_service` el `owner_id` se asigna una sola vez, en la rama de creación; la
rama de edición —donde se toca `is_public`— no lo mira.

Encima va la **regla de referencias** (`can_reference`): una definición pública
solo puede referenciar señales públicas; una privada, públicas más las del mismo
dueño. Sin esto, publicar una estrategia que consume una señal privada expondría
los scores de esa señal sin exponer su definición: una filtración indirecta. No
hay excepción ni para el propio dueño, porque si después se despublicara la
dependencia quedaría rota para los demás. Se cierra por el otro lado también:
**despublicar falla con `ValueError`** si `signal_dependents_of_others` encuentra
dependientes públicos o de otro dueño. No advierte, bloquea el guardado, tanto en
el ABM como en el import de xlsx.

Y el punto que más confunde:

> El pipeline de cálculo **ignora los dos campos y calcula todo**.
> `compute_all_strategies` hace `s.query(Strategy.id).all()` sin filtro alguno: se
> persisten los scores de todas las definiciones, incluidas las privadas de otros
> usuarios. La visibilidad es de definiciones y pantallas, **no de valores**.

Es estructural. El ranking es transversal, así que filtrar al calcular haría que
el resultado dependiera de quién dispara la corrida, y el scheduler corre sin
request context, o sea sin `current_user` (ver
[El motor de cálculo](/manual/motor-de-calculo)). La separación se ve en pares de
funciones gemelas cuyo nombre dice qué camino toma cada llamador:
`get_all_signals()` para el pipeline, `get_visible_signals()` para pantallas y
dropdowns. El segundo compone `visible_filter()`, que devuelve un criterio
SQLAlchemy y no un filtro en Python, para que el descarte lo haga la base.

Al escribir un camino de escritura hay que tener presente que **el filtro de
lectura no autoriza**: siempre se vuelve a llamar `can_edit` sobre el objeto ya
cargado, porque un POST puede traer un id que el usuario nunca vio en pantalla.
Los 39 tests de `tests/test_visibility.py` cubren solo la mitad pura del módulo,
la que no toca ni Flask ni la base. La vista de usuario está en
[Visibilidad y permisos](/manual/visibilidad-y-permisos).

> El default de `is_public` es coherente entre los dos caminos: la columna nace en
> `False` (privada) y `parse_publica(None)` también devuelve `False`, así que una
> señal creada por la UI y la misma importada desde un xlsx sin columna `publica`
> nacen **ambas privadas**. El default público —exponer los packs anteriores a la
> columna sin que quien importa lo decida— era el comportamiento antiguo, ya
> revertido: publicar es siempre un paso explícito.

## El gráfico técnico calcula en el navegador

`app/callbacks/chart_callbacks.py` invierte la arquitectura del resto del
sistema, que es todo pre-calculado: Python solo trae los precios crudos al
cambiar de activo y **todos los indicadores se calculan en el browser**. La razón
es interactividad — mover un slider de período no puede costar un round-trip.

El namespace `window._lwc` no es un archivo en `assets/`: se construye como un
f-string de Python y se pasa como string a `clientside_callback`, por eso las
llaves JS van escapadas. Eso permite interpolar la firma de la función JS desde
el dict `_SLOTS`, así que agregar un indicador es tocar un dict y no sincronizar
a mano la firma con la lista de Inputs. El archivo tiene unas 1.950 líneas / 80
KB y expone **19 funciones**: nueve de indicadores (`sma`, `ema`, `emaW`,
`bollinger`, `rsi`, `macd`, `stochastic`, `drawdown`, `atr`), cuatro de overlays,
más `resample`, `pnfColumns`, `addSeries`, `fullRender`, `simulateTrades` y
`buildSpec`. De los 23 `clientside_callback` de toda la app, 16 están acá.

La semántica del simulador está duplicada a propósito entre
`app/services/trade_simulator.py` y `window._lwc.simulateTrades`, con la regla de
homologación en recuadro en ambos archivos. En realidad son **tres** espejos: el
armado de la spec vive también en `trade_optimizer.spec_from_controls`, y el
contrato entre los tres es el **orden posicional de los 27 controles** de
`_SIM_CONTROL_IDS`. Un control insertado en el medio rompe silenciosamente a los
otros dos (ver [El simulador de trades](/manual/simulador-de-trades)).

> **Ningún test ejecuta el JavaScript.** La paridad Python↔JS de
> `tests/test_paridad_grafico.py` (5 tests) se logra reimplementando el JS en
> Python dentro del propio test: si alguien edita `window._lwc.rsi` y no toca
> `_ref_rsi_js`, la suite sigue verde. Ídem `simulateTrades`: los 35 casos de
> `tests/fixtures/trade_simulator_cases.json` solo corren contra Python. La regla
> de homologación es una convención social, no CI.

## Modales ABM y callbacks huérfanos

`app/components/abm.py` genera tabla, modal de formulario y modal de confirmación
de borrado, con ids derivados del prefijo `entity_id`. Lo usan 8 pantallas; el
resto de los ABM arma su layout a mano.

La convención es que **el modal no se cierra ante error de guardado**, para que
el usuario no pierda lo cargado. Se implementa así: el callback que abre el modal
reacciona a `btn-add`, `btn-edit` y `btn-cancel`, pero **nunca a `btn-save`**; el
de save tiene su propio `Output(..., "is_open", allow_duplicate=True)` y devuelve
`False` solo en el camino de éxito, y `no_update` en validación fallida y en
excepción. Por eso hay dos alerts: `{entity_id}-modal-error` adentro del
`ModalBody` para el error, y `{entity_id}-alert` de página para el éxito — si el
error fuera al de página quedaría tapado por el modal abierto.

> `suppress_callback_exceptions=True` es necesario para registrar callbacks de
> páginas que se renderizan bajo demanda, pero esconde los callbacks huérfanos, y
> ya hay dos casos reales. El bloque ABM de `price_sources` en
> `reference_callbacks.py` (44 referencias a ids `price_sources-*`) apunta a
> componentes que la pantalla dejó de renderizar al pasar a vista de tarjetas de
> solo lectura. Y al revés: la pantalla de eventos usa `make_abm_layout`, que
> siempre dibuja "Sel. todos" / "Desel. todos", pero `"events"` no está en el loop
> de `_register_select_all` — esos botones no hacen nada.
> `test_module_registration.py` no atrapa nada de esto: verifica registro de
> módulos, no coherencia de ids. La deuda que queda se lista en
> [Estado actual, límites conocidos y deuda técnica](/manual/estado-y-limites-conocidos).
