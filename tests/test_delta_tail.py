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
    _BACKFILL_FNS, _BENCHMARK_DEP_CODES, _DELTA_TAIL_MODE, _delta_tail_start,
    _pairs_to_write, _stale_bench_assets,
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


def test_full_sample_no_esta_en_tail_mode():
    # volatility_* y atr_percentile_* reclasifican historia: nunca cola-solamente
    for code in _DELTA_TAIL_MODE:
        assert not code.startswith("volatility")
        assert not code.startswith("atr_percentile")


def test_benchmark_dep_codes_estan_en_tail_mode():
    # el chequeo de staleness solo tiene sentido para códigos con camino rápido
    for code in _BENCHMARK_DEP_CODES:
        assert code in _DELTA_TAIL_MODE


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
