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


# ── Histograma ────────────────────────────────────────────────────────────────

def test_el_histograma_recorta_las_colas_para_dibujar_pero_las_informa():
    """Un solo activo extremo (se midió un volumen relativo de 162 contra una
    mediana de 1) estira el eje y aplasta toda la masa en la primera barra: el
    gráfico queda vacío y parece que no hay datos. Se recorta para dibujar y se
    dice cuántos quedaron afuera, que son justo los que un clamp satura."""
    valores = list(range(1, 200)) + [100000]
    h = st.histograma(valores, bins=10)
    assert h["fuera_der"] >= 1
    assert sum(h["conteos"]) >= 190
    assert h["bins"][-1] < 1000, "el extremo no puede estirar el eje"


def test_histograma_con_todos_los_valores_iguales_no_revienta():
    h = st.histograma([5.0] * 20, bins=10)
    assert sum(h["conteos"]) == 20


def test_histograma_sin_valores():
    assert st.histograma([])["conteos"] == []


# ── Distribución del puntaje ──────────────────────────────────────────────────

def test_los_scores_muestran_la_saturacion_en_los_dos_topes():
    """La vista más directa de una escala mal puesta: los picos en ±100."""
    valores = [-50, -20, 0, 20, 50]          # escala de -10 a 10 → casi todo satura
    r = st.resumen_de_scores(valores, "range", {"min": -10, "max": 10})
    assert r["pct_en_tope"] == 40.0          # 20 y 50
    assert r["pct_en_piso"] == 40.0          # -20 y -50


def test_los_scores_cuentan_aparte_a_los_que_la_formula_no_puntua():
    """Una categoría fuera del mapa NO vale cero: deja al activo sin ese
    componente y le renormaliza los pesos a favor. Contarla como cero sería
    exactamente el error que la señal comete en silencio."""
    r = st.resumen_de_scores(["bullish", "lateral", "inesperada"],
                             "discrete_map", {"map": {"bullish": 100, "lateral": 0}})
    assert r["n"] == 2 and r["sin_puntaje"] == 1


def test_los_empates_de_un_threshold_se_ven_y_no_los_muestra_ninguna_otra_medida():
    """El ranking es transversal: un `threshold` de pocos tramos parte el
    universo en bloques y adentro de cada bloque la señal no ordena nada.

    Este es el caso que ninguna otra métrica agarra: las dos fórmulas de abajo
    tienen la MISMA saturación (cero) y el threshold tiene hasta más recorrido
    de cuartil central, así que por esos dos números parecería la mejor. Los
    puntajes distintos son 5 contra 101."""
    valores = list(range(0, 101))
    continua = st.resumen_de_scores(valores, "range", {"min": -200, "max": 200})
    tramos = st.resumen_de_scores(valores, "threshold", {"thresholds": [
        [80, 90], [60, 45], [40, 0], [20, -45], [None, -90]]})

    assert continua["pct_en_tope"] == tramos["pct_en_tope"] == 0.0
    assert continua["pct_en_piso"] == tramos["pct_en_piso"] == 0.0
    assert tramos["recorrido_iqr"] >= continua["recorrido_iqr"]

    assert tramos["puntajes_distintos"] == 5
    assert continua["puntajes_distintos"] == 101
    assert tramos["pct_distintos"] < 5 < continua["pct_distintos"]
