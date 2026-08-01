"""Formato de packs (strategy_packs/SPEC.md): parseo, filas normalizadas,
resolución de atributos por nombre y validación offline.

Todo lógica pura: es exactamente lo que corre `scripts/validate_pack.py` sin
base de datos, así que quien escribe un pack ve los mismos errores que le daría
el import.
"""
import json

import pytest

from app.services import pack_service as ps


# ── Detección de formato ──────────────────────────────────────────────────────

def test_looks_like_json_por_extension():
    assert ps.looks_like_json(b"{}", "pack.json")
    assert not ps.looks_like_json(b"PK\x03\x04", "senales.xlsx")


def test_looks_like_json_sin_nombre_olfatea_el_contenido():
    """El upload puede llegar sin nombre; un xlsx es un ZIP ('PK') y un pack
    empieza con '{', así que la distinción es inequívoca."""
    assert ps.looks_like_json(b'\n  {"signals": []}', None)
    assert not ps.looks_like_json(b"PK\x03\x04ndjs", None)


def test_extension_manda_sobre_el_contenido():
    """Un .xlsx que empieza con '{' no existe, pero si el nombre lo declara
    Excel hay que intentar leerlo como Excel y fallar con ese mensaje."""
    assert not ps.looks_like_json(b"{", "cosa.xlsx")


# ── parse_pack ────────────────────────────────────────────────────────────────

def _pack_bytes(obj) -> bytes:
    return json.dumps(obj, ensure_ascii=False).encode("utf-8")


def test_parse_pack_minimo():
    pack = ps.parse_pack(_pack_bytes({"signals": [{"key": "a"}]}))
    assert pack["signals"][0]["key"] == "a"


def test_parse_pack_acepta_bom():
    """Un JSON guardado desde Windows suele traer BOM; rechazarlo por eso
    sería un rechazo incomprensible para quien lo escribió."""
    crudo = '{"signals": [{"key": "a"}]}'.encode("utf-8-sig")
    assert ps.parse_pack(crudo)["signals"]


def test_parse_pack_json_invalido_dice_donde():
    with pytest.raises(ps.PackError, match="línea"):
        ps.parse_pack(b'{"signals": [,]}')


def test_parse_pack_rechaza_lista_de_nivel_superior():
    with pytest.raises(ps.PackError, match="lista"):
        ps.parse_pack(b'[{"key": "a"}]')


def test_parse_pack_rechaza_version_desconocida():
    with pytest.raises(ps.PackError, match="spec_version"):
        ps.parse_pack(_pack_bytes({"spec_version": 99, "signals": [{"key": "a"}]}))


def test_parse_pack_sin_version_asume_la_actual():
    assert ps.parse_pack(_pack_bytes({"signals": [{"key": "a"}]}))


def test_parse_pack_vacio_se_rechaza():
    with pytest.raises(ps.PackError, match="ni señales ni estrategias"):
        ps.parse_pack(_pack_bytes({"spec_version": 1}))


# ── Filas normalizadas ────────────────────────────────────────────────────────

def test_signal_rows_params_objeto_a_texto():
    pack = {"signals": [{"key": "s", "formula_type": "range",
                         "params": {"min": -3, "max": 3, "clamp": True}}]}
    fila = ps.signal_rows_from_pack(pack)[0]
    assert json.loads(fila["params"]) == {"min": -3, "max": 3, "clamp": True}


def test_signal_rows_conserva_el_orden_de_thresholds():
    """El orden de los thresholds es SEMÁNTICO (gana el primer límite que el
    valor supera): reordenarlos al serializar cambiaría los puntajes."""
    params = {"thresholds": [[-5, 100], [-15, 50], [None, -50]]}
    pack = {"signals": [{"key": "s", "formula_type": "threshold",
                         "params": params}]}
    fila = ps.signal_rows_from_pack(pack)[0]
    assert json.loads(fila["params"])["thresholds"] == params["thresholds"]


def test_signal_rows_params_texto_se_respeta_tal_cual():
    crudo = '{"min": 1, "max": 2}'
    pack = {"signals": [{"key": "s", "params": crudo}]}
    assert ps.signal_rows_from_pack(pack)[0]["params"] == crudo


def test_signal_rows_publica_booleana():
    pack = {"signals": [{"key": "a", "publica": True},
                        {"key": "b", "publica": False},
                        {"key": "c"}]}
    filas = ps.signal_rows_from_pack(pack)
    assert [f["publica"] for f in filas] == ["si", "no", "no"]


def test_signal_rows_deja_pasar_source_para_que_el_import_lo_rechace():
    """`source` se removió: la fila lo lleva para que el validador del import
    lo rechace con su mensaje, en vez de perderlo en silencio."""
    pack = {"signals": [{"key": "s", "source": "group"}]}
    assert ps.signal_rows_from_pack(pack)[0]["source"] == "group"


def test_signal_rows_pack_sin_senales_avisa_donde_importarlo():
    with pytest.raises(ps.PackError, match="Estrategias"):
        ps.signal_rows_from_pack({"strategies": [{"name": "E"}]})


def test_strategy_rows_filtro_objeto_a_texto_y_componentes_planos():
    tree = {"op": "AND", "children": [
        {"cond": {"left": {"type": "indicator", "key": "rsi_daily"},
                  "operator": ">", "right": {"type": "const", "value": 50}}}]}
    pack = {"strategies": [{
        "name": "E1", "filter": tree,
        "components": [{"signal_key": "a", "weight": 3},
                       {"signal_key": "b", "weight": 1}]}]}
    rows_s, rows_c = ps.strategy_rows_from_pack(pack)
    assert json.loads(rows_s[0]["filter_conditions"]) == tree
    assert [(c["strategy_name"], c["signal_key"], c["weight"]) for c in rows_c] \
        == [("E1", "a", 3), ("E1", "b", 1)]


def test_strategy_rows_acepta_filter_conditions_como_texto():
    """Para poder pegar sin retocar lo que exportó la app."""
    pack = {"strategies": [{"name": "E", "filter_conditions": '{"op": "AND"}',
                            "components": []}]}
    rows_s, _ = ps.strategy_rows_from_pack(pack)
    assert rows_s[0]["filter_conditions"] == '{"op": "AND"}'


def test_strategy_rows_sin_filtro_queda_none():
    pack = {"strategies": [{"name": "E", "components": []}]}
    rows_s, _ = ps.strategy_rows_from_pack(pack)
    assert rows_s[0]["filter_conditions"] is None


# ── Atributos: nombre → id ────────────────────────────────────────────────────

INDEX = {"sector": {"technology": 3, "energy": 7},
         "instrument_type": {"equity": 1, "fund": 2}}


def _cond(attr, operator, value):
    return {"cond": {"left": {"type": "attribute", "key": attr},
                     "operator": operator,
                     "right": {"type": "const", "value": value}}}


def test_resuelve_nombre_a_id():
    tree, errores = ps.resolve_attribute_values(_cond("sector", "=", "Technology"),
                                                INDEX)
    assert not errores
    assert tree["cond"]["right"]["value"] == 3


def test_resuelve_lista_de_nombres():
    tree, errores = ps.resolve_attribute_values(
        _cond("instrument_type", "in", ["Equity", "FUND"]), INDEX)
    assert not errores
    assert tree["cond"]["right"]["value"] == [1, 2]


def test_no_distingue_mayusculas_ni_espacios():
    tree, errores = ps.resolve_attribute_values(_cond("sector", "=", "  eNeRgY "),
                                                INDEX)
    assert not errores and tree["cond"]["right"]["value"] == 7


def test_ids_ya_resueltos_pasan_intactos():
    """Reimportar lo que exportó la app (que persiste ids) no debe romperse."""
    tree, errores = ps.resolve_attribute_values(_cond("sector", "in", [3, "7"]),
                                                INDEX)
    assert not errores and tree["cond"]["right"]["value"] == [3, 7]


def test_nombre_inexistente_es_error_con_sugerencia():
    _, errores = ps.resolve_attribute_values(_cond("sector", "=", "Technolgy"),
                                             INDEX)
    assert len(errores) == 1
    assert "no existe" in errores[0] and "technology" in errores[0]


def test_atributo_sin_valores_cargados_avisa():
    _, errores = ps.resolve_attribute_values(_cond("market", "=", "NASDAQ"), INDEX)
    assert "ningún valor cargado" in errores[0]


def test_no_muta_el_arbol_original():
    original = _cond("sector", "=", "Technology")
    copia = json.loads(json.dumps(original))
    ps.resolve_attribute_values(original, INDEX)
    assert original == copia


def test_recorre_grupos_anidados_y_no_toca_otras_condiciones():
    tree = {"op": "AND", "children": [
        {"op": "OR", "children": [_cond("sector", "=", "Energy")]},
        {"cond": {"left": {"type": "indicator", "key": "trend_daily"},
                  "operator": "=",
                  "right": {"type": "const", "value": "bullish"}}}]}
    resuelto, errores = ps.resolve_attribute_values(tree, INDEX)
    assert not errores
    assert resuelto["children"][0]["children"][0]["cond"]["right"]["value"] == 7
    # la condición sobre un indicador categórico queda como estaba
    assert resuelto["children"][1]["cond"]["right"]["value"] == "bullish"


# ── validate_pack ─────────────────────────────────────────────────────────────

CATALOGO = {
    "spec_version": 1,
    "indicators": [
        {"code": "rsi_daily", "name": "RSI", "type": "num", "keep_history": True},
        {"code": "trend_daily", "name": "Tendencia", "type": "str",
         "keep_history": True,
         "values": ["bullish", "bearish", "lateral"]},
        {"code": "best_sma", "name": "SMA óptima", "type": "num",
         "keep_history": False},
    ],
    "attributes": {"sector": ["Technology", "Energy"],
                   "instrument_type": ["Equity"]},
    "signals": [{"key": "ya_existe", "publica": True}],
}

PACK_OK = {
    "spec_version": 1,
    "pack": "ejemplo",
    "signals": [
        {"key": "rsi_bajo", "name": "RSI bajo", "indicator_key": "rsi_daily",
         "formula_type": "range", "params": {"min": 70, "max": 30, "clamp": True},
         "publica": True},
        {"key": "tendencia", "name": "Tendencia", "indicator_key": "trend_daily",
         "formula_type": "discrete_map",
         "params": {"map": {"bullish": 100, "bearish": -100, "lateral": 0}},
         "publica": True},
    ],
    "strategies": [{
        "name": "E1", "publica": True,
        "filter": {"op": "AND", "children": [
            _cond("sector", "in", ["Technology"]),
            {"cond": {"left": {"type": "indicator", "key": "rsi_daily"},
                      "operator": "<", "right": {"type": "const", "value": 40}}},
        ]},
        "components": [{"signal_key": "rsi_bajo", "weight": 3},
                       {"signal_key": "tendencia", "weight": 1}],
    }],
}


def test_pack_valido_no_tiene_errores_ni_avisos():
    r = ps.validate_pack(PACK_OK, CATALOGO)
    assert r["errors"] == []
    assert r["warnings"] == []
    assert r["skipped"] == []


def _errores(pack, catalogo=CATALOGO) -> str:
    return " | ".join(ps.validate_pack(pack, catalogo)["errors"])


def _avisos(pack, catalogo=CATALOGO) -> str:
    return " | ".join(ps.validate_pack(pack, catalogo)["warnings"])


def _con(pack, **cambios):
    """Copia del pack válido con la señal/estrategia modificada."""
    nuevo = json.loads(json.dumps(pack))
    for ruta, valor in cambios.items():
        seccion, idx, campo = ruta.split(".")
        nuevo[seccion][int(idx)][campo] = valor
    return nuevo


def test_error_indicador_inexistente():
    assert "no existe" in _errores(_con(PACK_OK, **{"signals.0.indicator_key": "chau"}))


def test_error_indicador_faltante():
    assert "indicator_key" in _errores(_con(PACK_OK, **{"signals.0.indicator_key": ""}))


def test_error_formula_no_coincide_con_el_tipo_del_indicador():
    """discrete_map sobre un indicador numérico compila y nunca puntúa: es la
    trampa silenciosa más cara, así que es error y no aviso."""
    malo = _con(PACK_OK, **{"signals.1.indicator_key": "rsi_daily"})
    assert "nunca puntúa" in _errores(malo)


def test_error_params_con_forma_equivocada():
    malo = _con(PACK_OK, **{"signals.0.params": {"map": {"bullish": 1}}})
    assert "range requiere" in _errores(malo)


def test_error_señal_del_componente_no_esta_en_el_pack():
    malo = json.loads(json.dumps(PACK_OK))
    malo["strategies"][0]["components"][0]["signal_key"] = "fantasma"
    assert "autosuficiente" in _errores(malo)


def test_señal_existente_en_la_instalacion_no_hace_falta_que_este_en_el_pack():
    ok = json.loads(json.dumps(PACK_OK))
    ok["strategies"][0]["components"].append({"signal_key": "ya_existe", "weight": 1})
    assert ps.validate_pack(ok, CATALOGO)["errors"] == []


def test_error_estrategia_sin_componentes():
    malo = _con(PACK_OK, **{"strategies.0.components": []})
    assert "sin componentes" in _errores(malo)


def test_error_sector_inexistente():
    malo = json.loads(json.dumps(PACK_OK))
    malo["strategies"][0]["filter"]["children"][0]["cond"]["right"]["value"] = ["Minería"]
    assert "no existe en esta instalación" in _errores(malo)


def test_error_categoria_fuera_del_catalogo_del_indicador():
    malo = json.loads(json.dumps(PACK_OK))
    malo["strategies"][0]["filter"]["children"][1] = {
        "cond": {"left": {"type": "indicator", "key": "trend_daily"},
                 "operator": "=",
                 "right": {"type": "const", "value": "alcista"}}}
    assert "fuera del catálogo" in _errores(malo)


def test_error_estrategia_publica_con_señal_privada():
    malo = _con(PACK_OK, **{"signals.0.publica": False})
    assert "señales privadas" in _errores(malo)


def test_error_source_y_scope_removidos():
    malo = _con(PACK_OK, **{"signals.0.source": "group"})
    malo["strategies"][0]["components"][0]["scope"] = "own_group"
    errores = _errores(malo)
    assert "'source' ya no se soporta" in errores
    assert "'scope' ya no se soporta" in errores


def test_error_key_repetida():
    malo = json.loads(json.dumps(PACK_OK))
    malo["signals"].append(dict(malo["signals"][0]))
    assert "repetida" in _errores(malo)


def test_error_peso_no_numerico():
    malo = json.loads(json.dumps(PACK_OK))
    malo["strategies"][0]["components"][0]["weight"] = "mucho"
    assert "peso no numérico" in _errores(malo)


def test_aviso_mapa_discreto_incompleto():
    malo = _con(PACK_OK, **{"signals.1.params": {"map": {"bullish": 100}}})
    assert "no cubre" in _avisos(malo)


def test_aviso_thresholds_desordenados():
    """La pantalla los ordena sola; el pack queda como lo escribieron, y mal
    ordenado el tramo permisivo absorbe todo sin dar ningún error."""
    malo = _con(PACK_OK, **{
        "signals.0.formula_type": "threshold",
        "signals.0.params": {"thresholds": [[-30, 0], [-5, 100], [None, -50]]}})
    assert "de mayor a menor" in _avisos(malo)


def test_aviso_threshold_sin_tramo_final():
    malo = _con(PACK_OK, **{
        "signals.0.formula_type": "threshold",
        "signals.0.params": {"thresholds": [[-5, 100], [-15, 50]]}})
    assert "sin tramo final" in _avisos(malo)


def test_aviso_clamp_desactivado():
    malo = _con(PACK_OK, **{"signals.0.params": {"min": 70, "max": 30,
                                                 "clamp": False}})
    assert "±100" in _avisos(malo)


def test_aviso_indicador_sin_historia():
    malo = _con(PACK_OK, **{"signals.0.indicator_key": "best_sma"})
    assert "no guarda historia" in _avisos(malo)


def test_aviso_señal_que_nadie_usa():
    malo = json.loads(json.dumps(PACK_OK))
    malo["signals"].append({"key": "huerfana", "indicator_key": "rsi_daily",
                            "formula_type": "range",
                            "params": {"min": 0, "max": 100}, "publica": True})
    assert "ninguna estrategia del pack usa" in _avisos(malo)


def test_aviso_estrategia_sin_filtro():
    malo = json.loads(json.dumps(PACK_OK))
    del malo["strategies"][0]["filter"]
    assert "sin filtro" in _avisos(malo)


def test_señal_usada_solo_en_el_filtro_no_cuenta_como_huerfana():
    pack = json.loads(json.dumps(PACK_OK))
    pack["strategies"][0]["components"] = [{"signal_key": "rsi_bajo", "weight": 1}]
    pack["strategies"][0]["filter"]["children"].append(
        {"cond": {"left": {"type": "signal", "key": "tendencia"},
                  "operator": ">", "right": {"type": "const", "value": 0}}})
    assert "ninguna estrategia" not in _avisos(pack)


# ── Sin catálogo: validación parcial, declarada ───────────────────────────────

def test_sin_catalogo_valida_lo_que_puede_y_declara_lo_que_no():
    r = ps.validate_pack(PACK_OK, None)
    assert r["errors"] == []
    assert r["skipped"], "sin catálogo hay que decir qué NO se verificó"


def test_sin_catalogo_no_inventa_indicadores_desconocidos():
    """Sin catálogo no se sabe qué indicadores existen: reportar 'desconocido'
    en cada condición sería ruido que taparía los errores reales."""
    r = ps.validate_pack(PACK_OK, None)
    assert not any("desconocido" in e for e in r["errors"])


def test_sin_catalogo_igual_detecta_errores_de_gramatica():
    malo = json.loads(json.dumps(PACK_OK))
    malo["strategies"][0]["filter"]["children"][1]["cond"]["operator"] = "≈"
    assert "operador desconocido" in " | ".join(
        ps.validate_pack(malo, None)["errors"])


def test_sin_catalogo_igual_valida_params():
    malo = _con(PACK_OK, **{"signals.0.params": {"min": 1, "max": 1}})
    assert "min y max" in " | ".join(ps.validate_pack(malo, None)["errors"])


# ── Planillas → pack (la inversa, scripts/pack_to_json.py) ────────────────────

def test_pack_from_rows_ida_y_vuelta_conserva_el_contenido():
    """La conversión a planillas y de vuelta tiene que dar el mismo pack: es lo
    que permite publicar en JSON lo que hoy solo existe como xlsx sin que el
    canónico diga otra cosa que el histórico."""
    original = {
        "spec_version": 1,
        "pack": "ida_y_vuelta",
        "signals": [
            {"key": "s1", "name": "Señal 1", "description": "con ñ y tilde",
             "indicator_key": "rsi_daily", "formula_type": "threshold",
             "params": {"thresholds": [[70, -100], [30, 50], [None, 100]]},
             "publica": True},
            {"key": "s2", "name": "Señal 2", "indicator_key": "trend_daily",
             "formula_type": "discrete_map",
             "params": {"map": {"bullish": 100, "bearish": -100}},
             "publica": False},
        ],
        "strategies": [
            {"name": "E1", "description": "una", "publica": True,
             "filter": {"op": "AND", "children": [
                 {"cond": {"left": {"type": "indicator", "key": "rsi_daily"},
                           "operator": ">",
                           "right": {"type": "const", "value": 50}}}]},
             "components": [{"signal_key": "s1", "weight": 3},
                            {"signal_key": "s2", "weight": 1}]},
        ],
    }
    filas_s = ps.signal_rows_from_pack(original)
    filas_e, filas_c = ps.strategy_rows_from_pack(original)
    vuelta = ps.pack_from_rows(filas_s, filas_e, filas_c, name="ida_y_vuelta")
    assert vuelta == original


def test_pack_from_rows_omite_las_celdas_vacias():
    """Un pack se lee y se edita a mano: `"description": null` en cada señal es
    ruido que el original no tenía."""
    pack = ps.pack_from_rows(
        [{"key": "s1", "name": "S", "description": None,
          "indicator_key": "rsi_daily", "formula_type": "range",
          "params": '{"min": 1, "max": 2}', "publica": "si"}], [], [])
    assert pack["signals"][0] == {
        "key": "s1", "name": "S", "indicator_key": "rsi_daily",
        "formula_type": "range", "params": {"min": 1, "max": 2},
        "publica": True}


def test_pack_from_rows_publica_ausente_se_omite():
    """Ausente = privada en los dos formatos; omitirlo conserva la semántica
    sin inventar una decisión que la planilla no tomó."""
    pack = ps.pack_from_rows(
        [{"key": "s1", "formula_type": "range", "params": "{}"}], [], [])
    assert "publica" not in pack["signals"][0]


def test_pack_from_rows_agrupa_componentes_sin_distinguir_caso():
    """El import cruza por nombre sin distinguir caso (ci_equals); agrupar de
    otra forma dejaría la estrategia sin componentes en silencio."""
    pack = ps.pack_from_rows(
        [], [{"name": "Mi Estrategia", "publica": "si"}],
        [{"strategy_name": "mi estrategia", "signal_key": "s1", "weight": 2.0}])
    assert pack["strategies"][0]["components"] == [
        {"signal_key": "s1", "weight": 2}]


def test_pack_from_rows_conserva_las_columnas_de_mas():
    """`source` fue removido y el import lo RECHAZA: si la conversión lo
    tragara, el pack convertido importaría distinto del original."""
    pack = ps.pack_from_rows(
        [{"key": "s1", "formula_type": "range", "params": "{}",
          "source": "group"}], [], [])
    assert pack["signals"][0]["source"] == "group"


def test_pack_from_rows_params_invalido_dice_cual_es_la_fila():
    with pytest.raises(ps.PackError, match="señales\[s1\]"):
        ps.pack_from_rows([{"key": "s1", "params": "{no es json}"}], [], [])


def test_pack_from_rows_filtro_invalido_dice_cual_es_la_fila():
    with pytest.raises(ps.PackError, match="estrategias\[E1\]"):
        ps.pack_from_rows([], [{"name": "E1",
                                "filter_conditions": "{roto"}], [])
