---
name: carga-masiva-alto-volumen
description: "Import Excel + descarga de precios \"solo nuevos\"/redescarga global optimizados para 10k activos (21-jul, commits adcd0bb/ea97fa5); pendiente verificar con red real en Codespace"
metadata: 
  node_type: memory
  type: project
  originSessionId: 778df6e9-3198-4e99-b2ba-5b8b27296640
  modified: 2026-07-22T01:26:20.163Z
---

**Carga masiva de activos a escala 10k — implementado 21-jul-2026, commits
`adcd0bb` (precios) y `ea97fa5` (import), pusheados.** Cierra el gap que el
usuario detectó: todo el escalado previo ([[objetivo-soportar-10000-activos]])
era del pipeline posterior; el alta masiva seguía secuencial.

**Precios (`price_service.py`):** `_bulk_download_assets(assets, progress_cb,
full)` extraído de `update_all_active_assets` (split Yahoo/otras+sintéticos,
last_dates en un GROUP BY, prefetch por chunks de 200, ThreadPool de 6, y
skip_indicators=True siempre — el llamador encadena el delta UNA vez).
`update_new_assets_prices` ("solo nuevos", el botón natural post-import) lo
reusa: activos nuevos caen enteros al grupo first_time (historia completa en
batch). `redownload_prices` global también, con `full=True`: los workers
borran la historia previa DENTRO de su transacción y solo si la descarga
trajo datos (chequeo de df vacío ANTES del delete). La redescarga puntual
sigue secuencial a propósito. "Actualizar todos" conserva su cadena idéntica
(delta indicadores → fundamentales → group_scores; test de orden lo fija).

**Import (`import_service.py`):** dos fases. (1) `_prefetch_validations`:
ThreadPool de 6 resolviendo `validate_ticker` en paralelo — red pura, CERO
BD en threads; dedupe por (fuente,ticker); existentes/fuente desconocida se
saltean sin red; retry con backoff exponencial ante transitorios
(`_is_transient_error`; yahoo.py ahora distingue HTTP 429 de "no
encontrado"). (2) El alta secuencial original consumiendo los resultados.
`validate_ticker` ganó `need_metadata=True` (default compatible): fila del
Excel completa (los 7 campos autocompletables, caso re-import de planilla
exportada) → Yahoo saltea el `.info` lento, queda solo el chequeo de
existencia. Micro-opts: `_cached_resolve` memoiza catálogos por corrida,
ImportLog precargado en dict (commit por fila SE CONSERVA — durabilidad),
benchmarks en 2da pasada con mapa ticker→id + bulk_update_mappings + 1
commit. Fix de paso: `fuente_fundamentales` vacía llegaba como NaN →
advertencia espuria "'nan' no encontrada" en toda fila sin fundamentales.

**Decisiones/casos borde:** import_service NO importa app.sources a nivel
módulo (el `__init__` del paquete arrastra yfinance, que no está en esta PC
ni en la suite) — `_ValidationFailure` duck-typed para el camino de error.
El import_log guarda el ÚLTIMO intento por ticker: una fila duplicada dentro
del archivo pisa el "imported" con "skipped" (semántica histórica, fijada en
test). Deletes full concurrentes: mismo patrón de locking que ya corre (6
workers, activos distintos); un 1205/1213 queda como error por-activo sin
voltear la corrida (revisado y aceptado).

**Why:** a 10k activos la validación secuencial contra Yahoo (2-4 s/ticker)
y la descarga por-activo eran horas; el resto del pipeline ya escala.

**How to apply / PENDIENTE CODESPACE:** probar con red real: importar una
planilla (mirar la barra en 2 fases y que el re-import de una planilla
exportada NO pegue al `.info`), después "Actualizar Precios → solo nuevos"
(debe ir en batch, minutos no horas) y una redescarga global chica. Si Yahoo
tira 429 en ráfaga, bajar `_VALIDATE_WORKERS`/`_UPDATE_WORKERS` (constantes
al tope de cada servicio).
