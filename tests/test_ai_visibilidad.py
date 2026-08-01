"""La capa de IA no muestra lo que el usuario no vería en la pantalla.

Es LA propiedad de seguridad de `app/ai`, y no se hereda de ningún lado: el
gate de visibilidad de esta aplicación está implementado en los callbacks y las
páginas (más de cien llamadas a `current_viewer()`/`get_visible_*`), mientras
que los servicios de lectura devuelven lo que se les pida —
`strategy_service.get_strategy_results()` recibe un id y no chequea nada, y el
gate era que la pantalla ya hubiera filtrado el desplegable.

Un servidor MCP corre fuera de Flask: no hay `current_user`, no hay pantalla, y
si estas herramientas no re-aplican el filtro, cualquier token puede leer las
definiciones privadas de otro usuario probando ids.
"""
import pytest
import sqlalchemy as sa

from app.ai import registry
from app.ai.caller import AiCaller
from app.database import Base, Session, engine, get_session

_ADMIN = 1
_ANA = 7          # analista
_OTRO = 9         # otro analista


@pytest.fixture()
def db():
    import app.models  # noqa: F401

    Session.remove()
    Base.metadata.create_all(engine)
    tablas = ("strategy_component", "strategy", "`signal`")
    with engine.begin() as conn:
        for t in tablas:
            conn.execute(sa.text(f"DELETE FROM {t}"))
    yield
    with engine.begin() as conn:
        for t in tablas:
            conn.execute(sa.text(f"DELETE FROM {t}"))
    Session.remove()


def _sembrar():
    """Tres estrategias: pública del admin, privada del analista, privada de
    otro. La tercera es la que nunca tiene que aparecer."""
    from app.models import Strategy

    s = get_session()
    filas = {
        "publica_admin": Strategy(name="publica_admin", owner_id=_ADMIN,
                                  is_public=True),
        "privada_ana": Strategy(name="privada_ana", owner_id=_ANA,
                                is_public=False),
        "privada_otro": Strategy(name="privada_otro", owner_id=_OTRO,
                                 is_public=False),
    }
    for st in filas.values():
        s.add(st)
    s.commit()
    return {k: v.id for k, v in filas.items()}


def _nombres(resultado) -> set:
    return {e["name"] for e in resultado["strategies"]}


# ── Listar ────────────────────────────────────────────────────────────────────

def test_el_analista_ve_las_publicas_y_las_propias(db):
    _sembrar()
    out = registry.call("list_strategies", AiCaller(user_id=_ANA))
    assert _nombres(out) == {"publica_admin", "privada_ana"}


def test_el_analista_no_ve_la_privada_de_otro(db):
    _sembrar()
    out = registry.call("list_strategies", AiCaller(user_id=_ANA))
    assert "privada_otro" not in _nombres(out)


def test_el_admin_ve_todo(db):
    _sembrar()
    out = registry.call("list_strategies",
                        AiCaller(user_id=_ADMIN, is_admin=True))
    assert _nombres(out) == {"publica_admin", "privada_ana", "privada_otro"}


def test_el_anonimo_solo_ve_publicas(db):
    _sembrar()
    out = registry.call("list_strategies", AiCaller(user_id=None))
    assert _nombres(out) == {"publica_admin"}


# ── Acceso por id: el agujero más fácil de dejar abierto ─────────────────────

def test_no_se_puede_leer_por_id_una_estrategia_ajena(db):
    """El servicio de lectura no chequea visibilidad: si la herramienta no lo
    hace, alcanza con probar ids para leer lo privado de otro."""
    ids = _sembrar()
    with pytest.raises(ValueError):
        registry.call("strategy_ranking", AiCaller(user_id=_ANA),
                      {"strategy_id": ids["privada_otro"]})


def test_tampoco_por_la_historia_de_scores(db):
    ids = _sembrar()
    with pytest.raises(ValueError):
        registry.call("strategy_score_history", AiCaller(user_id=_ANA),
                      {"strategy_id": ids["privada_otro"], "asset_ids": [1]})


def test_el_mensaje_no_delata_que_la_estrategia_existe(db):
    """Mismo texto exista o no: si dijera "no tenés permiso" para una y "no
    existe" para otra, el error se vuelve un oráculo para enumerar ids."""
    ids = _sembrar()
    ana = AiCaller(user_id=_ANA)

    with pytest.raises(ValueError) as ajena:
        registry.call("strategy_ranking", ana,
                      {"strategy_id": ids["privada_otro"]})
    with pytest.raises(ValueError) as inexistente:
        registry.call("strategy_ranking", ana, {"strategy_id": 999_999})

    def _sin_id(msg):
        return msg.replace(str(ids["privada_otro"]), "X").replace("999999", "X")

    assert _sin_id(str(ajena.value)) == _sin_id(str(inexistente.value))


def test_el_dueno_si_llega_a_la_suya(db):
    ids = _sembrar()
    out = registry.call("strategy_ranking", AiCaller(user_id=_ANA),
                        {"strategy_id": ids["privada_ana"]})
    # Sin historia calculada devuelve el aviso, no un error: la estrategia se
    # resolvió bien, lo que falta es el pipeline.
    assert out["strategy_id"] == ids["privada_ana"]
    assert out["ranking"] == []
    assert "historia" in out["aviso"]


def test_el_admin_llega_a_la_ajena(db):
    ids = _sembrar()
    out = registry.call("strategy_ranking",
                        AiCaller(user_id=_ADMIN, is_admin=True),
                        {"strategy_id": ids["privada_otro"]})
    assert out["strategy_id"] == ids["privada_otro"]


# ── Señales ───────────────────────────────────────────────────────────────────

def test_las_senales_tambien_se_filtran(db):
    from app.models import SignalDefinition

    s = get_session()
    s.add(SignalDefinition(key="pub", name="p", formula_type="threshold",
                           params="{}", owner_id=_ADMIN, is_public=True))
    s.add(SignalDefinition(key="priv_otro", name="o", formula_type="threshold",
                           params="{}", owner_id=_OTRO, is_public=False))
    s.commit()

    out = registry.call("list_signals", AiCaller(user_id=_ANA))
    claves = {x["key"] for x in out["signals"]}
    assert claves == {"pub"}


# ── Manual: el nivel del caller ───────────────────────────────────────────────

def _slugs_visibles(caller):
    from app.ai.tools.manual import _nivel
    from app.services import manual_service

    return {s.slug for s in manual_service.visible(
        manual_service.load_sections(), _nivel(caller))}


def test_un_analista_no_queda_en_nivel_invitado():
    """Regresión. La primera versión resolvía el nivel con
    `manual_service.role_of(autenticado, username, is_admin)`, y como la capa
    de IA no tiene username le pasaba None — esa función devuelve "invitado"
    en ese caso, así que un analista veía 24 de 73 secciones y el manual le
    ocultaba justo las páginas que usa. Ningún trinquete lo veía: la llamada
    funcionaba y devolvía menos, que es la peor forma de fallar."""
    anonimo = _slugs_visibles(AiCaller(user_id=None))
    analista = _slugs_visibles(AiCaller(user_id=_ANA))
    admin = _slugs_visibles(AiCaller(user_id=_ADMIN, is_admin=True))

    assert anonimo < analista < admin, (
        f"el escalafón se aplastó: invitado={len(anonimo)} "
        f"analista={len(analista)} admin={len(admin)}")


def test_el_analista_llega_a_la_seccion_de_estrategias():
    """Concreta y no solo por cantidades: es la sección con `roles: analista`
    que el bug ocultaba."""
    assert "configuracion-estrategias" in _slugs_visibles(AiCaller(user_id=_ANA))


def test_el_catalogo_no_filtra_las_definiciones_ajenas(db):
    """build_catalog() enumera TODO (lo escribió un botón admin-only). La
    herramienta reemplaza esas dos claves por la vista del usuario; si algún
    día alguien la simplifica llamando a build_catalog() a secas, esto lo
    frena."""
    from app.models import SignalDefinition

    s = get_session()
    s.add(SignalDefinition(key="priv_otro", name="o", formula_type="threshold",
                           params="{}", owner_id=_OTRO, is_public=False))
    s.commit()
    _sembrar()

    cat = registry.call("get_catalog", AiCaller(user_id=_ANA))
    assert "priv_otro" not in {x["key"] for x in cat["signals"]}
    assert "privada_otro" not in {x["name"] for x in cat["strategies"]}
