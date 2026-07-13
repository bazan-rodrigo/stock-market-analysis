---
name: Decisiones técnicas acordadas
description: Decisiones de arquitectura acordadas con el usuario para este proyecto
type: project
originSessionId: d56247d5-0d87-4acc-839e-a171f01f972d
---
**APScheduler:** Opción A — corre en el proceso principal, WSGIDaemonProcess con un solo proceso en producción.
**Why:** Simplicidad, todo en Python, sin cron externo.

**Migraciones:** Alembic con versiones numeradas (0001, 0002...).
**Why:** Permite evolucionar el schema en producción sin perder datos.

**Screener:** Pre-calculado tras cada descarga de precios. El diseño evolucionó: la tabla `screener_snapshot` original fue reemplazada por tablas `ind_{codigo}` (serie por indicador) + `current_indicator_values` (vigentes) + `group_scores` (agregados por grupo).
**Why:** Con 200-1000 activos, el cálculo on-the-fly sería lento (200K filas por carga).

**Nomenclatura (julio 2026):** el término "snapshot" fue eliminado del código. Vocabulario vigente: `current` (valor de hoy, ej. `compute_current_indicators`), `update_*_history` (backfill incremental que además recalcula siempre la última fecha porque el último precio es preliminar), `rebuild_*_history` (borrar y recalcular desde cero), `GroupScore`/`group_scores` (agregados por grupo), `target_date` (fecha de cálculo del pipeline).
**Why:** "snapshot" venía de tablas eliminadas (migraciones 0040/0042) y confundía; el usuario pidió estandarizar.

**Fuente de precios inicial:** Solo Yahoo Finance (via yfinance).
**Why:** Es la única fuente requerida por ahora. Arquitectura extensible para agregar más.

**Remotes de git (13-jul-2026):** `origin` pushea a TRES repos a la vez
(URLs con PAT embebido): bazan-rodrigo, rodrigoqw33 y rodrigoba77
(agregado 13-jul a pedido del usuario; ese repo ya era una copia
sincronizada). Un `git push` normal actualiza los tres; si falla en uno
solo, revisar el token de esa cuenta (`git remote -v`).

**Usuario admin inicial:** Credenciales hardcodeadas admin/admin123 en `Config`.
**Why:** Script de init simple, el admin las cambia después del primer login.

**Configuración:** conf.properties (INI, sección [settings]) con prioridad a variables de entorno.
**Why:** Permite usar env vars en producción Linux y archivo local en desarrollo Windows.
