---
name: reflejar-todo-cambio-en-ui-y-spec
description: "Todo cambio del sistema que corresponda debe reflejarse también en la interfaz y en el contrato publicado (SPEC + manual), en el mismo commit"
metadata: 
  node_type: memory
  type: feedback
  originSessionId: 7d646682-e734-4c79-b645-f2655c6e3237
  modified: 2026-07-27T02:30:09.720Z
---

Cuando se agrega o cambia una capacidad del motor (una fórmula de señal, un
operador del filtro, un tipo de operando, un atributo filtrable, una regla de
validación del import), **hay que reflejarlo en las tres caras en el mismo
commit**: el motor, la **interfaz** (dropdowns del ABM, constructor de
filtros, textos de ayuda) y el **contrato publicado**
(`strategy_packs/SPEC.md` + `docs/manual/`).

**Why:** lo pidió el 26-jul-2026, apenas se publicó el estándar de packs
([[packs-estandar-para-ia]]). La razón de fondo: lo que el motor soporta pero
la UI no ofrece es **invisible** para el usuario, y lo que el SPEC no
documenta **no lo puede usar** quien arma packs desde afuera (una IA o una
persona sin acceso al código). Un SPEC desactualizado es peor que no tenerlo:
manda a escribir algo que el import rechaza.

**How to apply:** no redeclarar listas — las fuentes únicas son
`signal_engine.FORMULA_TYPES`, `strategy_filter.{NUMERIC,CATEGORICAL}_OPERATORS`,
`OPERAND_TYPES`, `ATTRIBUTE_KEYS`, `RESOLUTIONS` y
`pack_service.{SIGNAL,STRATEGY,COMPONENT}_COLUMNS`. `tests/test_pack_spec.py`
ya ata el SPEC al código (vocabulario); el lado UI y la semántica en prosa
todavía **no** tienen red automatizada — al 26-jul agregar una fórmula exige
tocar a mano 5 lugares (motor, `_FORMULA_OPTS` en la página, `FORMULA_HELP`
en ui_constants, `_FT_LABEL` en el callback, el editor de
`signal_params_ui`), y agregar un operador o un atributo, 2-4 lugares sin
ningún aviso. Ver [[registro-pantallas-nuevas]] y [[manual-usuario-web]],
que son la misma idea aplicada a las pantallas.
