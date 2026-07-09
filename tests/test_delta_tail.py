"""Camino rápido del delta: decisión por activo y paridad de escrituras.

_delta_tail_start decide si un activo puede escribir solo la cola
(historial completo) o si cae al camino lento (activo nuevo, hueco
histórico, precios por detrás de lo guardado). La paridad verifica que
el camino rápido escribe lo mismo que el lento más la reescritura de la
última fecha guardada (que pudo calcularse con un precio preliminar).
"""
from datetime import date, timedelta

import pytest

from app.services.technical_service import (
    _BACKFILL_FNS, _BENCHMARK_DEP_CODES, _CHECKSUM_DEP_CODES, _DELTA_TAIL_MODE,
    _confirmed_empty_fast_path, _delta_tail_start, _pairs_to_write,
    _series_checksum, _series_stats, _stale_bench_assets, _stale_dates_to_delete,
)


def _fechas(n, start=date(2025, 1, 1)):
    return [start + timedelta(days=i) for i in range(n)]


# ── Decisión fast/slow ────────────────────────────────────────────────────────

def test_historial_completo_devuelve_indice_de_la_ultima_guardada():
    dates = _fechas(10)
    # guardado d2..d7 sin huecos → cola desde d7 (inclusive)
    stat = (dates[2], dates[7], 6)
    assert _delta_tail_start(dates, stat, "series") == 7


def test_solo_falta_la_cola_es_el_caso_tipico():
    dates = _fechas(10)
    stat = (dates[0], dates[9], 10)      # al día: reescribe solo la última
    assert _delta_tail_start(dates, stat, "series") == 9


def test_hueco_historico_cae_al_camino_lento():
    dates = _fechas(10)
    stat = (dates[2], dates[7], 5)       # faltan filas entre medio
    assert _delta_tail_start(dates, stat, "series") is None


def test_activo_nuevo_cae_al_camino_lento():
    dates = _fechas(5)
    assert _delta_tail_start(dates, None, "series") is None
    assert _delta_tail_start(dates, (None, None, 0), "series") is None


def test_precios_detras_de_lo_guardado_cae_al_camino_lento():
    dates = _fechas(5)
    stat = (dates[0], dates[4] + timedelta(days=3), 5)
    assert _delta_tail_start(dates, stat, "series") is None


def test_zones_ignora_huecos_pero_no_lo_demas():
    dates = _fechas(10)
    con_hueco = (dates[2], dates[7], 5)
    assert _delta_tail_start(dates, con_hueco, "zones") == 7
    assert _delta_tail_start(dates, None, "zones") is None
    detras = (dates[0], dates[9] + timedelta(days=1), 5)
    assert _delta_tail_start(dates, detras, "zones") is None


def test_serie_vacia_cae_al_camino_lento():
    assert _delta_tail_start([], (date(2025, 1, 1), date(2025, 1, 2), 2),
                             "series") is None


# ── _confirmed_empty_fast_path: activos sin datos válidos, confirmados ───────
# (p.ej. best_sma_* inválido en dist_optimal_sma_*, o activo sin benchmark
# en relative_strength_52w) — evita repetir el camino lento para siempre.

def test_confirmado_vacio_y_sigue_vacio_activa_camino_rapido():
    assert _confirmed_empty_fast_path(None, (None, None, 0)) is True


def test_primera_vez_sin_cache_no_activa_camino_rapido():
    # sin cached_stat todavía (primera corrida): debe caer al camino lento
    # normal para confirmarlo por primera vez
    assert _confirmed_empty_fast_path(None, None) is False


def test_vacio_pero_antes_tenia_datos_no_activa_camino_rapido():
    # cached_stat con count>0: transición valor→vacío, debe ir al camino
    # lento para poder borrar/reescribir lo ya guardado
    stat = (date(2025, 1, 1), date(2025, 1, 5), 3)
    assert _confirmed_empty_fast_path(None, stat) is False


def test_ahora_tiene_datos_no_activa_camino_rapido_aunque_antes_no_tuviera():
    # stats ya no es None: la serie se volvió válida, debe ir al camino
    # lento para escribir la serie recién habilitada
    stats = (date(2025, 1, 1), date(2025, 1, 5), 5)
    assert _confirmed_empty_fast_path(stats, (None, None, 0)) is False


# ── _stale_dates_to_delete: valores que dejaron de ser válidos ───────────────
# (p.ej. best_sma_* dejó de encontrar un período válido, o se le quitó el
# benchmark a un activo) — _pairs_to_write nunca borra, así que sin esto la
# fila vieja quedaría representando un cálculo que ya no es válido.

def test_valor_invalido_con_fila_guardada_es_obsoleto():
    dates = _fechas(3)
    vals  = [1.0, None, 3.0]
    existing = {dates[0], dates[1], dates[2]}
    assert _stale_dates_to_delete(dates, vals, existing) == [dates[1]]


def test_valor_invalido_sin_fila_guardada_no_es_obsoleto():
    # nunca se escribió nada para esa fecha: no hay nada que borrar
    dates = _fechas(3)
    vals  = [1.0, None, 3.0]
    existing = {dates[0], dates[2]}
    assert _stale_dates_to_delete(dates, vals, existing) == []


def test_sin_existing_no_hay_obsoletos():
    dates = _fechas(3)
    vals  = [None, None, None]
    assert _stale_dates_to_delete(dates, vals, set()) == []
    assert _stale_dates_to_delete(dates, vals, {}) == []


def test_stale_funciona_con_existing_dict():
    # relative_strength_52w/trend_* usan dict-compare (needs_dict_fallback)
    dates = _fechas(2)
    vals  = [None, 2.0]
    existing = {dates[0]: 1.0, dates[1]: 2.0}
    assert _stale_dates_to_delete(dates, vals, existing) == [dates[0]]


# ── Paridad de escrituras: rápido vs lento ────────────────────────────────────

def test_paridad_cola_vs_camino_lento():
    dates = _fechas(10)
    vals  = [float("nan"), float("nan")] + [float(i) for i in range(2, 10)]
    # guardado d2..d7 (los NaN del warm-up quedan antes de mn)
    stored = set(dates[2:8])
    stat   = (dates[2], dates[7], 6)

    k = _delta_tail_start(dates, stat, "series")
    rapido = _pairs_to_write(dates[k:], vals[k:], set())
    lento  = _pairs_to_write(dates, vals, stored)

    # el rápido escribe lo mismo que el lento + la última guardada (d7),
    # que se reescribe por si su precio era preliminar
    assert rapido == [(dates[7], 7.0)] + lento
    assert lento  == [(dates[8], 8.0), (dates[9], 9.0)]


def test_paridad_con_hueco_el_lento_lo_rellena():
    dates = _fechas(6)
    vals  = [float(i) for i in range(6)]
    stored = {dates[0], dates[1], dates[3]}          # falta d2: hueco
    stat   = (dates[0], dates[3], 3)

    assert _delta_tail_start(dates, stat, "series") is None
    lento = _pairs_to_write(dates, vals, stored)
    assert lento == [(dates[2], 2.0), (dates[4], 4.0), (dates[5], 5.0)]


# ── Consistencia de la configuración ──────────────────────────────────────────

def test_todo_codigo_tail_tiene_funcion_de_backfill():
    for code in _DELTA_TAIL_MODE:
        assert code in _BACKFILL_FNS, code


def test_benchmark_y_checksum_dep_codes_estan_en_tail_mode():
    # el chequeo de staleness solo tiene sentido para códigos con camino rápido
    for code in _BENCHMARK_DEP_CODES | _CHECKSUM_DEP_CODES:
        assert code in _DELTA_TAIL_MODE


def test_checksum_dep_codes_son_los_full_sample():
    # volatility_* y atr_percentile_* reclasifican historia (full_sample):
    # el camino rápido necesita la compuerta de checksum, no alcanza con
    # "sin huecos" como en el resto
    assert _CHECKSUM_DEP_CODES == {
        "volatility_daily", "volatility_weekly", "volatility_monthly",
        "atr_percentile_daily", "atr_percentile_weekly", "atr_percentile_monthly",
    }
    # volatility_* tiene Nones legítimos (zonas sin confirmar); atr_percentile
    # es una serie contigua una vez pasado el warm-up
    for code in _CHECKSUM_DEP_CODES:
        expected = "zones" if code.startswith("volatility") else "series"
        assert _DELTA_TAIL_MODE[code] == expected


# ── _series_checksum: hash del prefijo histórico ─────────────────────────────

def test_checksum_mismos_valores_mismo_hash():
    a = [1.0, 2.0, "alta_larga", None]
    b = [1.0, 2.0, "alta_larga", None]
    assert _series_checksum(a) == _series_checksum(b)


def test_checksum_cambia_si_cambia_un_valor():
    a = [1.0, 2.0, 3.0]
    b = [1.0, 2.5, 3.0]
    assert _series_checksum(a) != _series_checksum(b)


def test_checksum_none_y_nan_son_equivalentes():
    assert _series_checksum([1.0, None, 3.0]) == _series_checksum([1.0, float("nan"), 3.0])


def test_checksum_distingue_bordes_entre_valores():
    # sin separador, ("1","23") y ("12","3") colisionarían al concatenar
    assert _series_checksum(["1", "23"]) != _series_checksum(["12", "3"])


def test_checksum_vacio_es_string_vacio():
    assert _series_checksum([]) == ""


# ── _series_stats: (min_date, max_date, count) cacheado en ind_asset_meta ────

def test_series_stats_serie_completa_sin_nan():
    dates = _fechas(5)
    vals  = [float(i) for i in range(5)]
    assert _series_stats(dates, vals) == (dates[0], dates[4], 5)


def test_series_stats_ignora_warmup_nan_al_principio():
    dates = _fechas(5)
    vals  = [float("nan"), float("nan"), 2.0, 3.0, 4.0]
    assert _series_stats(dates, vals) == (dates[2], dates[4], 3)


def test_series_stats_zones_con_none_legitimo_a_mitad_de_serie():
    dates = _fechas(5)
    vals  = [0.0, None, 2.0, None, 4.0]
    assert _series_stats(dates, vals) == (dates[0], dates[4], 3)


def test_series_stats_serie_vacia_o_toda_nan_es_none():
    assert _series_stats([], []) is None
    dates = _fechas(3)
    assert _series_stats(dates, [None, None, None]) is None


# ── _stale_bench_assets: invalidación por cambio de benchmark ────────────────

def test_benchmark_sin_cambios_no_hay_stale():
    current = {1: 10, 2: 20, 3: None}
    stored  = {1: 10, 2: 20, 3: None}
    assert _stale_bench_assets(current, stored) == set()


def test_benchmark_cambiado_marca_stale():
    current = {1: 10, 2: 99}     # activo 2 cambió de benchmark
    stored  = {1: 10, 2: 20}
    assert _stale_bench_assets(current, stored) == {2}


def test_benchmark_asignado_de_none_a_valor_es_stale():
    current = {1: 10}
    stored  = {1: None}
    assert _stale_bench_assets(current, stored) == {1}


def test_activo_sin_meta_guardada_es_stale():
    # primera corrida tras habilitar el chequeo, o activo nuevo
    current = {1: 10, 2: None}
    stored  = {}
    assert _stale_bench_assets(current, stored) == {1, 2}
