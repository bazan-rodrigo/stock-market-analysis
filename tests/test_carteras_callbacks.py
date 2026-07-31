"""Tests de los helpers puros de la vista de Carteras (/carteras).

`_spec_summary` traduce el spec del simulador guardado en una cartera promovida a
una línea legible; `_currency_options`/`_currency_error` arman el combo de monedas
(la moneda se guarda como TEXTO, no como FK, así que el catálogo es la fuente de
las opciones pero lo ya cargado a mano tiene que sobrevivir). Los callbacks en sí
tocan Dash y no se testean acá, igual que el resto de la app.
"""
import sqlalchemy as sa
from sqlalchemy.orm import Session

from app.callbacks.carteras_callbacks import (_currency_error,
                                              _currency_options, _spec_summary)
from app.database import Base
from app.models import Currency


def test_spec_summary_vacio():
    assert _spec_summary({}) == "Sin reglas de entrada/salida."
    assert _spec_summary(None) == "Sin reglas de entrada/salida."


def test_spec_summary_solo_entradas():
    spec = {"entries": [{"type": "score", "th": 2.0},
                        {"type": "pct", "th": 90.0}]}
    assert _spec_summary(spec) == "Entrada: score ≥ 2 y percentil ≥ 90"


def test_spec_summary_completo():
    spec = {"entries": [{"type": "score", "th": 3.0}],
            "score_exits": [{"type": "absolute", "x": 1.0}],
            "caps": [{"type": "max_bars", "n": 20},
                     {"type": "stop_loss", "pct": 5.0},
                     {"type": "trailing_stop", "pct": 8.0},
                     {"type": "take_profit", "pct": 15.0}],
            "cooldown": 3, "rearm": True}
    out = _spec_summary(spec)
    assert out == ("Entrada: score ≥ 3 · Salida: score < 1, máx 20 barras, "
                   "stop loss 5%, trailing 8%, take profit 15% · cooldown 3 · "
                   "re-arme")


def test_spec_summary_sin_reglas_efectivas():
    # spec con listas vacías (todas las condiciones apagadas) → sin reglas
    assert _spec_summary({"entries": [], "score_exits": [], "caps": [],
                          "cooldown": 0, "rearm": False}
                         ) == "Sin reglas de entrada/salida."


# ── Combo de monedas ─────────────────────────────────────────────────────────

def _session(*currencies):
    """sqlite en memoria con el esquema completo (no toca la base real)."""
    eng = sa.create_engine("sqlite://")
    Base.metadata.create_all(eng)
    s = Session(eng)
    for name, iso in currencies:
        s.add(Currency(name=name, iso_code=iso))
    s.commit()
    return s


def test_currency_options_value_es_el_iso():
    # Se guarda texto: el value tiene que ser el código, no el id del catálogo.
    s = _session(("Dólar Estadounidense", "USD"))
    assert _currency_options(s) == [
        {"label": "USD — Dólar Estadounidense", "value": "USD"}]


def test_currency_options_sin_iso_usa_el_nombre():
    s = _session(("Guaraní", None))
    assert _currency_options(s) == [{"label": "Guaraní", "value": "Guaraní"}]


def test_currency_options_no_duplica_cuando_nombre_es_el_iso():
    # Las monedas que crea la importación desde Yahoo nacen con name == iso_code.
    s = _session(("ARS", "ARS"))
    assert _currency_options(s) == [{"label": "ARS", "value": "ARS"}]


def test_currency_options_ordenadas_por_nombre():
    s = _session(("Peso Argentino", "ARS"), ("Dólar", "USD"), ("Euro", "EUR"))
    assert [o["value"] for o in _currency_options(s)] == ["USD", "EUR", "ARS"]


def test_currency_options_conserva_lo_cargado_fuera_del_catalogo():
    # Antes del combo la moneda era texto libre: editar una cartera vieja no
    # puede borrarle en silencio una moneda que el catálogo no tiene.
    s = _session(("Peso Argentino", "ARS"))
    opts = _currency_options(s, extra="U$S")
    assert opts[0] == {"label": "U$S (fuera del catálogo)", "value": "U$S"}
    assert len(opts) == 2


def test_currency_options_no_duplica_lo_que_ya_esta_en_el_catalogo():
    s = _session(("Peso Argentino", "ARS"))
    assert _currency_options(s, extra="ARS") == [
        {"label": "ARS — Peso Argentino", "value": "ARS"}]


def test_currency_error_solo_si_no_entra_en_la_columna():
    assert _currency_error(None) is None
    assert _currency_error("ARS") is None
    assert _currency_error("1234567890") is None          # justo el máximo
    msg = _currency_error("Peso Argentino")               # 14 > 10
    assert msg and "código ISO" in msg
