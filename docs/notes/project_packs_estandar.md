---
name: packs-estandar-para-ia
description: "26-jul-2026: el armado de señales/estrategias se volvió un estándar publicado (SPEC v1 + catálogo por instalación + validador offline) para que personas y otras IA entreguen packs importables"
metadata: 
  node_type: memory
  type: project
  originSessionId: 7d646682-e734-4c79-b645-f2655c6e3237
  modified: 2026-07-27T02:07:05.218Z
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
