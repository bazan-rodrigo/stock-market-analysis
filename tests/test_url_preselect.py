"""Preselección de activo desde la URL (`/activo?asset_id=N`, los links del
screener de señales).

La regla que codifican estos tests: el value SOLO se emite si ya figura entre
las options del dropdown. Es lo que hace la preselección determinista — el
`dcc.Dropdown` de Dash borra en silencio cualquier value que no esté en sus
options, así que emitirlo antes equivale a no emitirlo (bug intermitente:
"a veces carga el activo y a veces no", según qué callback contestara primero).
"""
from pathlib import Path

from dash import no_update

from app.components.url_params import (
    int_param_from_search, option_values, preselect_from_options,
)

ROOT = Path(__file__).resolve().parent.parent

_OPTS = [
    {"label": "AAPL - Apple", "value": 101},
    {"label": "GGAL - Galicia", "value": 303},
]


def test_con_las_options_cargadas_devuelve_el_id_de_la_url():
    assert preselect_from_options(_OPTS, "?asset_id=303") == 303


def test_sin_options_todavia_NO_emite_el_value():
    """El caso del bug: si el value gana la carrera, el Dropdown lo borra. La
    respuesta correcta es esperar — el callback vuelve a disparar cuando las
    options llegan."""
    assert preselect_from_options([], "?asset_id=303") is no_update
    assert preselect_from_options(None, "?asset_id=303") is no_update


def test_un_id_que_no_esta_en_el_catalogo_no_toca_el_selector():
    assert preselect_from_options(_OPTS, "?asset_id=999999") is no_update


def test_sin_asset_id_no_pisa_lo_que_el_usuario_haya_elegido():
    assert preselect_from_options(_OPTS, "") is no_update
    assert preselect_from_options(_OPTS, None) is no_update
    assert preselect_from_options(_OPTS, "?tab=chart") is no_update


def test_una_url_editada_a_mano_no_explota():
    assert preselect_from_options(_OPTS, "?asset_id=abc") is no_update
    assert preselect_from_options(_OPTS, "?asset_id=") is no_update


def test_el_parametro_viaja_como_texto_y_se_compara_como_entero():
    """La query string trae '303' y las options tienen 303: sin el int() la
    comparación falla siempre y la preselección nunca funcionaría."""
    assert int_param_from_search("?asset_id=303", "asset_id") == 303
    assert int_param_from_search("?strategy_id=7&asset_id=303", "asset_id") == 303
    assert int_param_from_search("?asset_id=303", "strategy_id") is None


def test_options_escalares_pelados_tambien_se_soportan():
    assert option_values([1, 2, 3]) == {1, 2, 3}
    assert option_values(_OPTS) == {101, 303}


def test_ningun_callback_parsea_la_query_string_por_su_cuenta():
    """La preselección va SIEMPRE por el helper: es el único lugar donde la
    validación contra las options está garantizada. Un `parse_qs` suelto en un
    callback es el patrón que traía el bug de vuelta."""
    culpables = sorted(
        p.name for p in (ROOT / "app" / "callbacks").glob("*.py")
        if "parse_qs" in p.read_text(encoding="utf-8")
    )
    assert not culpables, (
        f"Callbacks que parsean la URL a mano: {culpables}. Usá "
        f"app.components.url_params.preselect_from_options, que no emite un "
        f"value ausente de las options (si no, el Dropdown lo borra).")
