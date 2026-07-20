---
slug: pruebas-y-medicion
title: Como se prueba y como se mide el rendimiento
chapter: Anexo tecnico
order: 1095
roles: admin
---

Son dos preguntas distintas y el proyecto las resuelve con herramientas
distintas: **¿cómo sé que no rompí nada?** lo contesta pytest, y **¿cómo sé que
mejoré algo?** lo contesta un método de medición con cuatro pasos y bastante
historia de haber medido mal.

Lo que las une es que ninguna está automatizada por infraestructura. No hay CI,
no hay pipeline, no hay git hooks. La red es humana: correr la suite antes de
cada push.

## La suite: cientos de tests que nunca tocan la base

La suite supera los **800 tests, repartidos en más de 60 archivos, y corre
completa en menos de un minuto** en la PC de desarrollo. El número exacto hay
que sacarlo del comando (`pytest --collect-only -q`), no de la documentación —
tampoco de esta: `CLAUDE.md` dice "~400" y `docs/notes/project_testing.md` dice
"710", los dos desactualizados y con valores distintos entre sí. Todo conteo
escrito envejece; el comando no.

La configuración es deliberadamente mínima. `pytest.ini` tiene tres líneas
(`testpaths` y `-q`): sin markers, sin plugins, sin cobertura — el proyecto no
mide cobertura. Las dependencias de test viven aparte, en `requirements-dev.txt`
(`pytest` y `hypothesis`), así que producción no las instala. Eso tiene una
consecuencia visible: el panel de verificación trata "pytest no está instalado"
como un caso distinto de "fallan tests".

**Toda la suite es de lógica pura y jamás toca una base real.** El mecanismo está
en `tests/conftest.py`, y el detalle importante es que **fuerza**
`DATABASE_URL` hacia un stub sqlite antes de importar nada de `app` — no usa
`setdefault`. Si encuentra una URL real, imprime un aviso a stderr y la ignora
igual.

> Si estás debuggeando "por qué mis tests no ven mi base de desarrollo": nunca la
> van a ver, por diseño, y hay dos mecanismos independientes para garantizarlo.

La razón no es teórica. El fixture de `tests/test_affected_by_new_assets.py` hace
`DELETE FROM assets` sin ningún filtro, y `prices` e `ind_*` tienen `ON DELETE
CASCADE` sobre `assets`: con una URL real en el entorno, `setdefault` la habría
respetado y la suite habría vaciado la base entera. **Pasó de verdad.** El commit
`5690052` corrige exactamente eso, y la evidencia forense fue una tabla
`ind_zz_test_explorer` que apareció en producción y que solo pudo haber creado
pytest.

El segundo cinturón es el hook `pytest_sessionstart`, que importa el engine y
aborta la sesión con `returncode=3` si el dialecto no quedó en sqlite. Corre
antes de la colección y de cualquier fixture, así que cuando aborta todavía no se
ejecutó ninguna sentencia. Su docstring se llama a sí mismo "cinturón además de
tiradores": el forzado ya alcanza hoy, el hook protege contra la regresión de
mañana.

Dos detalles más de `conftest.py`. El stub sqlite es **descartable**: se borra en
cada corrida, porque `create_all` no altera tablas existentes y un stub viejo
daría fallos fantasma tras agregar una columna a un modelo. Y si el borrado falla
en Windows con WinError 32 (dos corridas en paralelo, un handle colgado), cae a
un stub por PID en vez de abortar la colección entera.

> La suite corre con `USE_WIDE_IND_TABLES=0`, o sea por el camino per-código,
> mientras que producción usa tablas anchas. El camino default de producción
> **no** es el que ejercita la mayoría de la suite: solo los de la familia
> `wide_*` lo revierten con monkeypatch.

## Los patrones que vale la pena conocer

**Verificar el ORDEN, no el cálculo.** `tests/test_indicator_pipeline_order.py`
stubea con monkeypatch todo lo pesado (`get_session`,
`recompute_current_indicators`, `backfill_all_indicator_values`) y el assert
completo es `calls == ["current", "backfill"]`. Existe porque hubo un bug real de
secuencia: `dist_optimal_sma_*` depende de `best_sma_*`, y calcularlo antes usaba
el valor de la corrida anterior. Era un bug de orden, no de fórmula, así que no
hace falta ejecutar ningún cálculo para blindarlo.

**El contrato ejecutable.** `tests/fixtures/trade_simulator_cases.json` tiene 35
casos y es el único fixture del repo. Existe porque la semántica del
[simulador de trades](/manual/simulador-de-trades) vive duplicada en Python y en
JavaScript a propósito: cambiar un caso del JSON es cambiar la semántica, y
obliga a tocar ambas implementaciones en el mismo commit. El test no solo compara
la salida esperada; además verifica invariantes sobre todos los casos (que
`exit_idx > entry_idx`, que el retorno sea consistente con los cierres, que haya
a lo sumo un trade abierto y solo al final), así que un caso mal escrito no se
cuela aunque el autor ponga un `expected` equivocado.

**La familia de paridad**, que es cómo se hacen refactors grandes sin miedo. Son
cinco variantes del mismo truco: guardar la implementación vieja como oráculo y
exigir igualdad. Rango contra por-fecha (`test_signal_range_parity.py`), SQL de
MySQL byte-idéntico al histórico (`test_db_compat.py`, que compila offline los
dialectos con binds falsos que nunca conectan), Python contra JavaScript
(`test_paridad_grafico.py`, `test_paridad_zonas.py`), evaluador compilado contra
interpretado (`test_signal_engine_compile.py`) y tabla ancha contra per-código
(`test_wide_cutover.py`). En los de paridad las funciones `_ref_*` son copias
**literales** de la versión anterior, conservadas dentro del test: la versión
lenta y obviamente correcta queda como referencia ejecutable para siempre, no
enterrada en el historial de git.

**Meta-tests estructurales**, que no prueban lógica sino configuración.
`test_module_registration.py` lee `app/__init__.py` como texto y verifica que
toda página con `register_page(` esté citada en `_PAGES` — porque sin
auto-discovery, un módulo sin registrar da 404 en silencio (pasó con
`/backtest`). `test_manual_coverage.py` ata la documentación al código en ambas
direcciones y además caza slugs duplicados, `order` repetidos, roles mal escritos
y enlaces internos rotos. Los tres son fallos silenciosos: un rol mal escrito
degrada a visible-para-todos sin avisar. `test_bootstrap_portability.py` renderiza
las migraciones post-freeze contra `mysql://` y `postgresql://` sin base ni
driver, y atrapa backticks o `AUTO_INCREMENT` crudo antes del deploy (ver
[soporte dual](/manual/soporte-dual-de-base-de-datos)).

**Property-based con Hypothesis**, en exactamente dos archivos y con
justificación empírica. `test_delta_tail_properties.py` nació de un bug de
`_checksum_prefix` que los tests de ejemplo no encontraron y que apareció con
datos reales; `test_signal_engine_compile.py` exige identidad exacta entre el
evaluador compilado y el interpretado —incluyendo `None`, `NaN` y la igualdad
exacta de floats— porque esa optimización corre en el loop caliente del backfill
y cualquier divergencia sería un bug de datos silencioso en toda la historia de
señales. Ambos con 300 ejemplos por propiedad.

## Nada obliga a correrla

No hay `.github/`, no hay workflows, y `.git/hooks` solo tiene los `.sample` de
fábrica. La regla "correr la suite antes de cada push" es una convención escrita
y nada la verifica: un push sin tests pasa sin resistencia.

Lo que sí existe es un botón en `/admin/verify` que lanza pytest como subprocess
desde la app, en un thread daemon con timeout de 300 s y polling cada segundo.

> Ese subprocess hereda el entorno del proceso de la app, incluida su
> `DATABASE_URL` de producción. Es literalmente el escenario contra el que existe
> el forzado de `conftest.py`: sin él, apretar ese botón vaciaría la base.

## La tercera red: verificar contra datos reales

`app/services/verification_service.py` hace algo que pytest estructuralmente no
puede: compara los valores **guardados en la base real** contra un recálculo
fresco desde cero, para una muestra de activos. Es solo-lectura —nunca escribe,
nunca trunca— y por eso es seguro contra producción. Pytest valida fórmulas sobre
datos sintéticos en sqlite; esto valida que el caché del delta (tail-mode,
checksums) no haya corrompido datos reales acumulados durante meses. Lo consumen
la CLI `scripts/verify_delta_correctness.py` y la pantalla de
[Verificación de datos](/manual/verificacion-de-datos).

Además hace chequeos de **cordura** independientes, y el porqué de que los dos
hagan falta está bien explicado en el propio docstring:

> Comparar el delta contra un recálculo fresco nunca puede detectar una fórmula
> equivocada: ambos lados usan la misma fórmula y coinciden en el mismo valor
> incorrecto. La comparación agarra bugs de caché; la cordura (RSI fuera de
> [0,100], una categoría desconocida, un retorno de +50000%) agarra bugs de
> fórmula.

Los límites son deliberadamente laxos: el objetivo es atrapar lo obviamente roto,
no discutir si un valor extremo pero real es razonable. Las tolerancias están
calibradas contra el **almacenamiento**, no contra el cálculo: `_TOL = 0.01`
(el mismo `.round(2)` que usa el sistema) más `_REL_TOL = 1e-4`, porque
`ind_fundamental_*` guarda en una columna `Float` de precisión simple y un ratio
en pesos de seis cifras pierde más de 0.01 en el redondeo de la propia columna.
Sin esa tolerancia relativa, los activos en monedas de alta denominación darían
falsos positivos permanentes y la herramienta se volvería ruido ignorable.

## Medir: el método en cuatro pasos

El método está consolidado en `docs/notes/project_scaling_target.md` y la
advertencia es no confundir los pasos:

1. **cProfile** dice **dónde** mirar. Nunca cuánto tarda.
2. **Leer el código** dice **qué** es el desperdicio. Es el paso que da certeza y
   no depende de que la medición sea precisa.
3. **Medir contra la base real** dice **cuánto** vale arreglarlo. Lo único que
   decide.
4. **Verificar que el resultado no cambie** — el paso que casi se saltea.

No es teoría: las dos reversiones documentadas salieron de saltar del paso 1 al 3
sin el paso 2.

**cProfile infla los tiempos entre 3.7x y 4.2x en este código**, y hay dos
mediciones independientes que convergen: el lote delta daba 69.2 s con profiler
contra 18.7 s reales, y `verify_asset_code` daba 1113 ms contra 268 ms reales.
El sesgo apunta siempre en la dirección equivocada, porque el profiler instrumenta
cada llamada y exagera justo lo que se llama millones de veces, que es lo que uno
está buscando optimizar. Eso produjo un overclaim que después hubo que corregir:
"la comparación es ~85% del costo" salía de la tabla del profiler; el valor real
medido fue ~54%.

Por eso existe el flag `--raw`, que corre el mismo trabajo sin instrumentar y es
el número contra el cual se juzgan las optimizaciones. Solo lo tienen 2 de los 14
profilers (`profile_pool_batch.py` y `profile_verification.py`), justamente los
acoplados a la base real.

> El total con profiler no solo está inflado: está inflado **desparejo entre
> versiones**. Dos implementaciones con distinta cantidad de llamadas se inflan
> distinto, así que ni el cociente antes/después es confiable.

Varios profilers corren **single-thread a propósito** (`profile_vol_zones.py` es
el patrón original que el resto copia). Si se perfilara el pool completo, el
tiempo por función mezclaría cómputo con espera de GIL y no se distinguiría "esta
función es cara" de "esta función esperó su turno". La excepción es
`profile_pool_concurrency.py`, que mide el mismo trabajo secuencial contra N
threads justamente para medir el efecto del GIL, y que declara en su docstring
cómo interpretar cada resultado posible **antes** de correrlo — hipótesis y
criterio de falsación escritos de antemano (ver
[concurrencia](/manual/concurrencia-y-multihilo)).

Tampoco se mide en producción: contenedores efímeros con CPU variable hacen que
comparar corridas de sesiones distintas sea ruido, y encima `profile_pool_batch`
escribe de verdad. El lugar de medición es el Codespace.

## El patrón de benchmark que decide si algo queda

Los `profile_*` (14) dicen dónde mirar; los `bench_*` (3) deciden si una
optimización queda o se revierte. El patrón es siempre el mismo: **cronometrar
ambas versiones en el mismo proceso, sobre datos reales leídos de la base,
verificando primero que las salidas sean idénticas**.

Nació de un problema concreto. El A/B clásico —correr el lote entero antes y
después, con `git checkout` en el medio— exige git y una máquina estable, y eso
es imposible en producción. Los `bench_*` lo esquivan midiendo las dos
implementaciones una al lado de la otra: mismo hardware, misma sesión, mismos
datos. Como son solo-lectura, corren en cualquier entorno.

La verificación de equivalencia va primero y aborta si algo se movió:
`bench_verify_asset_code.py` compara las listas de diffs código por código y
frena si la semántica cambió un milímetro; `bench_series_checksum.py` aborta si
alguna versión no es determinista. Es el paso 4 del método incorporado al
instrumento: no se puede reportar un speedup de algo que ya no hace lo mismo.

También se ocupan de reproducir la **forma** real de los datos.
`bench_series_checksum.py` reconstruye cada serie contra el calendario de precios
del activo para replicar la densidad real de nulos, que es exactamente lo que el
benchmark sintético estaba representando mal.

## Lo que la medición desmintió

Dos optimizaciones fueron **revertidas** después de medirlas bien, y las dos se
pueden verificar hoy en el código:

- **`d607273`** hasheaba bytes crudos en `_series_checksum`. El benchmark
  sintético daba **14x**. Sobre datos reales dio 1.19-1.40x en series numéricas
  y **0.52-0.56x —o sea, más lento— en las de texto**, con un ahorro de
  0.14-0.44 s sobre un lote de ~19 s: entre 0.7% y 2.3%. Revertido en `c816446`;
  `_series_checksum` es hoy la versión vieja, un `str()` por valor.
- **`2589e2d`** vectorizaba las conversiones de fecha de
  `_bf_relative_strength_52w`. Medido: **1.58 → 3.33 ms, 2x más lento**, y las
  conversiones eran apenas el 7% de la función. Revertido en `61b176e`.

La convención de commits refleja el método: las optimizaciones se commitean con
el sufijo **"(a validar)"** y un commit posterior registra el veredicto.

De las dos reversiones salió una regla predictiva: **eliminar trabajo gana
siempre; re-expresar trabajo solo gana si lo que se reemplaza es caro.**
Vectorizar paga cuando la operación por elemento es un dispatch caro
(`pd.notna` cuesta ~1.3 µs de maquinaria pandas) y no paga cuando ya es una
operación C barata (`math.isnan`, `date.toordinal`). La regla predijo
correctamente la segunda reversión y las notas anotan que se ignoró.

> El contraejemplo más didáctico del repo: **la misma máscara vectorizada ganó
> 1.3-1.8x en `_pairs_to_write` y perdió en `_series_checksum`** (1.603 → 1.689
> ms). Dos patrones que parecen idénticos se comportan al revés.

Y dos trampas más, caras las dos:

> "Salida byte-idéntica" no implica "performance intacta". El camino de texto del
> checksum conservaba el hash exacto y aun así regresó ~2x, por una detección de
> tipo agregada antes que escanea hasta el primer no-nulo. Al tocar una función
> con varios caminos, medir **todos**.

> Un benchmark sintético en este proyecto tiene historial de mentir por 10x,
> siempre para el lado optimista (tres veces en un mismo día). Sirve para
> **descartar** —si no gana ahí, no gana— nunca para confirmar. Si igual se usa
> uno, que modele el peor caso: así solo puede sorprender para bien.

También hay medidas que desmienten intuiciones enteras. Subir `_POOL_WORKERS` de
`cores+2` a `cores+6` **empeoró** el delta de 3m08s a 3m42s: el cuello era
contención de I/O, no falta de paralelismo. Atacar la causa real —precalcular
`tail_stats` secuencialmente antes de lanzar el pool— lo dejó en 2m11s. Y para
medir bloat de escritura en PostgreSQL, `n_dead_tup` y el porcentaje de tuplas
muertas mienten por diseño del motor: el autovacuum los resetea entre la corrida
y la medición. Hay que usar `n_tup_upd`, que es acumulado.

Vale marcar que el hallazgo de performance más grande del proyecto **no salió de
un profiler**: salió de mirar `information_schema.processlist` en vivo durante una
corrida real. cProfile mide cómputo Python, así que un cuello de botella que vive
dentro de la base es invisible ahí.

## Lo que esta red no cubre

- **La suite sobre sqlite no valida portabilidad de SQL crudo.** Ya explotó: un
  `DELETE FROM "tabla"` con comillas dobles es válido en PostgreSQL y sqlite, y
  MariaDB lo rechaza. La suite verde no dice nada sobre si el SQL corre en MySQL.
  Lo mitigan `test_db_compat.py` y `test_bootstrap_portability.py`, pero ninguno
  cubre SQL crudo escrito a mano en un servicio.
- **Las funciones del backtest que tocan BD** (`run_portfolio_backtest` y
  `_load_raw`) no están en la suite: se verifican a mano en el Codespace. Es
  coherente con la regla de no tocar la base, pero es un hueco real.
  (`walk_forward` sí se testea: su única fase con BD es `_load_universe`, que los
  tests monkeypatchean, y se la invoca con una sesión falsa.)
- **No hay registro versionado de las corridas de benchmark.** Los números viven
  en `docs/notes/` y en los mensajes de commit; re-verificar una medición vieja
  implica volver a correrla.
- **Lead de performance abierto:** `build_panels` se reconstruye 12 veces en el
  grid del walk-forward. Está identificado, es del tipo "eliminar trabajo" —el que
  mejor pronóstico tiene— y no está hecho. Se despriorizó por encuadre, no por
  falta de evidencia: el backtest corre bajo demanda, así que pesa menos que el
  pipeline diario. Más en
  [estado y límites conocidos](/manual/estado-y-limites-conocidos).
