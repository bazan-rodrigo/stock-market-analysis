"""Tests de los helpers puros de la vista de Carteras (/carteras).

Sólo la lógica de texto de `_spec_summary` (traduce el spec del simulador guardado
en una cartera promovida a una línea legible). Los callbacks en sí tocan Dash y no
se testean acá, igual que el resto de la app.
"""
from app.callbacks.carteras_callbacks import _spec_summary


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
