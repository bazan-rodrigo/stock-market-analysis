"""Armado de la grilla del screener (ag-grid): columnas, filas y el contrato
con los renderers de JavaScript.

La grilla reemplazó a una `html.Table` construida a mano. Lo que se testea acá
es lo que se puede testear sin navegador: que las columnas salgan completas y
en orden, que las filas queden planas (la grilla no sabe leer `comp_scores`
anidado) y que los renderers que Python nombra existan del lado JS — un typo
ahí no rompe nada visible desde Python: deja las celdas en blanco.
"""
import re
from pathlib import Path

from app.callbacks.screener_signals_callbacks import (
    _column_defs, _maximos, _row_data,
)

ROOT = Path(__file__).resolve().parent.parent

_META = [
    {"signal_key": "rsi", "signal_name": "RSI sobrevendido", "weight": 2.0},
    {"signal_key": "mm",  "signal_name": "Medias móviles",   "weight": 1.0},
]
_ROWS = [
    {"asset_id": 1, "ticker": "AAA", "name": "Activo A", "score": 80.0,
     "delta_score": 1.5, "comp_scores": {"rsi": 60.0, "mm": -30.0}},
    {"asset_id": 2, "ticker": "BBB", "name": "Activo B", "score": -40.0,
     "delta_score": None, "comp_scores": {"rsi": None, "mm": 90.0}},
]


# ── Máximos (normalizan las barras) ──────────────────────────────────────────

def test_los_maximos_son_por_valor_absoluto():
    """La barra tiene que reflejar igual de fuerte un −90 que un +90."""
    max_total, por_comp = _maximos(_ROWS)

    assert max_total == 80.0
    assert por_comp == {"rsi": 60.0, "mm": 90.0}


def test_los_maximos_ignoran_los_faltantes_y_nunca_dan_cero():
    """Un cero como máximo haría una división por cero en el renderer."""
    max_total, por_comp = _maximos(
        [{"score": None, "comp_scores": {"rsi": None}}])

    assert max_total == 1.0
    assert por_comp == {}


# ── Columnas ─────────────────────────────────────────────────────────────────

def test_las_columnas_fijas_van_primero_y_despues_una_por_senal():
    cols = _column_defs(_META, 80.0, {"rsi": 60.0, "mm": 90.0})

    assert [c["field"] for c in cols] == [
        "ticker", "name", "score", "delta_score", "rsi", "mm"]


def test_la_cabecera_de_cada_senal_lleva_su_peso():
    """El peso en la cabecera es lo que explica por qué una señal arrastra el
    score más que otra; se perdía si la columna solo mostrara el nombre."""
    cols = _column_defs(_META, 80.0, {"rsi": 60.0, "mm": 90.0})
    rsi = next(c for c in cols if c["field"] == "rsi")

    assert "×2" in rsi["headerName"]
    assert "RSI sobrevendido" in rsi["headerName"]
    assert "×2" in rsi["headerTooltip"]


def test_cada_columna_de_senal_se_normaliza_con_SU_maximo():
    """Comparar barras entre columnas distintas no tendría sentido: cada señal
    tiene su propio rango."""
    cols = _column_defs(_META, 80.0, {"rsi": 60.0, "mm": 90.0})
    por_campo = {c["field"]: c for c in cols}

    assert por_campo["rsi"]["cellRendererParams"]["barMax"] == 60.0
    assert por_campo["mm"]["cellRendererParams"]["barMax"] == 90.0
    assert por_campo["score"]["cellRendererParams"]["barMax"] == 80.0


def test_el_delta_no_lleva_barra_y_usa_sus_propios_umbrales():
    """±0,5 y no ±20: son magnitudes distintas, teñir un Δ de 3 de gris sería
    esconder el dato."""
    cols = _column_defs(_META, 80.0, {})
    delta = next(c for c in cols if c["field"] == "delta_score")["cellRendererParams"]

    assert delta["barMax"] == 0
    assert (delta["posTh"], delta["negTh"]) == (0.5, -0.5)
    assert delta["plusSign"] is True


def test_sin_componentes_quedan_solo_las_columnas_fijas():
    assert len(_column_defs([], 1.0, {})) == 4


# ── Filas ────────────────────────────────────────────────────────────────────

def test_las_filas_se_aplanan_con_una_clave_por_senal():
    filas = _row_data(_ROWS, _META)

    assert filas[0] == {
        "asset_id": 1, "ticker": "AAA", "name": "Activo A",
        "score": 80.0, "delta_score": 1.5, "rsi": 60.0, "mm": -30.0,
    }


def test_una_senal_sin_valor_viaja_como_None_y_no_se_omite():
    """Si la clave faltara, la grilla mostraría la celda vacía igual que un
    None, pero ordenar por esa columna se comportaría distinto."""
    filas = _row_data(_ROWS, _META)

    assert "rsi" in filas[1]
    assert filas[1]["rsi"] is None


def test_el_asset_id_viaja_porque_los_enlaces_lo_necesitan():
    """El renderer arma /activo?asset_id=… con el dato de la fila."""
    assert all("asset_id" in f for f in _row_data(_ROWS, _META))


# ── Contrato con el JavaScript ───────────────────────────────────────────────

def test_los_renderers_que_nombra_python_existen_en_el_js():
    """Un typo en el nombre del renderer no rompe ningún import: la celda
    simplemente queda en blanco en producción."""
    js = (ROOT / "assets" / "dashAgGridComponentFunctions.js").read_text(
        encoding="utf-8")
    definidos = set(re.findall(r"dagcomponentfuncs\.(\w+)\s*=", js))

    usados = {c["cellRenderer"] for c in _column_defs(_META, 80.0, {})
              if "cellRenderer" in c}

    assert usados, "las columnas deberían usar renderers propios"
    assert usados <= definidos, (
        f"Renderers nombrados en Python que no existen en el JS: "
        f"{sorted(usados - definidos)}")


def test_el_js_no_hardcodea_colores():
    """Los colores tienen que llegar por parámetro desde ui_constants; si el JS
    los escribe, la paleta se bifurca y el sistema de diseño deja de valer."""
    js = (ROOT / "assets" / "dashAgGridComponentFunctions.js").read_text(
        encoding="utf-8")

    assert not re.findall(r"#[0-9a-fA-F]{6}\b", js)
