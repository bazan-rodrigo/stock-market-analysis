"""Llegada desde Calibración: /admin/signals?editar=<key>&min=&max=

Por qué esto existe y por qué la preselección vive en el LAYOUT: el primer
intento la puso en un callback sobre `url.search` y **nunca disparó**. Cuando
la página se carga, el cambio de la URL ya ocurrió antes de que existieran los
componentes del modal, así que la única llamada posible es la inicial — y esa
es justo la que `prevent_initial_call` descarta. El síntoma fue mudo: la URL
llegaba con los parámetros y la pantalla mostraba la grilla, sin error.

Se prueba la parte pura (el merge de la escala propuesta sobre los params de la
señal); el armado del layout necesita un request de Flask.
"""
import dash

# Importar una página exige que exista una app Dash (register_page lo valida).
# Mismo patrón que test_ui_consistency.
try:
    dash.Dash(__name__, use_pages=True, pages_folder="")
except Exception:
    pass

from app.pages.admin_signals import params_con_escala  # noqa: E402


def test_pisa_min_y_max_y_conserva_el_resto():
    original = '{"min": 70, "max": 30, "clamp": true}'
    salida = params_con_escala(original, "6", "1")
    import json
    p = json.loads(salida)
    assert p["min"] == 6 and p["max"] == 1
    assert p["clamp"] is True, "no puede perder los otros parámetros"


def test_sin_parametros_devuelve_los_de_la_senal():
    original = '{"min": 70, "max": 30}'
    assert params_con_escala(original, None, None) == original
    assert params_con_escala(original, "", "") == original


def test_una_url_editada_a_mano_no_rompe_el_editor():
    """Un valor no numérico se ignora: abrir el editor con lo que ya tenía es
    mejor que no abrirlo."""
    original = '{"min": 70, "max": 30}'
    assert params_con_escala(original, "abc", "xyz") == original


def test_solo_uno_de_los_dos_tambien_vale():
    import json
    p = json.loads(params_con_escala('{"min": 70, "max": 30}', None, "1"))
    assert p == {"min": 70, "max": 1}


def test_params_ilegibles_se_devuelven_tal_cual():
    """Una señal con params rotos ya es un problema, pero no se agrava
    perdiéndolos acá."""
    assert params_con_escala("no es json", "1", "2") == "no es json"


def test_sin_params_previos_arranca_de_cero():
    import json
    assert json.loads(params_con_escala(None, "0", "100")) == {"min": 0, "max": 100}
