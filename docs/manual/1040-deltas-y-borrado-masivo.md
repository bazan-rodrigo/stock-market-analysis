---
slug: deltas-y-borrado-masivo
title: Deltas, recalculos y borrado masivo
chapter: Anexo tecnico
order: 1040
roles: admin
---

Casi todo el trabajo pesado del sistema es recalcular algo ya calculado. Cómo se
decide qué se rehace, y cómo se borra lo viejo sin frenar la base, concentra la
mayoría de las decisiones medidas del proyecto.

La convención de nombres es estricta: `update_*_history` es el delta (completa
huecos y rehace la última fecha) y `rebuild_*_history` borra y recalcula desde
cero. En los tres dominios **son la misma implementación con un flag `force`**
—`_run_current_and_backfill`, `_signal_history_run`, `_run_ratios_and_backfill`—
para que delta y rebuild no se desincronicen con el tiempo.

## La asimetría: por activo o por fecha global

**La unidad de trabajo del delta cambia según el dominio.**

En precios, indicadores, sintéticos y ratios el delta es **por activo**.
`backfill_indicator` (en `app/services/technical_service.py`) itera los activos
con precios y decide uno por uno: si un activo no tiene ninguna fila,
`_delta_tail_start` devuelve `None`, cae al camino lento y escribe la serie
entera. Un activo nuevo se llena solo, porque los indicadores de un activo no
dependen de los demás.

En señales y estrategias la unidad es **una fecha global**. En
`_signal_history_run` (`app/services/signal_service.py`) el universo son las
fechas distintas de `Price.date`, y el "ya calculado" sale de un `DISTINCT date`
sobre las tablas `sig_{id}` / `strat_res_{id}` **sin ningún filtro por activo**.
La razón es que el ranking es transversal: `percent_ranks` da el percentil de un
activo contra todos los de esa fecha y `aggregate_group_scores` promedia sobre
todo el grupo, así que recalcular un activo suelto daría filas incoherentes con
las ya guardadas.

> Un activo nuevo **no aparece nunca** en la historia de señales por más deltas
> que corras: como no agrega fechas nuevas, no hay nada que dispare trabajo. Su
> historia de indicadores, en cambio, se completa sola. Hay que pedir
> "Recalcular completo".

Para que eso no pase en silencio,
`signals_and_strategies_affected_by_new_assets` busca las señales `source=group`
de los grupos que tocan los activos nuevos y arma el aviso.

## La última fecha siempre se recalcula

El precio del día en curso puede cambiar hasta el cierre, así que todo lo
derivado es preliminar; sin esta regla, el valor calculado a media rueda quedaría
congelado para siempre. Está implementada cuatro veces, una por dominio:
`_delete_from_date` borra desde la última fecha y redescarga (precios);
`_delta_tail_start` devuelve un índice que **incluye** la última fecha guardada
(indicadores); el delta de ratios agrega `last_d` a los objetivos; y
`_dates_to_compute` suma siempre la última (señales).

## El camino rápido del delta de indicadores

`_DELTA_TAIL_MODE` lista **24 códigos** aptos para el atajo (18 en modo `series`,
6 en `zones`): si el valor de una fecha no cambia con barras nuevas, alcanza con
escribir la cola. En `series` se valida contra la grilla que no haya huecos; en
`zones` no se puede (hay `None` legítimos) y se asume cola-solamente. El diseño
es fail-safe: ante cualquier duda, camino lento. Se cuentan **cinco caminos** por
activo —`fast`, `gap`, `checksum`, `bench` y `empty`—; el último significa que el
indicador no tiene ningún valor válido para ese activo por su naturaleza, y a
propósito no figura como "lento" en el panel del Centro de Datos.

Dos compuertas cubren lo que el chequeo de huecos no ve: `_BENCHMARK_DEP_CODES`
(1 código) compara el benchmark vigente contra el guardado, y
`_CHECKSUM_DEP_CODES` (13 códigos) compara el sha256 del prefijo histórico contra
el de la corrida anterior. Hacen falta porque los indicadores `full_sample`
reclasifican historia vieja con cada dato nuevo, porque `trend_*` usa una EMA
recursiva sobre toda la historia y su configuración la edita el admin —sin la
compuerta, un delta posterior actualiza sólo la cola y deja la historia con los
parámetros viejos, **en silencio**— y porque `dist_optimal_sma_*` depende de
`best_sma_*`, recalculado a diario.

> El hash del prefijo, `_checksum_prefix`, **no** es `vals_list[:-1]`: cuando la
> última fecha con valor válido queda antes de la última del calendario, ese
> slice tiene largo distinto al que compara la corrida siguiente y el checksum no
> coincide nunca. Fue un bug real —~46 activos en `relative_strength_52w` en
> camino lento permanente— que motivó los tests con Hypothesis de
> `tests/test_delta_tail_properties.py`.

## El caché que evita el full-scan

Los metadatos que abaratan el delta viven en `ind_asset_meta`
(`app/models/indicator_store.py`): PK `(asset_id, code)` más `benchmark_id`,
`checksum`, `min_date`, `max_date` y `row_count`. Antes, `_query_tail_stats`
resolvía eso con `GROUP BY asset_id` y `MIN/MAX/COUNT(*)` sobre cada tabla
`ind_*`: el `COUNT(*)` impide el loose index scan que `MIN/MAX` solos permitirían
sobre la PK, así que era un full-scan por tabla y por corrida, con decenas de
threads compitiendo por el mismo disco. Cachearlo bajó el delta de **3m08s a
2m11s**. Antes se había probado la alternativa obvia —subir los workers del pool
de `cores+2` a `cores+6`— y **empeoró a 3m42s**: el cuello no era falta de
paralelismo sino contención de disco.

El caché sólo puede fallar hacia el lado lento: en `force`, el `DELETE FROM
ind_asset_meta` va en el **mismo commit** que el `TRUNCATE`, así que si el proceso
se cae a mitad el caché queda *ausente* y fuerza el camino lento, nunca un valor
viejo que haga creer que un activo está al día cuando no lo está.

> Editar una tabla `ind_*` a mano desde la consola SQL deja el caché mintiendo y
> **nada lo detecta**: el delta siguiente confía en un min/max/row_count que ya no
> corresponde y escribe sólo la cola. El remedio es forzar un rebuild, o correr
> `reconcile_ind_asset_meta` ("Recalcular caché"), que reconstruye las stats desde
> un full-scan real y **borra** benchmark y checksum en vez de adivinarlos.

La invariante que sostiene todo esto es **lote fallido = metadatos sin
actualizar**. En tablas anchas el worker no escribe código por código: acumula
en un buffer y lo vuelca una vez por lote, así que si el volcado agota los
reintentos *ninguna* fila del lote llegó a la base, de ningún código. Los
resultados por código traen checksum y stats calculados **en memoria**, no de
lo efectivamente escrito, así que dejarlos subir al padre hacía que
consolidara `ind_asset_meta` de filas inexistentes — y el delta siguiente veía
los metadatos coincidentes, tomaba el camino rápido y **el hueco no se
rellenaba nunca**. Hoy `_backfill_batch_worker` descarta `per_code` e
`inserted` cuando el volcado no se completa
(`tests/test_indicator_batching.py` lo fija, con su control del camino feliz).

> El arreglo es de julio de 2026: **una base que venía de antes puede tener ese
> daño ya escrito**. Si en el historial de corridas aparece un error de
> escritura de indicadores (`wide_flush`), correr "Recalcular caché" y después
> una [verificación de datos](/manual/verificacion-de-datos).

## El orden de fases, blindado por test

Delta y rebuild corren primero `recompute_current_indicators` y después
`backfill_all_indicator_values`. Invertirlo fue un bug real:
`dist_optimal_sma_*` lee `best_sma_cache` desde `current_indicator_values`, así
que calcularlo antes usa el valor de la corrida anterior.
`tests/test_indicator_pipeline_order.py` lo blinda stubeando las funciones
pesadas y verificando sólo el orden. El camino por activo respeta la misma
secuencia en `_rebuild_indicators_for_assets`, que además elige rebuild **y no
delta** a propósito: tras una redescarga puntual de precios una corrección
retroactiva de la fuente (un split re-ajustado) no deja hueco, así que el atajo
la ignoraría en los códigos sin compuerta de checksum.

## Borrado masivo: la regla dura

Todo DELETE masivo sobre un rango grande va por **ventanas que avanzan**,
`delete_by_ranges` en `app/services/db_utils.py`. Las tres estrategias se
midieron:

| Estrategia | Resultado medido |
|---|---|
| Sentencia única sobre millones de filas | 400s+, reteniendo locks y undo por minutos |
| Loop `DELETE ... LIMIT N` sobre el rango | 17min+ sin terminar |
| Ventanas que avanzan | decenas de segundos |

> El loop `DELETE ... LIMIT` es **peor** que la sentencia única, no mejor. Es el
> reflejo que uno tiene para "acotar los locks", y es la trampa que el docstring
> de `db_utils.py` existe para prevenir: cada lote arranca su escaneo desde el
> inicio del rango y se come los tombstones de los lotes anteriores, porque el
> purge de InnoDB no llega a tiempo. El costo es O(n²).

La clave de las ventanas es doble: **cada sentencia ataca un tramo virgen del
índice**, nunca re-escanea filas ya borradas, y hay un `session.commit()` dentro
del loop, así que la transacción queda acotada al tamaño de la ventana.

El único consumidor del repo es `app/services/signal_backfill_range.py`, con
ventanas de 100 fechas; si el rebuild cubre toda la historia ni se usa, se hace
`TRUNCATE`. Esos 400s+, dicho sea de paso, se midieron sobre `signal_value`,
tabla que **ya no existe**: la migración 0075 la reemplazó por tablas por unidad
—recalcular dentro de tablas pobladas era **3-5× más caro** que en vacías. Ver
[Modelo de datos](/manual/modelo-de-datos).

## La excepción tolerada

`purge_assets`, en `app/services/asset_service.py`, usa el patrón prohibido:
`DELETE ... WHERE asset_id IN (...) LIMIT 5000` en un `while` con commit por
lote. Se tolera sólo porque el conjunto es chico y está acotado por `asset_id`.
Las tablas de alto volumen se borran por lotes **antes** de la fila de `assets`,
para no dejarle una cascada gigante al `ON DELETE CASCADE`; las dinámicas se
limpian a mano porque `sig_*` y `strat_res_*` no tienen FK a `assets` (el chequeo
encarecería los inserts masivos).

El servicio **no usa `s.delete()` del ORM a propósito**: con commits intermedios
que expiran los objetos, el ORM dispara un lazy-load de cascada frágil y lento y
tira `ObjectDeletedError` si otra transacción ya borró la fila. Y tiene tres
ramas por motor —MySQL con `LIMIT` y lotes, PostgreSQL sin `LIMIT` (no existe en
su `DELETE`; bajo MVCC un DELETE por tabla no bloquea lectores), sqlite con el
ORM—, otro caso donde la técnica correcta depende del motor (ver
[Soportar dos motores](/manual/soporte-dual-de-base-de-datos)). El espacio en
disco no vuelve solo: lo recupera `maintenance_service` con `VACUUM FULL` u
`OPTIMIZE TABLE`.

Deuda anotada: **`purge_assets` no tiene ningún test** —
`tests/test_lock_retry_and_purge.py` lleva "purge" en el nombre pero sólo prueba
`_is_retryable_lock_error`— y `reconcile_ind_asset_meta` tampoco.
