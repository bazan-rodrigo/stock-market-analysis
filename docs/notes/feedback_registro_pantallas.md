---
name: feedback-registro-pantallas
description: "Al crear una pantalla Dash nueva: registrarla en _PAGES y _CALLBACKS de app/__init__.py (sin auto-discovery) + link en navbar — error recurrente marcado por el usuario"
metadata: 
  node_type: memory
  type: feedback
  originSessionId: 4db31ed2-6727-4196-9e4e-a45306ca9cb0
---

Al agregar una pantalla nueva, registrar SIEMPRE el módulo en las DOS
listas de `app/__init__.py`: `_PAGES` (la página) y `_CALLBACKS` (sus
callbacks), más el link en `app/components/navbar.py`.

**Why:** la app usa `pages_folder=""` — NO auto-descubre páginas. Crear el
archivo en `app/pages/` no alcanza: sin la línea en `_PAGES` la ruta da
404 silencioso. Pasó con `/backtest` (15-jul-2026) y el usuario marcó que
"siempre ocurre" al agregar pantallas.

**How to apply:** checklist de pantalla nueva = página en `app/pages/` +
callbacks en `app/callbacks/` + línea en `_PAGES` + línea en `_CALLBACKS`
+ navbar. La red automática es `tests/test_module_registration.py` (ata el
filesystem a ambas listas; un módulo sin registrar rompe la suite) — no
saltearla ni marcarla como esperada-a-fallar.
