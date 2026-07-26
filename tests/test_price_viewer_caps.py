"""Topes de la VISTA en el visor de precios: la DataTable manda todas las
filas al navegador aunque pagine, así que la pantalla corta y lo dice. Los
topes son de presentación — el cálculo sigue leyendo la serie entera.
"""
import sys
import types

# Esta PC de desarrollo no tiene yfinance (ver CLAUDE.md) y el callback lo
# arrastra vía asset_service → app.sources.yahoo; los helpers bajo prueba no
# lo tocan, así que alcanza con un módulo vacío para que importe.
sys.modules.setdefault("yfinance", types.ModuleType("yfinance"))

from app.callbacks.price_viewer_callbacks import (  # noqa: E402
    _history_info, _miles, _tail,
)


def test_la_cola_se_queda_con_los_registros_MAS_NUEVOS():
    """En una serie ordenada por fecha, lo último es lo que interesa."""
    rows = [{"date": f"2026-01-{d:02d}"} for d in range(1, 11)]

    shown, capped = _tail(rows, 3)

    assert [r["date"] for r in shown] == ["2026-01-08", "2026-01-09", "2026-01-10"]
    assert capped is True


def test_sin_exceso_no_hay_corte_ni_copia_recortada():
    rows = [{"date": "2026-01-01"}, {"date": "2026-01-02"}]

    shown, capped = _tail(rows, 5)

    assert shown == rows
    assert capped is False


def test_el_info_declara_el_rango_completo_aunque_muestre_menos():
    """El usuario tiene que ver que la serie arranca en 2004 aunque en pantalla
    solo entren las últimas filas: si no, parece que faltan precios."""
    info = _history_info(5213, "2004-01-02", "2026-07-24", 2000)

    assert "5.213 registros" in info
    assert "2004-01-02 → 2026-07-24" in info
    assert "mostrando los últimos 2.000" in info


def test_sin_corte_el_info_no_menciona_tope():
    info = _history_info(120, "2026-01-02", "2026-07-24", 120)

    assert info == "120 registros — 2026-01-02 → 2026-07-24"


def test_separador_de_miles_rioplatense():
    assert _miles(10000) == "10.000"
    assert _miles(999) == "999"
    assert _miles(1234567) == "1.234.567"
