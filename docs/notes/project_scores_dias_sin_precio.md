---
name: scores-dias-sin-precio-pendiente
description: "Diseño SIN DECIDIR: scores ficticios en días que un activo no cotizó (as-of carry-forward). Dos alternativas guardadas, retomar."
metadata: 
  node_type: memory
  type: project
  originSessionId: 1cfc6581-fa76-4acd-aea2-a61221e684ed
---

**PENDIENTE, SIN DECIDIR (13/14-jul-2026).** El usuario notó que un activo tiene
score en fechas que no cotizó (ej. 13-jul con último precio 10-jul), porque el
pipeline computa toda fecha que *algún* activo tenga precio y los indicadores se
leen **as-of** (tope 45 días) → arrastra el último valor propio. Además esos
scores no se refrescan cuando llega el dato real (el delta de señales es
por-fecha global: solo huecos + última). Incoherencia clave: `group_scores` YA
usa fecha exacta, pero `signal_value` arrastra.

Se evaluaron a fondo DOS alternativas y el usuario pidió guardarlas para verlas
más adelante (no quedó convencido). El detalle completo (problema, las dos
alternativas, comparación, casos borde delistado/domingo/lag-5-días, y el plan
de implementación) está en el repo: **`docs/notes/design_scores_dias_sin_precio.md`**.

Resumen de las alternativas:
- **A — Gate + recálculo dinámico:** scorear un activo en D solo si tiene precio
  en D (no rompe semanales/mensuales porque el gate va por el precio propio, no
  por la fecha del indicador). Refresco del dato tardío con un marcador
  persistente `min_dirty_date` (fecha más vieja GENUINAMENTE nueva, no reescrita)
  acumulado por indicadores y consumido por el delta de señales, con TOPE (~90
  días). Coherente con group_scores.
- **B — Flag `preliminary`:** conservar el carry-forward pero marcarlo y
  refrescarlo cuando aparece el precio real (JOIN signal_value preliminar ⋈
  prices), con ventana reciente para no acumular.

Recomendación tentativa: A, pero revisar. Aplicar cualquiera a la historia
existente requiere un "Recalcular completo" una vez. Ver
[[filtro-estrategias-y-roadmap-indicadores]] y [[group-scores-solo-grupos-consumidos]].
