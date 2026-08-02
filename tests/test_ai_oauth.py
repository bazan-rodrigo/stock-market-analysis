"""El servidor OAuth del MCP: lo que tiene que ser imposible.

Un servidor de autorización se rompe en silencio. Si un código se puede usar
dos veces, si revocar no revoca, si un token vencido sigue entrando, todo
"funciona" igual — hasta que no. Por eso estos tests están escritos desde la
negativa: qué NO tiene que poder hacerse.

La identidad de fondo sigue siendo el token de «Conexión IA» (0099): OAuth es
el envoltorio que exigen los conectores remotos, que no dejan mandar un header.
"""
import asyncio
from datetime import datetime, timedelta

import pytest
import sqlalchemy as sa

from app.ai import oauth, tokens
from app.database import Base, Session, engine, get_session

_CLIENTE = "cliente-de-prueba"


def corre(coro):
    return asyncio.run(coro)


@pytest.fixture()
def db():
    import app.models  # noqa: F401

    Session.remove()
    Base.metadata.create_all(engine)
    with engine.begin() as conn:
        for t in ("oauth_grant", "oauth_client", "users"):
            conn.execute(sa.text(f"DELETE FROM {t}"))
    yield
    with engine.begin() as conn:
        for t in ("oauth_grant", "oauth_client", "users"):
            conn.execute(sa.text(f"DELETE FROM {t}"))
    Session.remove()


def _usuario(username="ana", role="analyst") -> int:
    from app.models import User

    s = get_session()
    u = User(username=username, role=role, active=True)
    u.set_password("x")
    s.add(u)
    s.commit()
    return u.id


def _cliente():
    from mcp.shared.auth import OAuthClientInformationFull

    return OAuthClientInformationFull(
        client_id=_CLIENTE, client_secret="secreto",
        redirect_uris=["https://claude.ai/callback"],
        grant_types=["authorization_code", "refresh_token"],
        response_types=["code"], token_endpoint_auth_method="client_secret_post")


def _params(state="xyz"):
    from mcp.server.auth.provider import AuthorizationParams

    return AuthorizationParams(
        state=state, scopes=["read"], code_challenge="reto",
        redirect_uri="https://claude.ai/callback",
        redirect_uri_provided_explicitly=True, resource=None)


def _flujo_hasta_tokens(uid: int):
    """Recorre autorización → aprobación → canje. Devuelve el OAuthToken."""
    from urllib.parse import parse_qs, urlparse

    prov = oauth.ProveedorOAuth()
    cli = _cliente()
    corre(prov.register_client(cli))

    url = corre(prov.authorize(cli, _params()))
    solicitud = parse_qs(urlparse(url).query)["solicitud"][0]

    destino = oauth.aprobar(solicitud, tokens.generar(uid))
    codigo = parse_qs(urlparse(destino).query)["code"][0]

    ac = corre(prov.load_authorization_code(cli, codigo))
    return prov, cli, corre(prov.exchange_authorization_code(cli, ac))


# ── El camino feliz, para que lo demás signifique algo ────────────────────────

def test_el_flujo_completo_emite_tokens_usables(db):
    uid = _usuario()
    prov, _cli, tok = _flujo_hasta_tokens(uid)

    assert tok.access_token and tok.refresh_token
    acceso = corre(prov.load_access_token(tok.access_token))
    assert acceso is not None
    assert acceso.subject == str(uid)


def test_el_rol_del_usuario_viaja_en_los_claims(db):
    """De ahí sale el AiCaller: si el rol no llegara, un admin quedaría como
    analista y vería de menos (o al revés, que sería peor)."""
    prov, _cli, tok = _flujo_hasta_tokens(_usuario("jefe", role="admin"))
    assert corre(prov.load_access_token(tok.access_token)).claims["is_admin"] is True


def test_la_redireccion_conserva_el_state(db):
    """Sin `state` el cliente no puede verificar que la respuesta corresponde a
    SU pedido — es la defensa contra CSRF del flujo."""
    from urllib.parse import parse_qs, urlparse

    prov, cli = oauth.ProveedorOAuth(), _cliente()
    corre(prov.register_client(cli))
    url = corre(prov.authorize(cli, _params(state="valor-unico")))
    solicitud = parse_qs(urlparse(url).query)["solicitud"][0]

    destino = oauth.aprobar(solicitud, tokens.generar(_usuario()))
    assert parse_qs(urlparse(destino).query)["state"] == ["valor-unico"]


# ── Lo que NO tiene que poder hacerse ─────────────────────────────────────────

def test_el_codigo_es_de_un_solo_uso(db):
    """Si se pudiera canjear dos veces, un código interceptado seguiría
    sirviendo después de que el cliente legítimo lo usó."""
    from urllib.parse import parse_qs, urlparse

    prov, cli = oauth.ProveedorOAuth(), _cliente()
    corre(prov.register_client(cli))
    url = corre(prov.authorize(cli, _params()))
    solicitud = parse_qs(urlparse(url).query)["solicitud"][0]
    destino = oauth.aprobar(solicitud, tokens.generar(_usuario()))
    codigo = parse_qs(urlparse(destino).query)["code"][0]

    ac = corre(prov.load_authorization_code(cli, codigo))
    corre(prov.exchange_authorization_code(cli, ac))

    assert corre(prov.load_authorization_code(cli, codigo)) is None
    with pytest.raises(ValueError):
        corre(prov.exchange_authorization_code(cli, ac))


def test_la_solicitud_pendiente_se_consume(db):
    """Aprobar dos veces la misma solicitud no puede emitir dos códigos."""
    from urllib.parse import parse_qs, urlparse

    prov, cli = oauth.ProveedorOAuth(), _cliente()
    corre(prov.register_client(cli))
    url = corre(prov.authorize(cli, _params()))
    solicitud = parse_qs(urlparse(url).query)["solicitud"][0]
    token_ia = tokens.generar(_usuario())

    assert oauth.aprobar(solicitud, token_ia) is not None
    assert oauth.aprobar(solicitud, token_ia) is None


def test_un_token_de_ia_invalido_no_autoriza(db):
    from urllib.parse import parse_qs, urlparse

    prov, cli = oauth.ProveedorOAuth(), _cliente()
    corre(prov.register_client(cli))
    url = corre(prov.authorize(cli, _params()))
    solicitud = parse_qs(urlparse(url).query)["solicitud"][0]
    _usuario()

    assert oauth.aprobar(solicitud, "sma_no_existe") is None


def test_revocar_el_token_de_ia_corta_las_sesiones_oauth(db):
    """LA promesa del diseño. Si no se cumpliera, revocar en la pantalla daría
    una falsa sensación de haber cortado el acceso: el conector seguiría
    entrando con su token OAuth, que es una credencial distinta."""
    uid = _usuario()
    prov, _cli, tok = _flujo_hasta_tokens(uid)
    assert corre(prov.load_access_token(tok.access_token)) is not None

    tokens.revocar(uid)
    Session.remove()

    assert corre(prov.load_access_token(tok.access_token)) is None


def test_dar_de_baja_al_usuario_corta_el_acceso(db):
    """Sin pasos extra que alguien pueda olvidar."""
    from app.models import User

    uid = _usuario()
    prov, _cli, tok = _flujo_hasta_tokens(uid)

    s = get_session()
    s.query(User).filter(User.id == uid).first().active = False
    s.commit()
    Session.remove()

    assert corre(prov.load_access_token(tok.access_token)) is None


def test_un_token_de_acceso_vencido_no_entra(db):
    from app.models import OAuthGrant

    uid = _usuario()
    prov, _cli, tok = _flujo_hasta_tokens(uid)

    s = get_session()
    g = s.query(OAuthGrant).filter(
        OAuthGrant.token_hash == oauth._hash(tok.access_token)).first()
    g.expires_at = datetime.utcnow() - timedelta(seconds=1)
    s.commit()
    Session.remove()

    assert corre(prov.load_access_token(tok.access_token)) is None


def test_el_refresco_rota_y_el_viejo_muere(db):
    """Si el viejo siguiera sirviendo, un refresco filtrado valdría un mes."""
    uid = _usuario()
    prov, cli, tok = _flujo_hasta_tokens(uid)

    rt = corre(prov.load_refresh_token(cli, tok.refresh_token))
    nuevo = corre(prov.exchange_refresh_token(cli, rt, ["read"]))

    assert nuevo.refresh_token != tok.refresh_token
    assert corre(prov.load_refresh_token(cli, tok.refresh_token)) is None
    assert corre(prov.load_access_token(nuevo.access_token)) is not None


def test_al_renovar_no_se_pueden_ampliar_los_permisos(db):
    prov, cli, tok = _flujo_hasta_tokens(_usuario())
    rt = corre(prov.load_refresh_token(cli, tok.refresh_token))

    nuevo = corre(prov.exchange_refresh_token(cli, rt, ["read", "write:packs"]))

    assert "write:packs" not in (nuevo.scope or "")


def test_un_cliente_no_usa_el_codigo_de_otro(db):
    """El código está atado al cliente que lo pidió."""
    from urllib.parse import parse_qs, urlparse

    from mcp.shared.auth import OAuthClientInformationFull

    prov, cli = oauth.ProveedorOAuth(), _cliente()
    corre(prov.register_client(cli))
    url = corre(prov.authorize(cli, _params()))
    solicitud = parse_qs(urlparse(url).query)["solicitud"][0]
    destino = oauth.aprobar(solicitud, tokens.generar(_usuario()))
    codigo = parse_qs(urlparse(destino).query)["code"][0]

    intruso = OAuthClientInformationFull(
        client_id="otro-cliente", client_secret="x",
        redirect_uris=["https://malicioso.example/cb"],
        grant_types=["authorization_code"], response_types=["code"],
        token_endpoint_auth_method="client_secret_post")
    assert corre(prov.load_authorization_code(intruso, codigo)) is None


def test_una_solicitud_inventada_no_resuelve(db):
    assert oauth.resolver_solicitud("no-existe") is None
    assert oauth.aprobar("no-existe", tokens.generar(_usuario())) is None


# ── Las dos formas de presentar la misma identidad ────────────────────────────
# Regresión del hueco que encontró el ensayo de punta a punta y no los tests:
# el flujo OAuth entero funcionaba y emitía tokens válidos, pero el recurso los
# rechazaba porque el verificador solo conocía el token directo. Cada mitad
# andaba bien por separado.

def test_el_token_directo_de_conexion_ia_resuelve(db):
    uid = _usuario()
    at = corre(oauth.resolver_cualquier_token(tokens.generar(uid)))
    assert at is not None and at.subject == str(uid)


def test_el_token_emitido_por_oauth_tambien_resuelve(db):
    uid = _usuario()
    _prov, _cli, tok = _flujo_hasta_tokens(uid)
    at = corre(oauth.resolver_cualquier_token(tok.access_token))
    assert at is not None and at.subject == str(uid)


def test_los_dos_caminos_dan_la_misma_identidad(db):
    """Un admin tiene que ser admin por cualquiera de los dos, o vería de menos
    por uno y de más por el otro."""
    uid = _usuario("jefe", role="admin")
    _prov, _cli, tok = _flujo_hasta_tokens(uid)

    directo = corre(oauth.resolver_cualquier_token(tokens.generar(uid)))
    # Regenerar el token de IA no invalida la sesión OAuth ya emitida: el
    # usuario sigue teniendo token vigente, que es lo que se revalida.
    via_oauth = corre(oauth.resolver_cualquier_token(tok.access_token))

    assert directo.subject == via_oauth.subject == str(uid)
    assert directo.claims["is_admin"] is via_oauth.claims["is_admin"] is True


@pytest.mark.parametrize("basura", ["", "no-existe", "sma_inventado"])
def test_lo_que_no_es_ninguno_de_los_dos_no_resuelve(db, basura):
    _usuario()
    assert corre(oauth.resolver_cualquier_token(basura)) is None


# ── Lo que se guarda ──────────────────────────────────────────────────────────

def test_no_se_guarda_ningun_valor_en_claro(db):
    """Ni códigos ni tokens: si alguien lee la base, no obtiene credenciales."""
    uid = _usuario()
    _prov, _cli, tok = _flujo_hasta_tokens(uid)

    filas = get_session().execute(sa.text("SELECT * FROM oauth_grant")).mappings().all()
    todo = " ".join(str(v) for f in filas for v in f.values())
    for secreto in (tok.access_token, tok.refresh_token):
        assert secreto not in todo


def test_el_code_challenge_se_guarda_tal_cual(db):
    """PKCE lo valida el SDK contra este valor: si lo alteráramos, el canje
    fallaría siempre y el error no diría por qué."""
    from urllib.parse import parse_qs, urlparse

    prov, cli = oauth.ProveedorOAuth(), _cliente()
    corre(prov.register_client(cli))
    url = corre(prov.authorize(cli, _params()))
    solicitud = parse_qs(urlparse(url).query)["solicitud"][0]
    destino = oauth.aprobar(solicitud, tokens.generar(_usuario()))
    codigo = parse_qs(urlparse(destino).query)["code"][0]

    assert corre(prov.load_authorization_code(cli, codigo)).code_challenge == "reto"


def test_registrar_dos_veces_el_mismo_cliente_no_duplica(db):
    from app.models import OAuthClient

    prov, cli = oauth.ProveedorOAuth(), _cliente()
    corre(prov.register_client(cli))
    corre(prov.register_client(cli))

    assert get_session().query(OAuthClient).count() == 1
    assert corre(prov.get_client(_CLIENTE)) is not None


def test_un_cliente_desconocido_no_resuelve(db):
    assert corre(oauth.ProveedorOAuth().get_client("jamas-registrado")) is None


def test_revocar_borra_la_concesion(db):
    prov, cli, tok = _flujo_hasta_tokens(_usuario())
    rt = corre(prov.load_refresh_token(cli, tok.refresh_token))

    corre(prov.revoke_token(rt))

    assert corre(prov.load_refresh_token(cli, tok.refresh_token)) is None


def test_la_purga_limpia_lo_vencido_y_respeta_lo_vivo(db):
    from app.models import OAuthGrant

    uid = _usuario()
    _prov, _cli, tok = _flujo_hasta_tokens(uid)

    s = get_session()
    s.add(OAuthGrant(kind="code", token_hash="viejo", client_id=_CLIENTE,
                     user_id=uid, scopes="read",
                     expires_at=datetime.utcnow() - timedelta(days=1)))
    s.commit()
    Session.remove()

    assert oauth.purgar_vencidas() == 1
    Session.remove()
    assert corre(oauth.ProveedorOAuth().load_access_token(tok.access_token)) is not None
