---
slug: modelo-de-datos
title: Modelo de datos: tablas fijas, dinamicas y anchas
chapter: Anexo tecnico
order: 1020
roles: admin
---

La base tiene tres tipos de tabla, y saber en cuál cae una es lo primero antes de
tocarla. Las **fijas** son el modelo declarativo de siempre. Las **dinámicas** se
crean y se dropean en runtime, una por señal y una por estrategia, y viven fuera
de `Base.metadata`. Las **anchas** juntan decenas de indicadores en cinco tablas
por cadencia. Cada una salió de un problema medido.

```text
  FIJAS            DINAMICAS              ANCHAS
  48 tablas        sig_{id}               ind_daily / weekly / monthly
  app/models/      strat_res_{id}         ind_fundamental_daily
  Base.metadata    (fuera del metadata)   ind_fundamental_quarterly
  Alembic las ve   Alembic NO las ve      Alembic las ve (con filtro)
```

## Las tablas fijas

Son **48 tablas** en `Base.metadata`, en 41 módulos de `app/models/` (48 clases
que heredan de `Base`). El índice de importación es `app/models/__init__.py`:
**lo que no se importa ahí no lo ve ni Alembic ni `create_all`**.

| Familia | Tablas |
|---|---|
| Referencia | `countries`, `currencies`, `markets`, `instrument_types`, `sectors`, `industries`, `price_sources`, `catalog_aliases` |
| Activos y precios | `assets`, `prices`, `synthetic_formula`, `synthetic_component`, `currency_conversion_divisor` |
| Fundamentales | `fundamental_sources`, `fundamental_quarterly`, `fundamental_update_log` |
| Pipeline | `indicator_definitions`, `current_indicator_values`, `ind_asset_meta`, `group_scores`, `signal`, `group_signal_value`, `signal_eval_log`, `strategy`, `strategy_component` |
| Backtest | `backtest_run`, `backtest_quantile_stat`, `backtest_ic_point` |
| Carteras | `portfolio`, `portfolio_member`, `portfolio_run`, `portfolio_run_point`, `portfolio_transaction` |
| Config de análisis | `drawdown_config`, `regime_config`, `volatility_config`, `sr_config`, `pnf_config` |
| Infraestructura | `users`, `app_settings`, `scheduler_config`, `run_lock`, `price_update_log`, `indicator_update_log`, `import_log`, `market_event`, `verification_run_log`, `asset_verification_flag` |

Dos detalles muerden. La tabla `signal` es palabra reservada en MariaDB, y el
quoting no puede hardcodearse con backticks porque PostgreSQL usa comillas dobles:
va por `db_compat.quote_ident` (ver
[Soportar dos motores](/manual/soporte-dual-de-base-de-datos)). Y `group_scores`
declara sus índices con los nombres históricos de cuando se llamaba
`group_indicator_snapshot` —la 0050 la renombró— para que `create_all` y las
migraciones produzcan el mismo esquema y `alembic check` no marque un diff eterno.
Es el costo visible de mantener dos caminos de bootstrap.

## Las tablas dinámicas

Cada señal tiene su `sig_{id}` y cada estrategia su `strat_res_{id}`, desde
`app/models/signal_store.py`. El motivo está medido: con las dos tablas
monolíticas anteriores (`signal_value`, `strategy_result`) **la unidad de
recálculo no coincidía con la de almacenamiento**, así que todo recálculo acotado
pagaba borrar-e-insertar en tabla poblada, **3 a 5 veces más caro que en una
vacía**. Con tabla propia, recalcular es TRUNCATE más insertar en vacío; la 0075
copió la historia con INSERT…SELECT sin obligar a recalcular. Y borrar una señal es
hoy un DROP instantáneo: antes el CASCADE de `signal_value` retenía locks borrando
millones de filas.

Casi todo el resto del módulo sale de un solo hecho:

> **El DDL de MySQL no es transaccional** (hace commit implícito): ninguna
> operación que toque definición *y* tabla puede ser atómica.

De ahí, tres decisiones. **Se nombran por el ID inmutable, no por la key** —la key
es editable desde el ABM, y con el id renombrar es metadata puro—. **El orden deja
siempre el lado benigno**: en el alta primero se commitea la definición y después
va el CREATE (un crash deja una definición sin tabla, reparable con `ensure_*`); en
la baja primero se borra la definición y después el DROP (un crash deja una tabla
huérfana inofensiva). Y **`reconcile_dynamic_tables`** cierra los dos huecos en el
arranque —tabla sin definición se dropea, definición sin tabla se crea vacía— con
regex anclados (`^sig_(\d+)$`) para no barrer por error las tablas fijas `signal` o
`strategy`.

La PK es **`(date, asset_id)`, con date primero**, al revés que en las tablas de
indicadores: el backfill de señales es por-fecha global, inserta cronológicamente
(append-only sobre el clustered index) y opera por ventanas de fechas que necesitan
el prefijo; con date al final, cada ventana hacía full scan. El espejo lo mide la
0062, que agregó `ix_date` a las `ind_*` porque su PK `(asset_id, date)` no sirve
para filtrar solo por fecha: eso costaba **unos 18 full scans de ~1M filas por cada
fecha** del backfill de señales. Tampoco tienen FK a `assets`: se resigna el
borrado automático para no pagar el chequeo de FK en cada insert masivo, y
`purge_assets` las descubre por catálogo y las limpia a mano.

> Cualquier camino de borrado de activos que no pase por `purge_assets` deja filas
> huérfanas en las dinámicas. No hay CASCADE que lo salve.

## Las tablas anchas por cadencia

Son cinco: `ind_daily` (14 columnas), `ind_weekly` (5), `ind_monthly` (5),
`ind_fundamental_daily` (4) e `ind_fundamental_quarterly` (8) — **36 códigos**, 6
de ellos VARCHAR(50) y el resto FLOAT. Una fila por `(asset_id, date)`, una columna
por indicador, y el nombre de la columna *es* el código.

El problema, medido con `scripts/measure_indicator_storage.py` sobre la base real:
**el overhead domina**. El ratio índice/datos daba ≈1.02, y cada fila `ind_{code}`
diaria ocupaba 94-102 B para un payload útil de ~16 B — **alrededor del 80% es
estructura**, no dato. Las ~13-14 tablas diarias juntas (~20 MB) costaban unas
**7 veces la tabla `prices`** de la que derivan. Con 4 activos de historia profunda
la base pesaba 42 MB y las `ind_*` eran ~54%, contra un tope de 500 MB en Railway.
Como **acortar la historia estaba descartado por decisión del usuario**, la única
variable libre era la estructura: la ancha paga el overhead una vez por
`(activo, fecha)` en lugar de N veces.

Es la tercera etapa: EAV única (`indicator_values`, 0039) → una tabla por indicador
(`ind_{code}`, 0043, por la contención del PK autoincremental de la EAV) → anchas.
La segunda se revirtió porque **su motivo original desapareció**: el backfill hoy
particiona por activo. El gate era explícito —no se mergeaba si no quedaba al menos
igual de rápido— y el refactor resultó compute-positivo: escritura de 14
`executemany` por activo a 1 fila, lectura de señales de ~24 `query_values_asof`
por fecha a 3, `tail_stats` de 24 full-scans a 3.

### El truco para no tocar a los lectores

`_CodeView`, en `app/models/indicator_store.py`, es una vista por-código sobre la
ancha, **drop-in de una `ind_{code}` para los lectores**: su `.c.value` es el
Column *real* de la columna en la ancha, así que cualquier select o join compila
directo contra ella, en SQL plano y sin subquery. `get_ind_table` devuelve el proxy
cuando el flag está activo, y la transparencia es total: ningún consumidor de
`app/services` ni `app/callbacks` hace `isinstance` contra `_CodeView`. Los
escritores van por `technical_service.upsert_ind_cadence`; `_CodeView` no expone
`insert`/`update`/`delete`, así que un escritor que lo use por error falla con
`AttributeError` inmediato en vez de en silencio.

El ruteo lo decide `USE_WIDE_IND_TABLES`, con **default `1`** desde la fase 5,
porque las per-código de esos 36 códigos se dropearon en las migraciones 0079 y
0082. La suite lo fuerza a `0` en `tests/conftest.py` porque corre contra un stub
sqlite con tablas per-código.

> Consecuencia incómoda: **la suite ejercita el camino per-código, no el ancho**.
> El que corre en producción está bastante menos cubierto de lo que sugiere el
> conteo de tests. Ver [Cómo se prueba](/manual/pruebas-y-medicion).

### Las dos trampas

> Que exista la fila `(asset_id, date)` **no significa** que tu columna tenga
> valor: la pudo escribir un código hermano de la misma cadencia dejando la tuya en
> NULL. Sin `value IS NOT NULL`, ese NULL gana el `MAX(date)` y **oculta el último
> valor válido**.

Por eso la lectura as-of es **por columna**: `query_values_asof` filtra
`isnot(None)`, idéntico en `_load_sweep` y en el read de `group_score`. En las
per-código, que nunca guardan value NULL, es equivalente al comportamiento previo,
así que fue deploy-safe; aun así hubo lectores de display y verificación sin el
filtro que reportaban diferencias falsas e historia espuria. Del mismo hecho sale
`_null_wide_column`: se nullea la columna, no se borra la fila que las otras
columnas comparten.

> Escribir una ancha **columna por columna** genera N-1 tuplas muertas por fila.
> Medido: `ind_daily` pasó de 3,4 a 25 MB tras un rebuild ingenuo.

`upsert_ind_cadence` es un **upsert parcial por columna** —así varios códigos
escriben la misma fila sin pisarse— pero escribir de a una columna multiplica las
versiones de fila. El fix es un buffer thread-local que vuelca la fila completa una
sola vez (el delta no se bufferiza: su bloat es chico y lo recupera autovacuum). El
caso peor estaba en `backfill_asset_history`, que corre tras **cada** descarga de
precios: nulleaba la columna sobre toda la historia del activo y después la
escribía, por código — ~28 versiones de fila por fila con 14 columnas, unas
**450.000 para un activo de 16.000 barras**. El fix real: borrar las filas de esa
cadencia una vez, cuando los códigos la cubren entera, y recién ahí bufferizar.

De los 48 indicadores integrados, 36 tienen historia y 12 no (viven en
`current_indicator_values`). Los 36 están todos en las anchas, así que **en una base
migrada no queda ninguna `ind_{code}` per-código viva**; el camino per-código
sobrevive solo como fallback del flag y para la suite. Por eso `ensure_builtin_data`
saltea los códigos anchos al materializar `ind_{code}`, o el drop de la 0079 se
desharía en cada arranque. Aparte de los valores, `ind_asset_meta` guarda por
`(asset_id, code)` el metadato de invalidación del delta tail-mode, que evita un
full-scan por delta (ver [Deltas y recálculos](/manual/deltas-y-borrado-masivo)).
Ojo: **la consola SQL permite DML arbitrario sobre `ind_*` sin pasar por los
servicios**, así que tras una edición manual hay que forzar un rebuild o ese caché
queda desincronizado.

## Alembic y la frontera 0075

La cadena tiene **85 migraciones lineales**, de `0001_initial_schema` a la head
única `0085`. **0001–0075 quedaron congeladas como solo-MySQL** y no se tocan;
**desde la 0076 la cadena es única y portable**. Volver portables 75 migraciones
históricas sería trabajo muerto: ninguna base nueva las corre —nacen por
`create_all` más stamp head con `scripts/init_db.py`— y las MySQL existentes ya
pasaron por ellas. El guardián es `tests/test_bootstrap_portability.py`, que
renderiza el tramo `0075:head` en modo offline contra `mysql://` y `postgresql://`,
sin base ni driver.

El detalle que arruina el día de quien no lo sabe está en `alembic/env.py`:

> Las dinámicas viven fuera de `Base.metadata` a propósito. Sin el filtro
> `_include_object`, **`alembic revision --autogenerate` las ve solo en la base y
> propone DROPearlas todas** (tablas e índices).

El filtro excluye lo que matchea `^(ind_.+|sig_\d+|strat_res_\d+)$` **y** no está en
`target_metadata`, con una rama aparte para los índices que mira el nombre de la
tabla padre. La doble condición salva a `ind_asset_meta`, que matchea el regex pero
sí es un modelo. De ahí una trampa fina: un modelo nuevo con prefijo `ind_` que se
olvide de importar en `app/models/__init__.py` queda fuera de `target_metadata` y el
filtro lo vuelve invisible al autogenerate, en silencio.

Dos convenciones cierran el módulo. Las migraciones que crean tablas anchas
**repiten las listas de códigos** en vez de importar `indicator_store._WIDE`: son
autocontenidas a propósito, porque una migración importaría el modelo de hoy y no el
de cuando se escribió — un indicador nuevo va con `ALTER TABLE ADD COLUMN`, no
tocando la 0077. Y las migraciones de datos llevan un guard
`op.get_context().as_sql` **adentro**, que saltea el pivot y deja que su DDL igual
se renderice offline en ambos dialectos. El refactor ancho se hizo con el patrón
crear → poblar → dropear (0077-0079 técnicas, 0081-0082 fundamentales), con las
viejas como red de rollback y el DROP marcado como punto de no retorno; la 0078 se
reescribió antes de mergear, porque su primera versión con INSERT … ON CONFLICT por
código generaba el mismo bloat de ~Nx que exigía VACUUM FULL.
