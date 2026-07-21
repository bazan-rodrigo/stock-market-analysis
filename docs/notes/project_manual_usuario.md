---
name: project_manual_usuario
description: "Manual de usuario web en /manual — 72 secciones en docs/manual/*.md (60 de usuario + anexo técnico admin), filtrado por rol, con tests que lo atan al código"
metadata: 
  node_type: memory
  type: project
  originSessionId: 87013aa9-b8a1-4676-b6de-fce6bdf7294c
  modified: 2026-07-21T20:48:44.024Z
---

Manual de usuario completo, implementado el 20-jul-2026 (commits 4d673d4,
ccb239f, 3e39514). Cubre las 45 pantallas de la app.

**Arquitectura:** contenido en `docs/manual/*.md` versionado en git, renderizado
como HTML navegable en `/manual` y `/manual/<slug>`. El usuario nunca ve
Markdown. Front-matter propio (`slug/title/chapter/order/roles/page`) parseado a
mano: **no hay PyYAML en requirements y se decidió no agregarlo** por seis
claves.

**Roles jerárquicos** (invitado < analista < admin): `roles: analista` la ven
analistas Y admins. Un `roles:` olvidado deja la sección visible para todos —un
descuido no debe esconder documentación— y el contrapeso es que un rol mal
escrito rompe la suite. El filtro se aplica DOS veces: en el índice y en el
acceso directo por URL.

**Ícono «?» en cada pantalla:** `help_link(slug)` / `page_header(título, slug)`
de `app/components/help.py`, y `make_abm_layout(..., help_slug=...)` para las 7
pantallas ABM. Es un badge de texto con CSS propio, **no Font Awesome**, para no
atarse a la versión de FA que traiga dbc.

**Los tests son la red que mantiene el manual sincronizado** — si se agrega una
pantalla sin documentarla, la suite falla:
- `test_cobertura_de_pantallas`: toda ruta registrada tiene sección con `page:`.
- `test_todo_slug_referenciado_por_una_pantalla_existe`: cubre las TRES formas
  de referenciar (`help_link()`, `page_header()`, `help_slug=`). Ojo: la primera
  versión olvidó `help_slug=` y seis pantallas ABM quedaron sin validar.
- enlaces internos `(/manual/slug)` y enlaces a rutas de la app.

**Al documentar se detectaron 17 bugs/inconsistencias del código.** 13
arreglados en el commit f4fab61 (correlación sobre retornos no precios en Pares
y /scatter, +respeta fechas; evolución-estrategia limpia selección al cambiar;
import eventos alcance=asset exige ticker; ABM eventos permite fin==inicio;
fuente_fundamentales reporta warning; pais_iso resuelve por ISO; cartera pública
no deriva de estrategia privada; import packs sin columna=privado; fundamentales
toma lock HEAVY_WRITE; motivos de salida traducidos; tooltips retornos; texto
walk-forward; /scatter al navbar; leyenda del Mapa 10 regímenes). NO tocados: el
de synthetic (ya lo resolvió otra sesión, 586a006), el piso de ~92 semanas del
RRG (decisión de diseño), y edición masiva→conversiones (toca synthetic de otra
sesión). Ver [[project_pendientes]].

**Verificación adversarial COMPLETA (las 60 secciones, 21-jul):** tres tandas
— cap 7 (48 hallazgos en 11), caps 3-6 (21 en 27, 14 limpias), y resto (74 en
23, 1 limpia; commit 5447096). VALIÓ MUCHO la pena: la doc escrita por agentes
necesita esa segunda pasada, y la escrita por mí también (el "resto" era
mayormente mío). PERO el verificador también alucina: SIEMPRE leer el archivo
real antes de aplicar una corrección. Patrón que funcionó: workflow verificar →
triage → workflow corregir (cada corrector re-verifica contra el código y
rechaza falsos positivos/ya-corregidos).

**El modo INVITADO se ELIMINÓ (5abd63a, 21-jul).** La verificación había
destapado que desde 6c32179 el invitado con acceso público operaba como admin
(veía y editaba todo, incluidas definiciones privadas ajenas); el usuario
decidió quitarlo entero: siempre hay que loguearse con usuario real. Se
borraron GuestUser, la pantalla Configuración de app, app_config_service, el
modelo AppSetting y la tabla app_settings (migración 0086 portable, con
downgrade que espeja la 0034). Sección 820 del manual eliminada; 100/110/220/
800/1080/1090 actualizadas. El nivel `roles: invitado` del front-matter
SOBREVIVE como piso "visible para todos" — es solo un nombre interno, no un
perfil alcanzable (documentado en manual_service). PENDIENTE Codespace:
git pull + alembic upgrade head.

**Lección (20-jul):** al arreglar los 13 bugs de f4fab61 actualicé solo 2 de
las 8 secciones del manual afectadas — la verificación de caps 3-6 encontró
las otras 6 desactualizadas (390, 420, 510, 620, 630, 640) describiendo el
comportamiento pre-fix. **Al tocar código, grepear docs/manual/ por la pantalla
afectada en el MISMO commit** (es la convención del proyecto y ahora está en
CLAUDE.md). Todas las pantallas de esas correcciones quedaron al día en el
commit que siguió a f4fab61.

**ANEXO TÉCNICO (21-jul, b66f18c):** capítulo "Anexo tecnico" para ingenieros
de producto — 12 secciones `roles: admin`, orders 1000-1099, sin `page:`
(arquitectura, stack, modelo de datos, motor, deltas/borrado, concurrencia,
dual-DB, simulador, capa web, deploy, testing, deuda técnica). Convención:
explica el PORQUÉ con mediciones, nombra archivos/funciones (sin números de
línea), conteos volátiles en forma CUALITATIVA (7e24ca2), diagramas ASCII en
bloques ```text (sin lenguaje, highlight.js pinta tokens al azar).

**Auditoría de recorridos end-to-end (21-jul, 85c8aa9):** 10 casos de uso
auditados contra el manual; 7 completos, 3 cosidos en ese commit (200 era hub
sin enlaces salientes; purga sin efectos transversales; consola-sql sin la
advertencia de ind_*; scheduler sin "falla a mitad"; descarga trimestral vs
ratios diarios). De la auditoría salió un bug real de código: borrar un activo
componente de un sintético destripaba la historia antes del rechazo de la FK
RESTRICT — arreglado con guardia previa en purge_assets (1114724,
test_purge_componente.py).

**Método que funcionó:** agentes en paralelo, uno por pantalla, con instrucción
de leer el código real (página + callbacks + servicio) y prohibición explícita
de mencionar archivos .py / tablas / IDs de componentes. Se les pasó
`310-analisis-de-activo.md` como referencia obligatoria de voz. Los tooltips ya
escritos en `asset_analysis.py` y el `FORMULA_HELP` de `ui_constants.py` son
material de primera para redactar: ya están aprobados por el usuario.
