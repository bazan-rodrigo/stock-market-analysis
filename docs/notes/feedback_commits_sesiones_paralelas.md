---
name: feedback-commits-sesiones-paralelas
description: "En este repo hay sesiones en paralelo — commitear SIEMPRE con los archivos explícitos, porque `git commit` publica todo lo que esté staged lo haya puesto quien sea"
metadata: 
  node_type: memory
  type: feedback
  originSessionId: 022a1659-e3a1-43ba-8580-b5a5499c6b9f
  modified: 2026-08-02T05:57:01.851Z
---

En este repo trabajan **varias sesiones a la vez** sobre el mismo working tree.

**La regla: commitear con los archivos explícitos.**

```
git commit -- app/mi_archivo.py tests/test_mi_archivo.py -F- <<'EOF'
...
EOF
```

**Por qué:** `git commit` a secas publica **todo lo que esté en el índice**, lo
haya puesto ahí quien sea. Hacer `git add` solo de los archivos propios NO
alcanza: si otra sesión ya dejó cosas staged, se van en el commit de uno.

**Pasó el 2-ago-2026** (commit 49c8229): hice `git add` de tres archivos de
`docs/notes/` y el commit se llevó además **12 bajas de `strategy_packs/`** que
la sesión paralela tenía staged. Resultado: el repo quedó sin ningún pack —las
bajas publicadas, los reemplazos todavía sin trackear— con un mensaje de commit
que hablaba de otra cosa. El usuario decidió dejarlo así (la baja era
intencional de esa sesión y la iban a completar).

La memoria ya avisaba "no usar `git add -A`" y **no lo usé**: la regla vieja era
demasiado angosta. El agujero no es `add -A`, es el índice compartido.

**Antes de cada commit acá:** mirar `git status --short` y confirmar que lo
staged sea solo lo propio. Si aparece algo ajeno, no es para commitear — es
trabajo en curso de otro.

Relacionado: [[project-cleanup-commiteado-por-error]] (el mismo tipo de
incidente, la primera vez).
