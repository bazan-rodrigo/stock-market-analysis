---
name: entregar-estrategias-como-import-files
description: "Cuando el usuario pide una estrategia de trading, entregarla como archivos Excel de importación, no como instrucciones manuales"
metadata: 
  node_type: memory
  type: feedback
  originSessionId: 44667c57-b1c8-440a-b3df-63205dec6695
---

Cuando el usuario pide una estrategia de trading para probar, generarle los
archivos de importación en `strategy_packs/` del repo (no darle pasos para
crearla a mano en la UI).

**Why:** lo pidió explícitamente (12-jul-2026): "cuando te pido estrategias
me das los files y no los tengo que crear a mano".

**How to apply:** dos xlsx por pack — `<pack>_senales.xlsx` (formato del
import de /admin/signals: key, name, description, source, group_type,
indicator_key, formula_type, params) solo con señales que NO existen ya, y
`<pack>_estrategia.xlsx` (hojas Estrategias: name/description/
filter_conditions + Componentes: strategy_name/signal_key/weight/scope/
group_type/group_id). Validar offline con `signal_engine.validate_params` y
`strategy_filter.validate_tree` antes de entregar; documentar el pack en
`strategy_packs/README.md` (orden: señales primero). No incluir condiciones
por atributo con ids de catálogo (dependen de cada base) — anotarlas en el
README para agregar a mano. Ver [[filtro-estrategias-y-roadmap-indicadores]].
