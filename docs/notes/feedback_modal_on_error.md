---
name: Modal no se cierra si hay error al guardar
description: El modal/editor debe permanecer abierto cuando hay un error de validación o guardado, para que el usuario pueda corregir sin perder lo ingresado
type: feedback
originSessionId: 44377bb4-887c-4512-92c7-49aa1b27dc1e
---
El modal de ABM no debe cerrarse al hacer clic en "Guardar" si ocurre un error.

**Why:** El usuario pierde lo que había cargado y no puede corregir el problema.

**How to apply:** En los callbacks de ABM:
- El callback que controla `modal.is_open` NO debe cerrar el modal al detectar el trigger "btn-save" — solo debe abrirlo al "btn-add"/"btn-edit" y cerrarlo en "btn-cancel".
- El callback de `save_event` (el que hace el guardado real) debe ser quien controle el cierre del modal: emitir `is_open=False` solo en caso de éxito, y dejar `is_open=no_update` (modal abierto) en caso de error o validación fallida.
- Esto requiere que `save_event` tenga `Output("...-modal", "is_open")` y use `allow_duplicate=True` si es necesario.
