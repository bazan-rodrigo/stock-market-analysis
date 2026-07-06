"""import_service: helpers puros de validación/reconciliación de datos importados."""
from app.services.import_service import _first_nonempty, _valid


# ── _valid ────────────────────────────────────────────────────────────────────

def test_valid_string_normal_es_valido():
    assert _valid("Argentina") is True


def test_valid_vacio_o_none_es_invalido():
    assert _valid("") is False
    assert _valid(None) is False


def test_valid_nan_none_string_case_insensitive_es_invalido():
    assert _valid("nan") is False
    assert _valid("NaN") is False
    assert _valid("None") is False
    assert _valid("  nan  ") is False


def test_valid_solo_espacios_es_invalido():
    assert _valid("   ") is False


def test_valid_cero_numerico_es_invalido():
    # bool(0) es False: un valor numérico 0 se trata como "vacío", no como dato
    assert _valid(0) is False
    assert _valid(0.0) is False


# ── _first_nonempty ───────────────────────────────────────────────────────────

def test_first_nonempty_devuelve_el_primero_valido():
    assert _first_nonempty(None, "nan", "  ", "Argentina", "Brasil") == "Argentina"


def test_first_nonempty_recorta_espacios():
    assert _first_nonempty("  Chile  ") == "Chile"


def test_first_nonempty_todos_invalidos_devuelve_vacio():
    assert _first_nonempty(None, "nan", "None", "") == ""


def test_first_nonempty_sin_argumentos_devuelve_vacio():
    assert _first_nonempty() == ""


def test_first_nonempty_cero_numerico_se_saltea():
    # 0 es falsy → se saltea igual que un valor vacío, aunque sea un dato real
    assert _first_nonempty(0, "Uruguay") == "Uruguay"
