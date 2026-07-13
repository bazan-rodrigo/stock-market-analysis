---
name: feedback-calendar-popup
description: "El popup del calendario de dcc.DatePickerSingle sigue mostrando fondo blanco — múltiples intentos fallaron, usuario decidió dejarlo así"
metadata: 
  node_type: memory
  type: feedback
  originSessionId: 94d9e8a1-350e-4015-9aaa-71c8b63ddd5c
---

El fondo blanco del popup del calendario (`dcc.DatePickerSingle`) no pudo resolverse después de varios intentos (CSS por clase, CSS wildcard `[class*="..."]`, JS por ID, JS global con MutationObserver). El usuario dijo "ya dejalo".

**Why:** La causa raíz probable es que react-dates inyecta CSS dinámicamente (clases `_1`, `_2`) con `!important` después de que carga nuestro archivo CSS, y el mecanismo exacto varía según la versión de Dash instalada en el Codespace. El input field sí quedó dark; solo el popup (el grid de días) sigue blanco.

**How to apply:** No retomar este problema a menos que el usuario lo pida explícitamente. No proponer más intentos de fix del popup del calendario.
