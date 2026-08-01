---
name: project-trinquetes-faltantes
description: "Los cuatro huecos de trinquete que quedaron sin cubrir (1-ago-2026), medidos en el código, con el arreglo propuesto de cada uno"
metadata: 
  node_type: memory
  type: project
  originSessionId: 022a1659-e3a1-43ba-8580-b5a5499c6b9f
  modified: 2026-08-01T17:54:02.965Z
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

### 3. Nombres de tablas dropeadas que sobreviven en el código

Nueve referencias vivas a `sig_{id}` / `strat_res_{id}` en docstrings y
comentarios: `asset_service`, `maintenance_service`, `portfolio_backtest_service`,
`rules_backtest_service`, `signal_backfill_range` (y las de `cleanup_service`,
que ahora son deliberadas). Son comentarios, **pero la misma clase de resto sí
fue bug** en `cleanup_service`, donde el nombre viejo estaba en la lógica.

**Arreglo:** un test que grepee el código por nombres de tablas dropeadas por
una migración. Feo pero efectivo — habría encontrado el bug de Limpieza el día
del cutover de la 0094.

### 4. La cobertura de limpieza, derivada en vez de escrita a mano

Hoy `_LEAF_TABLES` y los tests de cobertura son listas paralelas mantenidas a
mano. **Arreglo:** recorrer los modelos registrados y exigir que cada tabla esté
o en el alcance de limpieza, o en una lista de exclusión con su motivo. Una
tabla nueva rompe la suite hasta que alguien decida conscientemente en qué grupo
va. Mismo mecanismo que `test_module_registration.py`, que funciona bien
justamente porque deriva del código.

### 5. El SPEC en prosa

Ya estaba anotado en [[project-packs-estandar]] y sigue vigente:
`test_pack_spec.py` ata las **listas** (fórmulas, operadores, columnas) pero no
la **prosa**, y por eso §1 quedó describiendo un flujo viejo durante 4 días. El
1-ago se le agregó a §8 la regla de que las señales exigen admin, y esa frase
**tampoco tiene quién la verifique**: si mañana se revierte el gate, el SPEC va
a seguir afirmándolo.

---

Relacionado: [[project-ia-mcp]] (la capa de IA es el consumidor que más se
beneficia de estos trinquetes: llama a los servicios desde fuera de un request
Flask, sin `current_user` del que deducir nada).
