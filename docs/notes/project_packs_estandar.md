---
name: packs-estandar-para-ia
description: "26-jul-2026: el armado de señales/estrategias se volvió un estándar publicado (SPEC v1 + catálogo por instalación + validador offline) para que personas y otras IA entreguen packs importables"
metadata: 
  node_type: memory
  type: project
  originSessionId: 7d646682-e734-4c79-b645-f2655c6e3237
  modified: 2026-08-01T02:08:16.958Z
---

El usuario quiso que **modelar señales y estrategias sea un estándar** que
puedan seguir personas y —sobre todo— **otras IA sin acceso al código**, y
entregar packs importables. Implementado el 26-jul-2026 (1050 tests en verde).

**La decisión de diseño clave:** el contrato se parte en dos. Lo **fijo** va
en `strategy_packs/SPEC.md` (formato, las 3 fórmulas, la gramática del árbol
de filtro, qué rechaza el import); lo **variable por instalación** —qué
indicadores existen, qué categorías devuelven, qué sectores/mercados están
cargados— se exporta aparte con el botón **Catálogo** de /admin/signals
(`pack_service.build_catalog`). A una IA se le pasan los dos archivos y
alcanza. Antes esa mitad variable no era publicable de ninguna forma.

**Piezas** (todo nuevo salvo lo marcado):
- `app/services/pack_service.py` — formato, filas normalizadas, validación
  offline (`validate_pack`), catálogo, y la resolución de atributos.
- El import acepta **JSON además de xlsx** en las dos pantallas; los dos
  caminos convergen en filas normalizadas y comparten validación y escritura
  (`import_signal_rows` / `import_strategy_rows`), fijado por un test que
  compara el estado de la base entre ambos.
- **Atributos por nombre**: era la barrera real de portabilidad (el árbol
  guarda ids de FK, distintos en cada base — por eso el pack de pullback dejó
  afuera el filtro por `instrument_type`). Ahora el pack dice "Technology" y
  el import lo resuelve; los ids se siguen aceptando.
- `scripts/validate_pack.py` (sin base, mismos errores que el import + avisos
  de trampas silenciosas) y `scripts/pack_from_json.py` (JSON → las 2
  planillas).
- **Pantalla `/admin/packs`** (27-jul, pedida por el usuario: "la verificación
  tiene que ser por pantalla"): subir un pack lo REVISA sin escribir
  (`preview_pack` = validate_pack contra el catálogo real + impacto: qué crea,
  qué actualiza, de quién es lo que pisa), y recién el botón Importar aplica
  los dos pasos en orden (`import_pack`). Con errores el botón queda
  deshabilitado. Resuelve de paso la pregunta de "¿el mismo JSON lo subo dos
  veces?": por acá, una sola vez.
- `tests/test_pack_spec.py` **ata el SPEC al código**: si aparece una fórmula,
  operador, atributo o columna sin documentar, la suite falla. Además valida
  que los ejemplos del documento sean JSON válido y pasen el validador.
- Manual: sección nueva `packs-de-senales-y-estrategias` (735).

**Endurecido de paso** (cambios de conducta, no solo docs): una señal **sin
`indicator_key` ahora se rechaza** (antes entraba muda y nunca puntuaba), y el
manual decía mal que sin columna `publica` las señales entran públicas —
entran **privadas** desde que se unificó con el default de la UI.

**PENDIENTE verificar en Railway** (esta PC no levanta la app): el botón
Catálogo (es la primera corrida real de `build_catalog` contra PostgreSQL), el
import de un JSON por pantalla, y un pack con filtro por nombre de sector.
Ver [[entorno-verificacion-solo-railway]] y [[pendientes-proxima-sesion]].

---

**31-jul-2026 (19e3bc5, 1209 passed) — el SPEC se había desfasado en 4 días.**
`test_pack_spec.py` seguía verde: ataba las LISTAS (fórmulas, operadores,
atributos, columnas) pero **no las afirmaciones en prosa**, que es donde se
pudrió. Lección para la próxima: un trinquete de enumeraciones no protege lo
que el documento *dice*.

Lo que decía mal, todo introducido por commits POSTERIORES al SPEC:
- **§1 publicaba el flujo viejo** (bajar el catálogo de Señales, importar en
  dos pantallas): `/admin/packs` nació después y el SPEC nunca la mencionó.
- **§8 mentía con el "todo o nada"**: es todo-o-nada *por paso*, y son dos
  transacciones — si las señales entran y la estrategia falla, **las señales
  quedan** (lo dice `import_pack` en su docstring).
- **§6 no tenía tres semánticas** que solo vivían en el manual 730: el tope de
  **45 días** del as-of (`ASOF_MAX_LOOKBACK_DAYS`), que **las señales se leen
  con fecha EXACTA** (no as-of), y el caso aparte de los atributos tras
  616c0b4.

El **README tenía un error, no un hueco**: `publica` ausente = "pública por
compatibilidad". Es **privada** (ver arriba, ya se había arreglado en el
manual y no acá). Caducó también su nota sobre ids de catálogo.

**Los 4 packs ahora están en los dos formatos.** Existían solo como xlsx
aunque el estándar declara el JSON canónico — cero ejemplos del formato que el
SPEC publica. Se hizo con conversor, no a mano: `pack_service.pack_from_rows`
+ `scripts/pack_to_json.py` (lee con las MISMAS funciones del import real).
Round-trip verificado celda por celda: las 8 planillas regeneradas salen
idénticas. Detalle que importa: la conversión **conserva las columnas de más**
(`source`) — tragárselas haría que el pack convertido importe distinto del
original en vez de ser rechazado igual.

Trinquete nuevo para el riesgo que se estrena (dos formatos del mismo pack que
se separan): `test_pack_spec.py` verifica que cada planilla tenga su JSON y
que ambos digan lo mismo. Probado mordiendo, no asumido.
