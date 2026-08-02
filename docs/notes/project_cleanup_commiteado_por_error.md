---
name: cleanup-module-commiteado-por-otra-sesion
description: Sesiones en paralelo sobre el mismo working tree — ya pasó DOS veces que una sesión commitee y pushee trabajo de otra; no usar `git add -A` ni dejar cambios stageados esperando
metadata: 
  node_type: memory
  type: project
  originSessionId: 3f3ca86a-8cd7-403c-926e-511e54e97359
  modified: 2026-08-02T05:52:53.333Z
---

**AVISO DE COORDINACIÓN ENTRE SESIONES.** En este repo trabajan varias
sesiones sobre el **mismo working tree**. Si encontrás tus archivos
commiteados sin haberlos commiteado vos, no es un error tuyo ni un conflicto:
ya pasó dos veces.

**Regla que sale de las dos:** no usar `git add -A` ni `git commit -a`;
stagear archivo por archivo, siempre. Y **no dejar cambios stageados
esperando** — el índice es compartido, así que lo que dejes ahí se lo lleva
la próxima sesión que commitee de más, con SU mensaje.

## 2-ago-2026 — el `git rm` de los packs se fue en un commit de notas

Esta sesión borró los 12 archivos de los 4 packs viejos (`garp`, `momentum`,
`pullback`, `pullback_bajista`) con `git rm`, que **stagea** la baja. Antes de
que llegara a commitear, otra sesión commiteó y pusheó: las 12 bajas quedaron
dentro de **`49c8229`**, cuyo mensaje es `docs(notes): carteras andando, y el
bug de render que shipee sin verlo`.

El borrado era el buscado (lo pidió el usuario), así que no hay nada que
arreglar en el contenido — pero la historia dice "docs(notes)" para un commit
que además borra los packs, y **ya está pusheado a origin**. Mismo criterio que
la vez anterior: no se reescribe historia.

## 19-jul-2026 — el módulo de limpieza (nota original, transitoria)

Otra sesión, trabajando en performance del pipeline de indicadores, usó
`git add -A` para commitear una corrección de notas y **arrastró trabajo en
progreso del módulo de limpieza** que estaba en el working tree. Quedó todo
dentro del commit **`f626f01`**, cuyo mensaje dice `docs(notes): corregir el
overclaim de verify_asset_code` — el mensaje NO refleja que también trae
código de limpieza.

Archivos que se fueron en ese commit:
- `app/services/cleanup_service.py` (**alta**)
- `app/callbacks/admin_cleanup_callbacks.py`
- `app/pages/admin_cleanup.py`
- `scripts/clean_data.py`

`tests/test_cleanup_service.py` **NO** entró (se creó después).

**Estado verificado tras el incidente:** no rompió nada. La suite da 759
passed (incluye los ~9 tests del módulo de limpieza), `admin_cleanup` está
registrado en `_PAGES` y `_CALLBACKS` de `app/__init__.py`, y
`app.services.cleanup_service` importa sin problemas.

**Decisión tomada por el usuario:** NO se reescribe la historia. Hacer
force-push sobre `master` en los dos remotes, con Railway auto-desplegando,
es más riesgoso que un commit con mensaje engañoso. El commit queda como
está.

**Consecuencia a tener en cuenta:** ese código **ya está desplegado en
Railway**, aunque el usuario no eligió desplegarlo — se fue con el push.
