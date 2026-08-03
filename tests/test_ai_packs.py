"""Las dos piezas que le faltaban a la IA para poder ARMAR un pack.

`get_catalog` ya le decía qué existe en esta instalación; lo que no tenía era el
formato del archivo —vivía detrás de un botón de descarga de una pantalla— ni
forma de probar lo que escribía. El resultado medido: el modelo llegaba a la
sección del manual que menciona la especificación, leía que se descarga desde la
pantalla, y entregaba el pack a ojo.

Acá se prueba lo que es responsabilidad de la capa de IA: que el documento que
sirve la herramienta sea EL MISMO que baja la pantalla, que el ensayo re-aplique
el gate (la pantalla equivalente es admin-only) y que lo que llega por argumento
pase por el mismo parseo que el import. La validación en sí es del servicio y la
prueban `test_pack_service.py` / `test_pack_spec.py`.
"""
import json

import pytest

from app.ai import registry
from app.ai.caller import AiCaller
from app.services import pack_service

ADMIN = AiCaller(user_id=1, is_admin=True)
ANALISTA = AiCaller(user_id=7, is_admin=False)


# ── La especificación ────────────────────────────────────────────────────────

def test_devuelve_el_mismo_documento_que_baja_la_pantalla():
    """Si algún día se sirviera una copia recortada, la IA y la persona
    estarían siguiendo contratos distintos sin que nadie se entere."""
    out = registry.call("get_pack_spec", ADMIN)
    assert out["contenido"] == pack_service.spec_bytes().decode("utf-8")
    assert out["spec_version"] == pack_service.SPEC_VERSION


def test_lista_las_secciones_para_poder_pedirlas_sueltas():
    out = registry.call("get_pack_spec", ADMIN)
    titulos = " | ".join(out["secciones"])
    assert len(out["secciones"]) >= 10
    for esperado in ("Señales", "fórmulas", "filtro de elegibilidad"):
        assert esperado in titulos


def test_una_seccion_devuelve_solo_esa_seccion():
    entero = registry.call("get_pack_spec", ADMIN)["contenido"]
    out = registry.call("get_pack_spec", ADMIN, {"seccion": "6"})
    assert out["seccion"].startswith("6.")
    assert "filtro" in out["seccion"].lower()
    assert out["contenido"].startswith("## 6.")
    assert len(out["contenido"]) < len(entero)


def test_la_seccion_tambien_se_pide_por_titulo():
    """El modelo la va a citar como la leyó, no siempre por su número."""
    por_numero = registry.call("get_pack_spec", ADMIN, {"seccion": "4"})
    por_texto = registry.call("get_pack_spec", ADMIN, {"seccion": "fórmulas"})
    assert por_texto["seccion"] == por_numero["seccion"]


def test_el_signo_de_seccion_del_propio_spec_se_acepta():
    """El SPEC se referencia a sí mismo con «§7», así que es tal cual lo que un
    modelo va a pasar después de leerlo."""
    assert registry.call("get_pack_spec", ADMIN,
                         {"seccion": "§7"})["seccion"].startswith("7.")


def test_una_seccion_inexistente_lista_las_que_hay():
    """Para que el modelo se corrija solo en vez de reintentar lo mismo."""
    with pytest.raises(ValueError, match="Señales"):
        registry.call("get_pack_spec", ADMIN, {"seccion": "99"})


def test_siempre_remite_al_catalogo():
    """La especificación es la mitad FIJA del estándar: sola no alcanza para
    escribir un pack, y quedarse con ella es justo el error que un modelo puede
    cometer sin enterarse (inventaría `indicator_key` plausibles)."""
    out = registry.call("get_pack_spec", ANALISTA, {"seccion": "2"})
    assert "get_catalog" in out["catalogo"]
    assert "preview_pack" in out["ensayo"]


def test_la_especificacion_no_esta_restringida_por_rol():
    """El contrato es público por diseño: existe para que lo siga alguien que
    no ve ni el repo ni la base."""
    assert registry.call("get_pack_spec", ANALISTA)["contenido"]


# ── El ensayo ────────────────────────────────────────────────────────────────

@pytest.fixture()
def fake_preview(monkeypatch):
    """El ensayo real toca la base; acá se verifica el adaptador."""
    llamadas = []

    def _fake(pack, acting_user_id=None):
        llamadas.append({"pack": pack, "acting_user_id": acting_user_id})
        return {"errors": [], "warnings": ["señal 'x': nunca puntúa"],
                "rows": [{"tipo": "Señal", "nombre": "x", "accion": "crea"}],
                "summary": {"crea": 1, "actualiza": 0}}

    monkeypatch.setattr(pack_service, "preview_pack", _fake)
    return llamadas


_PACK = {"spec_version": pack_service.SPEC_VERSION, "pack": "prueba",
         "signals": [{"key": "x", "name": "X", "indicator_key": "rsi_daily",
                      "formula_type": "range",
                      "params": {"min": 70, "max": 30}}]}


def test_ensaya_y_delega_con_la_identidad_de_quien_pregunta(fake_preview):
    """`acting_user_id` es lo que le permite al servicio avisar «esto ya existe
    y es de otro»: sin propagarlo, el aviso no sale."""
    out = registry.call("preview_pack", ADMIN, {"pack": _PACK})
    assert fake_preview[0]["acting_user_id"] == 1
    assert fake_preview[0]["pack"]["signals"][0]["key"] == "x"
    assert out["summary"] == {"crea": 1, "actualiza": 0}


def test_la_respuesta_explica_errores_avisos_y_pisadas(fake_preview):
    out = registry.call("preview_pack", ADMIN, {"pack": _PACK})
    assert "rechaza" in out["como_leerlo"]
    assert "actualiza" in out["como_leerlo"]


def test_el_pack_tambien_se_acepta_como_texto(fake_preview):
    """Un modelo que ya escribió el JSON en la conversación lo manda tal cual;
    rechazarlo solo gastaría un turno."""
    registry.call("preview_pack", ADMIN, {"pack": json.dumps(_PACK)})
    assert fake_preview[0]["pack"]["signals"][0]["key"] == "x"


def test_un_analista_no_puede_ensayar(fake_preview):
    """El gate no se hereda: la pantalla equivalente es admin-only, y el informe
    nombra definiciones ajenas —con su dueño— para decir cuál se pisaría."""
    with pytest.raises(ValueError, match="administradores"):
        registry.call("preview_pack", ANALISTA, {"pack": _PACK})
    assert not fake_preview, "no tendría que haber llegado al servicio"


def test_el_error_de_rol_deja_una_salida(fake_preview):
    """Que no pueda ensayar no significa que no pueda escribir el pack."""
    with pytest.raises(ValueError, match="get_pack_spec"):
        registry.call("preview_pack", ANALISTA, {"pack": _PACK})


def test_un_json_invalido_se_explica_en_vez_de_reventar(fake_preview):
    with pytest.raises(ValueError, match="JSON inválido"):
        registry.call("preview_pack", ADMIN, {"pack": "{no es json"})


def test_algo_que_no_es_un_pack_se_rechaza_con_su_tipo(fake_preview):
    with pytest.raises(ValueError, match="lista"):
        registry.call("preview_pack", ADMIN, {"pack": [1, 2, 3]})


def test_un_pack_enorme_se_corta_antes_de_parsearlo(fake_preview):
    """Es la primera herramienta que RECIBE un documento; sin tope, el límite lo
    pondría el servidor de otra forma y mucho más tarde."""
    from app.ai.tools import packs

    with pytest.raises(ValueError, match="tope"):
        registry.call("preview_pack", ADMIN,
                      {"pack": "x" * (packs.MAX_PACK_BYTES + 1)})
    assert not fake_preview


def test_el_ensayo_no_importa_nada():
    """El nombre de la herramienta es `preview_pack` y no hay ninguna que
    aplique: la escritura sigue siendo un acto humano en la pantalla."""
    nombres = {t.name for t in registry.all_tools()}
    assert "preview_pack" in nombres
    assert not (nombres & {"import_pack", "apply_pack", "save_pack"})
