---
name: entregar-estrategias-como-import-files
description: "Cuando el usuario pide una estrategia de trading, entregarla como un pack JSON validado (formato estándar), no como instrucciones manuales"
metadata: 
  node_type: memory
  type: feedback
  originSessionId: 44667c57-b1c8-440a-b3df-63205dec6695
  modified: 2026-07-27T02:06:45.985Z
---

Cuando el usuario pide una estrategia de trading para probar, generarle el
**pack** en `strategy_packs/` del repo (no darle pasos para crearla a mano en
la UI).

**Why:** lo pidió explícitamente (12-jul-2026): "cuando te pido estrategias
me das los files y no los tengo que crear a mano".

**How to apply:** desde el 26-jul-2026 el formato es un **estándar publicado**
(`strategy_packs/SPEC.md`, atado al código por `tests/test_pack_spec.py`) y el
canónico es **un solo JSON** con `signals` + `strategies`; el import de la app
acepta JSON y xlsx indistintamente, y `scripts/pack_from_json.py` genera las
planillas si se quieren. **Validar SIEMPRE antes de entregar** con
`python scripts/validate_pack.py <pack>.json` — corre sin base y da los mismos
errores que el import, más avisos de las trampas silenciosas (mapa discreto
incompleto, thresholds desordenados). Con `--catalog` (lo que baja el botón
*Catálogo* de /admin/signals) además verifica indicadores y sectores reales.
Los filtros por atributo ahora SÍ se pueden incluir: van **por nombre**
("Technology"), el import los resuelve al id de esa base. Documentar el pack
en `strategy_packs/README.md` (orden: señales primero). Ver
[[packs-estandar-para-ia]] y [[filtro-estrategias-y-roadmap-indicadores]].
