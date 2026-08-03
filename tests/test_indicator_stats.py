"""Distribución de un indicador entre activos (indicator_stats_service).

Lógica pura: los estadísticos y la forma de la respuesta, sin tocar la base.
Es lo que sostiene la calibración de los cortes de una señal — si los
percentiles mienten, los umbrales que salgan de ellos también.
"""
import datetime

import pytest

from app.services import indicator_stats_service as st


# ── Numérico ──────────────────────────────────────────────────────────────────

def test_percentiles_y_extremos():
    r = st.resumen_numerico(list(range(1, 101)), total_activos=100)
    assert r["n"] == 100
    assert r["min"] == 1 and r["max"] == 100
    assert r["percentiles"]["p50"] == pytest.approx(50.5)
    assert r["percentiles"]["p10"] == pytest.approx(10.9)
    assert r["percentiles"]["p90"] == pytest.approx(90.1)


def test_cobertura_es_sobre_el_total_de_activos_no_sobre_los_que_tienen_dato():
    """La cobertura es LA trampa del catálogo: una señal sin valor no castiga,
    se saltea y renormaliza los pesos. Medirla contra los que sí tienen dato
    daría siempre 100% y taparía justo lo que hay que ver."""
    r = st.resumen_numerico([1.0] * 50, total_activos=200)
    assert r["n"] == 50
    assert r["cobertura_pct"] == 25.0


def test_descarta_no_numericos_y_no_finitos():
    r = st.resumen_numerico([1.0, "hola", None, float("nan"), float("inf"), 3.0],
                            total_activos=6)
    assert r["n"] == 2
    assert r["media"] == pytest.approx(2.0)


def test_sin_valores_lo_dice_en_vez_de_devolver_ceros():
    """Cero no es lo mismo que "no hay dato": devolver estadísticos en cero
    haría creer que el indicador vale cero en toda la base."""
    r = st.resumen_numerico([], total_activos=10)
    assert r["n"] == 0 and r["cobertura_pct"] == 0.0
    assert "nota" in r
    assert "percentiles" not in r


# ── La escala tentativa ───────────────────────────────────────────────────────

def test_saturacion_cuenta_lo_que_el_clamp_recortaria():
    valores = list(range(0, 101))          # 0..100
    r = st.resumen_numerico(valores, 101, escala={"min": 20, "max": 80})
    sat = r["escala_propuesta"]
    assert sat["pct_debajo_del_rango"] == pytest.approx(20 / 101 * 100, abs=0.01)
    assert sat["pct_encima_del_rango"] == pytest.approx(20 / 101 * 100, abs=0.01)
    assert sat["pct_saturado"] == pytest.approx(40 / 101 * 100, abs=0.01)
    assert sat["pct_dentro"] == pytest.approx(61 / 101 * 100, abs=0.01)


def test_una_escala_invertida_recorta_lo_mismo():
    """min > max es cómo se invierte una señal (SPEC §4). El intervalo
    recortado es el mismo: lo que cambia es hacia qué lado puntúa, no quién
    queda afuera. Si esto se rompiera, calibrar una señal invertida daría
    números al revés."""
    valores = list(range(0, 101))
    normal = st.resumen_numerico(valores, 101, escala={"min": 20, "max": 80})
    invert = st.resumen_numerico(valores, 101, escala={"min": 80, "max": 20})
    assert (invert["escala_propuesta"]["pct_saturado"]
            == normal["escala_propuesta"]["pct_saturado"])
    assert invert["escala_propuesta"]["min"] == 80, "se reporta como la escribieron"


def test_escala_degenerada_se_rechaza():
    with pytest.raises(ValueError, match="iguales"):
        st.resumen_numerico([1.0, 2.0], 2, escala={"min": 5, "max": 5})


def test_escala_sin_min_o_max_se_rechaza():
    with pytest.raises(ValueError, match="min"):
        st.resumen_numerico([1.0], 1, escala={"min": 5})


# ── Categórico ────────────────────────────────────────────────────────────────

def test_categorias_ordenadas_por_frecuencia():
    valores = ["bullish"] * 5 + ["lateral"] * 3 + ["bearish"]
    r = st.resumen_categorico(valores, total_activos=18)
    assert r["n"] == 9
    assert r["cobertura_pct"] == 50.0
    assert [c["valor"] for c in r["categorias"]] == ["bullish", "lateral", "bearish"]
    assert r["categorias"][0]["pct"] == pytest.approx(55.56, abs=0.01)
    assert r["categorias_distintas"] == 3


def test_categorico_ignora_los_faltantes():
    r = st.resumen_categorico(["alta_corta", None, None], total_activos=3)
    assert r["n"] == 1


# ── Fechas ────────────────────────────────────────────────────────────────────

def test_parse_fecha_acepta_iso_date_y_datetime():
    """El indicador se lee comparando contra una columna `date`. Si llega el
    string sin convertir, en PostgreSQL la comparación no filtra como uno
    espera y el síntoma es "no hay datos", no un error — ya pasó en producción
    en la pantalla de backtest."""
    assert st.parse_fecha("2026-07-31") == datetime.date(2026, 7, 31)
    assert st.parse_fecha(datetime.date(2026, 7, 31)) == datetime.date(2026, 7, 31)
    assert st.parse_fecha(datetime.datetime(2026, 7, 31, 15, 4)) == datetime.date(2026, 7, 31)
    assert st.parse_fecha(None) is None


def test_parse_fecha_rechaza_basura_con_el_formato_esperado():
    with pytest.raises(ValueError, match="AAAA-MM-DD"):
        st.parse_fecha("31/07/2026")
