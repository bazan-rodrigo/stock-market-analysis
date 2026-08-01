"""Tokens de conexión de IA: lo que se guarda, lo que no, y qué resuelve.

El token identifica a un USUARIO ante el servidor MCP. No es la credencial del
proveedor de IA — esa se queda en el cliente del usuario y la aplicación nunca
la ve; fue la razón de elegir MCP en vez de un panel propio.

Lo que estos tests protegen es que el token siga siendo la puerta correcta:
que el texto en claro no quede escrito en ningún lado, que revocar sirva de
algo, y sobre todo que el `AiCaller` que sale de `resolver()` tenga el rol REAL
del usuario — de ahí sale todo el gate de visibilidad de `app/ai`.
"""
import pytest
import sqlalchemy as sa

from app.ai import tokens
from app.database import Base, Session, engine, get_session


@pytest.fixture()
def db():
    import app.models  # noqa: F401

    Session.remove()
    Base.metadata.create_all(engine)
    with engine.begin() as conn:
        conn.execute(sa.text("DELETE FROM users"))
    yield
    with engine.begin() as conn:
        conn.execute(sa.text("DELETE FROM users"))
    Session.remove()


def _usuario(username="ana", role="analyst", active=True) -> int:
    from app.models import User

    s = get_session()
    u = User(username=username, role=role, active=active)
    u.set_password("x")
    s.add(u)
    s.commit()
    return u.id


# ── Qué se guarda ─────────────────────────────────────────────────────────────

def test_el_token_en_claro_no_queda_en_la_base(db):
    """Si alguien lee la base, no obtiene credenciales usables. Se busca el
    token completo en TODAS las columnas de texto de la fila, no solo en la que
    esperamos: así el test sigue sirviendo si mañana se agrega otra."""
    uid = _usuario()
    token = tokens.generar(uid)

    fila = get_session().execute(
        sa.text("SELECT * FROM users WHERE id = :i"), {"i": uid}).mappings().one()
    for col, valor in fila.items():
        if isinstance(valor, str):
            assert token not in valor, f"el token aparece en claro en '{col}'"


def test_se_guarda_el_hash_y_la_fecha(db):
    from app.models import User

    uid = _usuario()
    token = tokens.generar(uid)

    Session.remove()
    u = get_session().query(User).filter(User.id == uid).first()
    assert u.mcp_token_hash == tokens._hash(token)
    assert len(u.mcp_token_hash) == 64          # sha-256 hex
    assert u.mcp_token_created_at is not None


def test_el_token_lleva_prefijo_reconocible(db):
    """Para poder identificarlo si aparece en un log o en un repo."""
    assert tokens.generar(_usuario()).startswith(tokens.PREFIJO)


def test_dos_tokens_nunca_son_iguales(db):
    uid_a, uid_b = _usuario("a"), _usuario("b")
    assert tokens.generar(uid_a) != tokens.generar(uid_b)


# ── Resolver ──────────────────────────────────────────────────────────────────

def test_resolver_devuelve_el_caller_del_usuario(db):
    uid = _usuario("ana", role="analyst")
    caller = tokens.resolver(tokens.generar(uid))

    assert caller is not None
    assert caller.user_id == uid
    assert caller.is_admin is False


def test_el_rol_sale_del_usuario_no_del_token(db):
    """Un token de admin resuelve a un caller admin. Es lo que hace que la capa
    de IA vea exactamente lo mismo que la pantalla equivalente."""
    uid = _usuario("jefe", role="admin")
    caller = tokens.resolver(tokens.generar(uid))

    assert caller.is_admin is True


@pytest.mark.parametrize("malo", [None, "", "   ", "sma_inventado", "xyz", 12345])
def test_un_token_que_no_existe_no_resuelve(db, malo):
    _usuario()
    assert tokens.resolver(malo) is None


def test_un_token_revocado_deja_de_resolver(db):
    uid = _usuario()
    token = tokens.generar(uid)
    assert tokens.resolver(token) is not None

    assert tokens.revocar(uid) is True
    Session.remove()
    assert tokens.resolver(token) is None


def test_regenerar_invalida_el_anterior(db):
    """Hay un token por usuario: generar de nuevo es también cómo se rota si se
    filtró."""
    uid = _usuario()
    viejo = tokens.generar(uid)
    nuevo = tokens.generar(uid)

    Session.remove()
    assert tokens.resolver(viejo) is None
    assert tokens.resolver(nuevo) is not None


def test_un_usuario_desactivado_no_resuelve(db):
    """Igual que no podría entrar por la web: dar de baja a alguien tiene que
    cortarle también el acceso de su IA, sin pasos extra que alguien olvide."""
    from app.models import User

    uid = _usuario()
    token = tokens.generar(uid)

    s = get_session()
    s.query(User).filter(User.id == uid).first().active = False
    s.commit()
    Session.remove()

    assert tokens.resolver(token) is None


# ── Estado y revocación ───────────────────────────────────────────────────────

def test_estado_arranca_sin_token(db):
    est = tokens.estado(_usuario())
    assert est == {"tiene": False, "creado": None}


def test_estado_no_devuelve_el_hash(db):
    """No le sirve a la pantalla y no tiene por qué viajar al browser."""
    uid = _usuario()
    tokens.generar(uid)
    assert set(tokens.estado(uid)) == {"tiene", "creado"}


def test_revocar_sin_token_no_falla(db):
    assert tokens.revocar(_usuario()) is False


def test_operar_sobre_un_usuario_inexistente_avisa(db):
    for fn in (tokens.generar, tokens.revocar, tokens.estado):
        with pytest.raises(ValueError, match="No existe el usuario"):
            fn(999_999)


# ── La capa de IA, de punta a punta ───────────────────────────────────────────

def test_el_caller_resuelto_sirve_para_invocar_una_herramienta(db):
    """El circuito completo: token → caller → herramienta, sin Flask en el
    medio. Es exactamente lo que va a hacer el servidor MCP."""
    from app.ai import registry

    uid = _usuario("ana", role="analyst")
    caller = tokens.resolver(tokens.generar(uid))
    salida = registry.call("list_strategies", caller)

    assert salida["strategies"] == []      # base vacía, pero resolvió y filtró
    assert salida["total"] == 0
