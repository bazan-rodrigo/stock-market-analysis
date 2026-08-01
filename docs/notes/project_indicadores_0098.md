---
name: project_indicadores_0098
description: "31-jul/1-ago: price_position_52w + adx_* + rvol_daily (migración 0098, pusheado 05edf82, 1227 passed). El hallazgo grande NO fue un indicador sino que el score de estrategia RENORMALIZA ante dato faltante mientras el filtro EXCLUYE — asimetría que recién importa ahora que hay un indicador de cobertura parcial. PENDIENTE Railway: upgrade + recálculo"
metadata: 
  node_type: memory
  type: project
  originSessionId: 1b45f51d-7422-49be-9e79-dbf346e4ef24
  modified: 2026-08-01T03:48:48.585Z
---

Sesión del 31-jul/1-ago-2026 (commit 05edf82, 1227 passed). Arrancó como
"otra IA me recomendó estos 10 indicadores, ¿qué opinás?" y terminó en tres
implementados.

## El criterio de admisión del catálogo (la respuesta a "¿por qué el MACD no entra?")

El usuario intuía que los indicadores multi-valor como el MACD no encajan. Es
correcto, pero **el motivo no es "muchos valores"**: las tres fórmulas de
`signal_engine` toman un escalar, y como el ranking es transversal ese escalar
tiene que ser **comparable entre activos** (un umbral fijo sobre un valor no
normalizado clasifica mal por construcción). El MACD falla por las dos —tres
series, y en unidades de precio— igual que el ATR absoluto.

Corolario que sí importa: **un compuesto entra si lo que se persiste es la
reducción escalar**. Bollinger Width = `4σ/SMA20` es adimensional y es un solo
número; el "Bollinger descartado" del hilo anterior era el *panel de tres
bandas del gráfico*, otra cosa. Ver [[project_indicadores_con_historia]].

## De las 10 propuestas: 3 implementadas, 2 ya existían, 1 era un error

- **Implementados**: `price_position_52w` (252 barras, solo diaria),
  `adx_{daily,weekly,monthly}`, `rvol_daily`.
- **`distance_all_time_high` YA EXISTÍA**: es `drawdown_current`
  (`_cur_drawdown_current` mide contra el máximo de toda la serie). Al pasar se
  detectó que su descripción del seed dice *"recent peak"* y **miente** — no se
  arregló en este commit.
- **`breakout_score` es un error arquitectónico**, no una feature: combinar
  resistencia + volumen + ATR con pesos *es* la definición de estrategia, y la
  fórmula `composite` se removió del motor justamente para eso. Como indicador
  congelaría en Python pesos que hoy el usuario edita.
- **Toques de soporte**: descartado, hereda entero el lookahead de los pivotes
  centrados de `compute_sr_from_df` (ya decidido en el hilo anterior).

## EL HALLAZGO: score renormaliza, filtro excluye

Lo más valioso de la sesión no es ningún indicador. Al preguntarle al código
qué pasa con un activo sin dato:

- **`_compute_asset_score` SALTEA el componente y no suma su peso** → los pesos
  se renormalizan sobre los que sí puntuaron. El activo **no queda excluido**:
  compite con una fórmula distinta, y como el componente que le falta tampoco
  puede castigarlo, **le va sistemáticamente mejor**. Con 2 componentes de peso
  1: real (+80, −60) = 10; sin dato (+80, —) = 80. Gana por carecer del dato.
- **`_compare` devuelve False ante `left is None`** → el filtro de elegibilidad
  sí excluye.

Las dos son razonables por separado y son **opuestas**. Nunca importó porque
ningún indicador faltaba por familia de activos; `rvol_daily` es el primero
(sintéticos y conversiones de moneda no tienen volumen propio — el usuario
decidió explícitamente "que no se les calcule"). Documentado en `SPEC.md` §5 y
en el glosario del manual como regla de armado de packs.

## Decisiones de implementación que costaron pensar

- **ADX con período FIJO 14, no `vol_cfg.atr_period`** → queda FUERA de
  `_CHECKSUM_DEP_CODES` (como `rsi_*`: recursivo pero sin config editable
  detrás). Lo que mete a `atr_pct_*` en ese frozenset es principalmente su
  período editable. Anotado en el código por si alguien lo ata a la config.
- **`shift(1)` en RVOL**: sin él una barra excepcional infla su propio
  denominador y se amortigua sola. Test que lo fija numéricamente (10,0 vs
  ~6,9).
- **`volume` a float32** en los cargadores: la mitad de memoria en el df que
  viaja al ProcessPool; el error relativo ~1e-8 es invisible en un cociente
  redondeado a 2 decimales.
- **Trampa encontrada**: `compute_current_indicators` escribe la fila COMPLETA
  por cadencia → un código de `_WIDE` ausente de su dict **pisa con NULL** lo
  que dejó el backfill, todos los días. No estaba en el plan.
- **No hay problema de warm-up** con la ventana de 252: `compute_fn` recibe
  siempre el df COMPLETO; el modo `"series"` del delta afecta qué se *escribe*,
  no qué se *calcula*.

## Medición (scripts/bench_indicadores_0098.py, local, cota superior)

El cómputo de backfill se encarece **26-30%** (dos configs, deriva 1,7-2,1%),
de lo cual **el 84% es el ADX**; `price_position_52w` y `rvol_daily` son casi
gratis (0,70 y 0,42 ms/activo). RVOL, el que más me preocupaba en el plan,
resultó el más barato.

Es **cota superior**: el baseline del banco está subestimado a su favor
(`dist_optimal_sma_*` cae a su camino corto sin `best_sma_*`,
`relative_strength_52w` excluido). **No mide** I/O ni escritura → el impacto
sobre el delta completo es menor, y NO lo estimé: es el error de "las partes
aisladas no suman el todo" que ya costó tres estimaciones malas
([[project_scaling_target]]).

Efecto lateral observado, **preexistente y no introducido acá**: las cadencias
semanales cuestan MÁS que las diarias pese a tener 5× menos barras
(`adx_weekly` 2,33 vs `adx_daily` 1,90; ya pasaba con `rsi_*` y `atr_pct_*`).
Es overhead fijo de pandas en `_wilder_smooth`; hay una optimización disponible
que beneficiaría a todo el catálogo.

## PENDIENTE en Railway

`alembic upgrade head` (0098) y después **"Recalcular completo"** de los cinco
códigos — las columnas nacen NULL. Nada de esto se probó contra datos reales:
el ADX no está contrastado contra una fuente externa y `rvol_daily` nunca vio
la columna `volume` de verdad (es su primer consumidor).

Relacionado: [[project_ind_wide_tables]], [[project_reduccion_footprint]]
(~100 MB por indicador diario a 10.000 activos), [[project_packs_estandar]]
(el SPEC que ahora documenta la regla), [[project_pendientes]].
