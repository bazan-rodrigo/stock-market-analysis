---
name: feedback-confirmacion-cambios
description: "Pedir confirmación antes de aplicar cambios al código, no ejecutarlos directamente al detectar un problema"
metadata: 
  node_type: memory
  type: feedback
  originSessionId: 94d9e8a1-350e-4015-9aaa-71c8b63ddd5c
---

Siempre pedir confirmación antes de aplicar cambios al código, incluso cuando el problema y la solución son claros.

**Why:** El usuario quiere revisar y aprobar la solución propuesta antes de que se escriba en los archivos. Aplicar cambios directamente sin confirmación previa le quita control del proceso.

**How to apply:** Después de identificar un problema y diseñar la solución, presentarla al usuario con "¿Aplico estos cambios?" y esperar el "sí" antes de usar Edit/Write. Aplica a cualquier modificación de código, CSS o configuración.

**Refuerzo (julio 2026, el usuario lo marcó dos veces):** una PREGUNTA es una pregunta — "¿tenemos forma de...?", "¿cómo se determina...?", "¿se puede...?" piden explicación/diseño, NO implementación. Aunque la respuesta implique una solución obvia y el usuario venga aprobando todo, responder primero y esperar el "sí" explícito. El ritmo de aprobaciones previas no convierte una pregunta en una orden.

**Refuerzo 2 (14-jul-2026, tercera vez que lo marca):** tampoco los PEDIDOS DIRECTOS ni los REPORTES de problemas autorizan a editar ("esto debería ser una sección separada", "no le veo sentido a X", "vi que Y se dibuja mal"). TODO cambio de código sigue el mismo flujo: proponer la solución concreta → esperar "sí" → recién ahí Edit/Write. La única excepción práctica que el usuario venía aceptando es cuando el "sí" es a una propuesta ya presentada en el mensaje anterior. Ante ambigüedad (ej. responde describiendo el problema en vez de "sí"), preguntar, no asumir.

**Refuerzo 3 (16-jul-2026, cuarta vez):** un "sí" que responde una pregunta FACTUAL no autoriza una propuesta pendiente. Caso concreto: pregunté dos cosas en un mensaje ("¿cuál modal viste?" y "¿agrego la instrumentación?"); el usuario respondió "si, estaba desactivado el check..." — su "sí" contestaba lo del modal/switch, y lo tomé como aprobación de la instrumentación y edité. MAL. Si un mensaje mío tiene más de una pregunta, el "sí" del usuario solo cubre lo que su propio texto indica; cualquier duda → volver a preguntar solo por la propuesta, sin editar. Mejor aún: no mezclar una pregunta factual y un pedido de autorización en el mismo mensaje.
