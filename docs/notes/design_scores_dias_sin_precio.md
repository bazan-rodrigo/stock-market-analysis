# Diseño pendiente: scores en días sin precio propio (as-of carry-forward)

**Estado: SIN DECIDIR (13/14-jul-2026).** Se evaluaron dos alternativas a fondo;
el usuario no quedó seguro y pidió guardarlas para retomar. No implementar sin
volver a discutir.

## El problema

El pipeline de señales/estrategias computa una fecha D si **algún** activo tiene
precio en D (las fechas salen de `distinct(Price.date)`). Los indicadores se leen
**as-of** (`query_values_asof`, tope `ASOF_MAX_LOOKBACK_DAYS = 45`): última fila
`<= D` dentro de 45 días. Consecuencia:

- Un activo cuyo último precio es el 10-jul recibe score el 13-jul (arrastrando su
  valor del 10) **si otro activo** (cripto/FX el finde, un índice, un sintético)
  hizo del 13 una fecha computable. → **scores "ficticios" en días que el activo
  no cotizó** (lo que el usuario reportó como incorrecto).
- Esos scores **no se refrescan** cuando llega el dato real de ese activo para esa
  fecha, porque el delta de señales es **por-fecha global**: `_dates_to_compute`
  solo reprocesa huecos (fechas sin *ningún* score) + siempre la última. Una fecha
  ya calculada (aunque incompleta para un activo) no se toca.

Incoherencia clave detectada: **`group_scores` YA usa fecha exacta** (`exact(d)`
sobre `ind_trend_*`): el agregado de un sector el día D solo incluye activos con
tendencia en D (que cotizaron D). Pero `signal_value` por-activo sí arrastra vía
as-of. O sea signal_value y group_scores hoy son **incoherentes**.

Casos comunes donde aparece: fin de semana (cripto cotiza domingo, stocks no);
descargar precios de unos activos y no de otros; **crear un activo nuevo** y traer
sus precios sin haber corrido el delta de los existentes.

## Alternativa A — GATE + recálculo dinámico (la más desarrollada)

**Gate:** un activo recibe `signal_value`/ranking en D **solo si tiene precio en
D**. Los ficticios **no existen** (más limpio, coherente con group_scores y con el
corte de línea del gráfico ya hecho).

- **No rompe semanales/mensuales**: el gate va por el **precio propio** (que existe
  a diario), NO por la fecha exacta del indicador. En un día que el activo cotizó,
  la señal semanal/mensual se sigue leyendo as-of (fin de período). El as-of queda
  intacto; el gate solo saca los días sin cotización propia.
- **Dónde**: filtrar `isnaps` a los activos con precio en D, en los DOS caminos
  (`compute_signal_values` y el modo rango), dejando el evaluador compartido
  `_evaluate_asset_signal_scores` intacto (preserva la paridad por-fecha↔rango).

**Refresco del dato tardío** (el activo SÍ cotizó D pero el precio llegó tarde →
hay que reprocesar D, que no es hueco): recálculo **dinámico desde la fecha más
vieja que recibió dato nuevo, con TOPE**.

- **Marcador persistente** `min_dirty_date` en una tabla meta:
  - Lo **acumula** (`min`) el core del backfill de indicadores, usando la **fecha
    más vieja GENUINAMENTE NUEVA** = primera fecha **más allá del `max_date` previo**
    del activo (cacheado en `ind_asset_meta`).
  - **CRÍTICO**: tiene que ser "dato nuevo", NO "fecha reescrita". El delta de
    indicadores SIEMPRE reescribe la última fecha de cada activo (preliminar); si el
    marcador contara eso, un activo parado en 5-jul re-dispararía 5-jul en cada
    corrida (loop). Por eso: solo cuentan filas en fechas > max_date previo.
  - Lo **consume y resetea** el delta de señales (recién al terminar bien).
- El delta reprocesa la unión de: huecos + última + `[max(min_dirty_date,
  frontera − CAP), frontera]`. `CAP` ~90 días.
  - Catch-up de 5 días → reprocesa las 5 completas.
  - Avance normal (marcador futuro) → rango vacío (lo cubre el hueco).
  - Alta con años de historia → capado; lo anterior a CAP = "Recalcular completo".
- **Independiente del orden/botones**: como el marcador es persistente y acumulado,
  correr indicadores y señales por botones separados, o varias veces, funciona
  (cada corrida de indicadores acumula el min; señales lo consume). No depende de
  una sola tarea.

Plan de implementación detallado (migración → gate+tests → marcador → consumo en
delta → tests): quedó escrito en el chat; rehacerlo al retomar.

## Alternativa B — Flag "preliminar" + refresco por JOIN

**Conservar** el carry-forward pero marcarlo y refrescarlo (no borrarlo).

- Columna `preliminary` (bool) en `signal_value`: true cuando el activo no tenía
  precio en esa fecha exacta (score arrastrado).
- El delta suma a las fechas a reprocesar las del JOIN:
  `SELECT DISTINCT sv.date FROM signal_value sv JOIN prices p ON p.asset_id=sv.asset_id
   AND p.date=sv.date WHERE sv.preliminary=1` → fechas donde un score preliminar
  consiguió precio real del mismo activo. Auto-limpiante (al reprocesar deja de ser
  preliminar). El domingo-stock (nunca tendrá precio) nunca matchea → no se reprocesa.
- **Necesita acotar** el JOIN a una ventana reciente (ej. `sv.date >= frontera−60`)
  para no escanear años de preliminares permanentes (domingos de stocks) → costo
  del delta constante.

## Comparación

| | Gate (A) | Preliminar (B) |
|---|---|---|
| Score ficticio | no existe (resuelve la queja de raíz) | existe, marcado y refrescado |
| Coherencia con group_scores | sí | no (signal_value sigue arrastrando) |
| Domingo/delistado | nada (no se scorea) | preliminar para siempre (hay que acotar ventana) |
| Modelo de datos | tabla meta (marcador) | columna + JOIN + ventana |
| Dato tardío (lag N días) | marcador + recálculo dinámico | JOIN lo resuelve |
| Semántica | cambia (menos filas) | igual (solo etiqueta) |

## Casos borde chequeados

- **Activo que deja de cotizar (delistado):** con A, no se scorea → nada. Con B,
  queda preliminar; el tope as-of de 45 días lo saca del pipeline ~45 días después.
- **Lag de 5 días:** ambos refrescan **los 5**, no solo el último.
- **Re-correr indicadores sin datos nuevos:** con A (marcador por dato nuevo) NO
  re-dispara; con la definición ingenua (fecha reescrita) sí → por eso el marcador
  debe ser "dato genuinamente nuevo".

## Al retomar

Decidir A vs B. Recomendación tentativa: **A (gate + recálculo dinámico con tope)**
por ser el arreglo de fondo y coherente con group_scores, pero el usuario no quedó
convencido — revisar de nuevo. Recordar: aplicar cualquiera a la historia existente
requiere un "Recalcular completo" una vez (los carry-forward viejos no se borran
solos). Ver [[filtro-estrategias-y-roadmap-indicadores]] y
[[group-scores-solo-grupos-consumidos]].
