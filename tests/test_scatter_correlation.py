"""Correlación de la pantalla de dispersión y de la solapa Correlación de
Análisis de Pares.

Se calcula sobre RETORNOS, no sobre precios: correlacionar niveles mide
recorrido compartido y da coeficientes altísimos entre activos que
simplemente subieron con el mercado. Estos tests fijan esa semántica —
antes se usaba np.corrcoef sobre los cierres.
"""
import math

from app.services.scatter_service import returns_correlation


# Retornos VARIABLES a propósito: una serie de retorno constante tiene desvío
# cero y la correlación queda indefinida (returns_correlation devuelve None).
_RET_A = [0.10, -0.05, 0.08, -0.02]      # los retornos que modelan las series


def _serie(inicial: float, retornos: list[float]) -> list[float]:
    precios = [inicial]
    for r in retornos:
        precios.append(precios[-1] * (1 + r))
    return precios


def test_series_que_se_mueven_igual_dan_correlacion_uno():
    a = _serie(100, _RET_A)
    b = _serie(50, _RET_A)           # mismos retornos, otro nivel de precio
    corr = returns_correlation(a, b)
    assert corr is not None and math.isclose(corr, 1.0, abs_tol=1e-9)


def test_series_que_se_mueven_al_reves_dan_correlacion_menos_uno():
    a = _serie(100, _RET_A)
    b = _serie(100, [-r for r in _RET_A])
    corr = returns_correlation(a, b)
    assert corr is not None and math.isclose(corr, -1.0, abs_tol=1e-9)


def test_tendencia_compartida_sin_movimientos_comunes_no_infla_la_correlacion():
    """El caso que motivó el cambio.

    Dos series que suben de punta a punta, pero cuyos movimientos diarios van
    alternados. Sobre PRECIOS la correlación da casi 1 (ambas suben); sobre
    retornos queda claro que no se mueven juntas.
    """
    a = [100, 104, 106, 110, 112, 116]
    b = [200, 202, 208, 210, 216, 218]

    import numpy as np
    corr_precios = float(np.corrcoef(a, b)[0, 1])
    corr_retornos = returns_correlation(a, b)

    assert corr_precios > 0.95, "la serie de precios debe verse casi perfecta"
    assert corr_retornos is not None
    assert corr_retornos < corr_precios - 0.5, (
        "sobre retornos la correlación tiene que caer mucho respecto de la de "
        "precios: es el sesgo que el cambio corrige")


def test_pocos_puntos_devuelve_none():
    assert returns_correlation([100, 110], [50, 55]) is None
    assert returns_correlation([], []) is None
    assert returns_correlation(None, None) is None


def test_largos_distintos_devuelve_none():
    assert returns_correlation([100, 110, 120], [50, 55]) is None


def test_serie_constante_devuelve_none_en_vez_de_nan():
    """Una serie plana tiene desvío cero: la correlación es indefinida.
    numpy devolvería nan con un RuntimeWarning; acá se corta antes."""
    assert returns_correlation([100, 100, 100, 100], [50, 55, 60, 66]) is None


def test_precios_no_positivos_se_descartan_sin_romper():
    """Un cero en la serie haría explotar el cociente."""
    a = [0] + _serie(100, _RET_A)
    b = [10] + _serie(50, _RET_A)
    corr = returns_correlation(a, b)
    assert corr is not None and math.isclose(corr, 1.0, abs_tol=1e-9)


def test_nunca_devuelve_nan():
    for a, b in [([100, 100, 100], [1, 2, 3]),
                 ([1, 2, 3], [5, 5, 5]),
                 ([0, 0, 0, 0], [1, 2, 3, 4])]:
        corr = returns_correlation(a, b)
        assert corr is None or corr == corr
