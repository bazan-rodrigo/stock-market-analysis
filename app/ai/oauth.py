"""Servidor de autorización OAuth para el MCP.

Existe por una razón muy concreta: los conectores remotos de las aplicaciones
de IA **no dejan pegar un token a mano**. Hacen registro dinámico de cliente y
después el flujo de OAuth; sin un servidor de autorización, agregar el conector
falla con "no se pudo registrar con el servicio de inicio de sesión".

**La identidad sigue siendo el token de «Conexión IA»**, no una contraseña. La
página de autorización pide ese token, y OAuth queda como el envoltorio que el
protocolo exige. Tres consecuencias buscadas:

- El servicio MCP nunca ve una contraseña, ni ahora ni nunca.
- Hay UN solo lugar donde se corta el acceso: revocar el token en la pantalla
  mata también las sesiones OAuth (`load_access_token` lo revalida en cada
  llamada). Con dos credenciales independientes, revocar una dejaría viva la
  otra — el tipo de detalle que se olvida justo cuando importa.
- Dar de baja a un usuario también lo corta, sin ningún paso extra.

Todo lo emitido se guarda **hasheado**. PKCE lo valida el SDK con el
`code_challenge` que guardamos; acá solo hay que persistirlo fielmente.
"""
import hashlib
import json
import logging
import secrets
from datetime import datetime, timedelta

from mcp.server.auth.provider import (AccessToken, AuthorizationCode,
                                      AuthorizationParams,
                                      OAuthAuthorizationServerProvider,
                                      RefreshToken)
from mcp.shared.auth import OAuthClientInformationFull, OAuthToken

from app.ai.caller import SCOPE_READ

logger = logging.getLogger(__name__)

# El código vive lo justo para el ida y vuelta del navegador. La recomendación
# de OAuth 2.1 es "lo más corto posible"; un minuto sobra y acota la ventana en
# la que un código filtrado sirve de algo.
CODIGO_SEGUNDOS = 60
# La autorización a medias caduca sola si la persona abandona la pestaña.
PENDIENTE_SEGUNDOS = 600
ACCESO_SEGUNDOS = 3600
REFRESCO_SEGUNDOS = 60 * 60 * 24 * 30

_PENDIENTE, _CODIGO, _ACCESO, _REFRESCO = "pending", "code", "access", "refresh"


def _hash(valor: str) -> str:
    return hashlib.sha256(valor.encode("utf-8")).hexdigest()


def _nuevo() -> str:
    return secrets.token_urlsafe(32)


def _ahora() -> datetime:
    return datetime.utcnow()


def _scopes(texto: str | None) -> list[str]:
    return (texto or "").split()


class ProveedorOAuth(OAuthAuthorizationServerProvider):
    """Implementa el contrato del SDK contra las tablas `oauth_*`."""

    # ── Clientes ─────────────────────────────────────────────────────────────

    async def get_client(self, client_id: str) -> OAuthClientInformationFull | None:
        from app.database import Session, get_session
        from app.models import OAuthClient

        try:
            fila = get_session().query(OAuthClient).filter(
                OAuthClient.client_id == client_id).first()
            if fila is None:
                return None
            return OAuthClientInformationFull.model_validate_json(fila.data)
        finally:
            Session.remove()

    async def register_client(self, client_info: OAuthClientInformationFull) -> None:
        """Registra al cliente, siempre como **público** (sin secret).

        El SDK, si el cliente no aclara nada, le inventa un `client_secret` y lo
        anota como confidencial. Eso rompe conectores reales por un desencuentro
        entre lo que el cliente DECLARA al registrarse y lo que MANDA al canjear:
        Google declara `client_secret_basic` y después no manda ese header, y el
        SDK —que mira solo donde el cliente dijo— contesta 401 al final del
        flujo, con el usuario ya autorizado. Se veía como "no se pudo vincular
        la cuenta" sin ninguna pista de por qué.

        Un cliente de registro dinámico es público por definición: el registro
        está abierto a cualquiera, así que ese secret no acredita ninguna
        identidad. Lo que protege el canje es PKCE, y la identidad la pone el
        token de «Conexión IA» en la pantalla de autorización.

        Se limpian LAS DOS cosas a propósito: con el secret guardado y el método
        en `none`, el SDK igual lo exige y el 401 vuelve. Y se muta el objeto que
        llega —no una copia— porque el handler arma con él la respuesta de
        registro DESPUÉS de llamarnos: así el cliente se entera de que quedó
        público en vez de recibir un secret que nunca va a servirle.
        """
        from app.database import Session, get_session
        from app.models import OAuthClient

        client_info.token_endpoint_auth_method = "none"
        client_info.client_secret = None
        client_info.client_secret_expires_at = None
        # Red de seguridad del scope. Si el cliente no declaró ninguno y la
        # configuración del servidor tampoco pone un default, queda en None — y
        # entonces `validate_scope` compara contra una lista VACÍA y rechaza
        # cualquier `scope` que el cliente pida en /authorize. Un cliente que no
        # manda scope nunca lo nota; uno que sí, rebota siempre. La config vive
        # en `opciones_de_registro()`, pero eso es un argumento que se puede
        # olvidar: acá no.
        if not client_info.scope:
            client_info.scope = SCOPE_READ

        s = get_session()
        try:
            fila = s.query(OAuthClient).filter(
                OAuthClient.client_id == client_info.client_id).first()
            datos = client_info.model_dump_json(exclude_none=True)
            if fila is None:
                s.add(OAuthClient(client_id=client_info.client_id, data=datos))
            else:
                fila.data = datos     # re-registro: idempotente
            s.commit()
            logger.info("OAuth: cliente registrado %s (%s)",
                        client_info.client_id, client_info.client_name or "sin nombre")
        except Exception:
            s.rollback()
            raise
        finally:
            Session.remove()

    # ── Autorización ─────────────────────────────────────────────────────────

    async def authorize(self, client: OAuthClientInformationFull,
                        params: AuthorizationParams) -> str:
        """Devuelve la URL de NUESTRA página de autorización.

        Los parámetros del pedido se guardan en la base y solo viaja un
        identificador opaco: si fueran por la URL, quien tenga el link podría
        cambiar el `redirect_uri` y desviar el código a otro lado.
        """
        from app.ai.mcp_adapter import url_publica
        from app.database import Session, get_session
        from app.models import OAuthGrant

        solicitud = _nuevo()
        s = get_session()
        try:
            s.add(OAuthGrant(
                kind=_PENDIENTE,
                token_hash=_hash(solicitud),
                client_id=client.client_id,
                scopes=" ".join(params.scopes or [SCOPE_READ]),
                expires_at=_ahora() + timedelta(seconds=PENDIENTE_SEGUNDOS),
                state=params.state,
                code_challenge=params.code_challenge,
                redirect_uri=str(params.redirect_uri),
                redirect_uri_explicit=bool(params.redirect_uri_provided_explicitly),
                resource=params.resource,
            ))
            s.commit()
        except Exception:
            s.rollback()
            raise
        finally:
            Session.remove()

        return f"{url_publica()}/ia/autorizar?solicitud={solicitud}"

    async def load_authorization_code(
        self, client: OAuthClientInformationFull, authorization_code: str
    ) -> AuthorizationCode | None:
        from app.database import Session, get_session
        from app.models import OAuthGrant

        try:
            g = get_session().query(OAuthGrant).filter(
                OAuthGrant.token_hash == _hash(authorization_code),
                OAuthGrant.kind == _CODIGO,
                OAuthGrant.client_id == client.client_id,
            ).first()
            if g is None or g.expires_at <= _ahora():
                return None
            return AuthorizationCode(
                code=authorization_code,
                scopes=_scopes(g.scopes),
                expires_at=g.expires_at.timestamp(),
                client_id=g.client_id,
                code_challenge=g.code_challenge or "",
                redirect_uri=g.redirect_uri,
                redirect_uri_provided_explicitly=bool(g.redirect_uri_explicit),
                resource=g.resource,
                subject=str(g.user_id),
            )
        finally:
            Session.remove()

    async def exchange_authorization_code(
        self, client: OAuthClientInformationFull, authorization_code: AuthorizationCode
    ) -> OAuthToken:
        """Canjea el código por tokens. El código es de UN SOLO USO: se borra
        acá mismo, así que reusarlo (o un atacante que lo haya interceptado)
        no obtiene nada."""
        from app.database import Session, get_session
        from app.models import OAuthGrant

        s = get_session()
        try:
            g = s.query(OAuthGrant).filter(
                OAuthGrant.token_hash == _hash(authorization_code.code),
                OAuthGrant.kind == _CODIGO,
            ).first()
            if g is None or g.expires_at <= _ahora():
                raise ValueError("código de autorización inválido o vencido")

            user_id, scopes = g.user_id, g.scopes
            s.delete(g)
            acceso, refresco = _nuevo(), _nuevo()
            s.add(OAuthGrant(kind=_ACCESO, token_hash=_hash(acceso),
                             client_id=client.client_id, user_id=user_id,
                             scopes=scopes,
                             expires_at=_ahora() + timedelta(seconds=ACCESO_SEGUNDOS)))
            s.add(OAuthGrant(kind=_REFRESCO, token_hash=_hash(refresco),
                             client_id=client.client_id, user_id=user_id,
                             scopes=scopes,
                             expires_at=_ahora() + timedelta(seconds=REFRESCO_SEGUNDOS)))
            s.commit()
        except Exception:
            s.rollback()
            raise
        finally:
            Session.remove()

        logger.info("OAuth: tokens emitidos para user=%s cliente=%s",
                    user_id, client.client_id)
        return OAuthToken(access_token=acceso, token_type="Bearer",
                          expires_in=ACCESO_SEGUNDOS, scope=scopes,
                          refresh_token=refresco)

    # ── Tokens ───────────────────────────────────────────────────────────────

    async def load_access_token(self, token: str) -> AccessToken | None:
        """Valida el token de acceso Y que la persona siga habilitada.

        Se revalida en CADA llamada contra `users`, no solo al emitir. Es lo
        que hace verdadera la promesa de que revocar el token de «Conexión IA»
        corta también las sesiones OAuth, y que dar de baja a un usuario le
        corta el acceso sin ningún paso extra. Es una consulta por id, indexada.
        """
        from app.database import Session, get_session
        from app.models import OAuthGrant, User

        try:
            s = get_session()
            g = s.query(OAuthGrant).filter(
                OAuthGrant.token_hash == _hash(token),
                OAuthGrant.kind == _ACCESO,
            ).first()
            if g is None or g.expires_at <= _ahora():
                return None

            user = s.query(User).filter(User.id == g.user_id).first()
            if user is None or not user.active or user.mcp_token_hash is None:
                return None

            return AccessToken(
                token=token, client_id=g.client_id, subject=str(user.id),
                scopes=_scopes(g.scopes),
                expires_at=int(g.expires_at.timestamp()),
                claims={"is_admin": bool(user.is_admin)},
            )
        finally:
            Session.remove()

    async def load_refresh_token(self, client: OAuthClientInformationFull,
                                 refresh_token: str) -> RefreshToken | None:
        from app.database import Session, get_session
        from app.models import OAuthGrant

        try:
            g = get_session().query(OAuthGrant).filter(
                OAuthGrant.token_hash == _hash(refresh_token),
                OAuthGrant.kind == _REFRESCO,
                OAuthGrant.client_id == client.client_id,
            ).first()
            if g is None or g.expires_at <= _ahora():
                return None
            return RefreshToken(token=refresh_token, client_id=g.client_id,
                                scopes=_scopes(g.scopes),
                                expires_at=int(g.expires_at.timestamp()),
                                subject=str(g.user_id))
        finally:
            Session.remove()

    async def exchange_refresh_token(self, client: OAuthClientInformationFull,
                                     refresh_token: RefreshToken,
                                     scopes: list[str]) -> OAuthToken:
        """Renueva. El refresh se ROTA: el viejo deja de servir en el acto, así
        que si uno filtrado se usa después del legítimo, falla."""
        from app.database import Session, get_session
        from app.models import OAuthGrant

        s = get_session()
        try:
            viejo = s.query(OAuthGrant).filter(
                OAuthGrant.token_hash == _hash(refresh_token.token),
                OAuthGrant.kind == _REFRESCO,
            ).first()
            if viejo is None or viejo.expires_at <= _ahora():
                raise ValueError("token de refresco inválido o vencido")

            user_id = viejo.user_id
            # No se pueden ampliar permisos al renovar: como mucho, los mismos.
            otorgados = _scopes(viejo.scopes)
            pedidos = [e for e in (scopes or otorgados) if e in otorgados] or otorgados
            texto = " ".join(pedidos)

            s.delete(viejo)
            acceso, refresco = _nuevo(), _nuevo()
            s.add(OAuthGrant(kind=_ACCESO, token_hash=_hash(acceso),
                             client_id=client.client_id, user_id=user_id,
                             scopes=texto,
                             expires_at=_ahora() + timedelta(seconds=ACCESO_SEGUNDOS)))
            s.add(OAuthGrant(kind=_REFRESCO, token_hash=_hash(refresco),
                             client_id=client.client_id, user_id=user_id,
                             scopes=texto,
                             expires_at=_ahora() + timedelta(seconds=REFRESCO_SEGUNDOS)))
            s.commit()
        except Exception:
            s.rollback()
            raise
        finally:
            Session.remove()

        return OAuthToken(access_token=acceso, token_type="Bearer",
                          expires_in=ACCESO_SEGUNDOS, scope=texto,
                          refresh_token=refresco)

    async def revoke_token(self, token) -> None:
        from app.database import Session, get_session
        from app.models import OAuthGrant

        s = get_session()
        try:
            s.query(OAuthGrant).filter(
                OAuthGrant.token_hash == _hash(getattr(token, "token", ""))
            ).delete()
            s.commit()
        except Exception:
            s.rollback()
            raise
        finally:
            Session.remove()


# ── La página de autorización ────────────────────────────────────────────────

def resolver_solicitud(solicitud: str) -> dict | None:
    """Los datos de una autorización pendiente, o None si no existe o venció."""
    from app.database import Session, get_session
    from app.models import OAuthClient, OAuthGrant

    try:
        s = get_session()
        g = s.query(OAuthGrant).filter(
            OAuthGrant.token_hash == _hash(solicitud),
            OAuthGrant.kind == _PENDIENTE,
        ).first()
        if g is None or g.expires_at <= _ahora():
            return None
        cli = s.query(OAuthClient).filter(
            OAuthClient.client_id == g.client_id).first()
        nombre = g.client_id
        if cli is not None:
            try:
                nombre = json.loads(cli.data).get("client_name") or g.client_id
            except ValueError:
                pass
        return {"client_id": g.client_id, "client_name": nombre,
                "scopes": _scopes(g.scopes)}
    finally:
        Session.remove()


def aprobar(solicitud: str, token_de_ia: str) -> str | None:
    """Valida el token de «Conexión IA» y emite el código.

    Devuelve la URL a la que hay que redirigir al navegador, o None si algo no
    cierra (solicitud vencida, token inválido, usuario dado de baja). Un solo
    None para todos los casos: distinguirlos le diría a quien prueba en cuál cayó.
    """
    from urllib.parse import urlencode

    from app.ai import tokens
    from app.database import Session, get_session
    from app.models import OAuthGrant

    caller = tokens.resolver(token_de_ia)
    if caller is None or caller.user_id is None:
        return None

    s = get_session()
    try:
        g = s.query(OAuthGrant).filter(
            OAuthGrant.token_hash == _hash(solicitud),
            OAuthGrant.kind == _PENDIENTE,
        ).first()
        if g is None or g.expires_at <= _ahora():
            return None

        codigo = _nuevo()
        destino, estado = g.redirect_uri, g.state
        s.add(OAuthGrant(
            kind=_CODIGO, token_hash=_hash(codigo), client_id=g.client_id,
            user_id=caller.user_id, scopes=g.scopes,
            expires_at=_ahora() + timedelta(seconds=CODIGO_SEGUNDOS),
            code_challenge=g.code_challenge, redirect_uri=g.redirect_uri,
            redirect_uri_explicit=g.redirect_uri_explicit, resource=g.resource,
        ))
        s.delete(g)          # la pendiente se consume
        s.commit()
    except Exception:
        s.rollback()
        raise
    finally:
        Session.remove()

    logger.info("OAuth: autorización aprobada por user=%s", caller.user_id)
    params = {"code": codigo}
    if estado:
        params["state"] = estado
    unir = "&" if "?" in destino else "?"
    return f"{destino}{unir}{urlencode(params)}"


async def resolver_cualquier_token(token: str) -> AccessToken | None:
    """Valida el token de `Authorization`, venga por donde venga.

    Hay DOS formas de presentar la MISMA identidad, y las dos tienen que
    resolver acá porque el SDK valida con esto todo pedido al recurso:

    1. **El token de «Conexión IA» directo**, para clientes que permiten mandar
       un header (Claude Code, cualquier cliente programático).
    2. **Un token de acceso emitido por nuestro OAuth**, para los conectores
       remotos, que NO permiten mandar un header y exigen el flujo completo.

    Que faltara la segunda es un hueco fácil de dejar y difícil de ver: el
    flujo OAuth entero funciona y emite tokens perfectamente válidos… y después
    el recurso los rechaza. Cada mitad anda bien por separado, así que lo
    detectó el ensayo de punta a punta y no los tests unitarios. Por eso vive
    acá y no en `mcp_server.py`: para que haya un test que lo fije.
    """
    from app.ai import tokens
    from app.database import Session

    try:
        caller = tokens.resolver(token)
    finally:
        Session.remove()

    if caller is not None:
        return AccessToken(
            token=token, client_id=str(caller.user_id),
            subject=str(caller.user_id), scopes=sorted(caller.scopes),
            claims={"is_admin": caller.is_admin})

    return await ProveedorOAuth().load_access_token(token)


# ── Cómo se anuncia el servicio ──────────────────────────────────────────────
# Vive acá y no en `mcp_server.py` porque ese archivo no lo ve la suite, y estas
# tres decisiones ya fallaron en silencio una vez cada una.

METODO_DE_AUTENTICACION = "none"


def opciones_de_registro():
    """Cómo se registran los clientes nuevos.

    `default_scopes` es lo que evita el agujero descripto en `register_client`:
    sin él, todo cliente queda con `scope=None` y cualquiera que pida un scope
    en /authorize rebota con `invalid_scope`. `valid_scopes` acota lo que se
    puede pedir y —efecto secundario buscado— es de donde el SDK saca el
    `scopes_supported` que publica en la metadata.
    """
    from mcp.server.auth.settings import ClientRegistrationOptions

    return ClientRegistrationOptions(
        enabled=True, valid_scopes=[SCOPE_READ], default_scopes=[SCOPE_READ])


def opciones_de_revocacion():
    from mcp.server.auth.settings import RevocationOptions

    return RevocationOptions(enabled=True)


RUTA_DE_METADATA = "/.well-known/oauth-authorization-server"


def metadata_publicada(issuer_url):
    """La metadata del servidor de autorización, con los métodos que de verdad
    se aceptan.

    El SDK publica `["client_secret_post", "client_secret_basic"]` fijo, pero
    `register_client` emite clientes **públicos**: un cliente que le cree a esa
    lista se registra pidiendo un secreto y después el canje no le cierra. Es el
    desencuentro que rompió a Google, visto desde el otro lado.

    Se construye con el mismo `build_metadata` del SDK y solo se corrige ese
    campo: si una versión nueva agrega campos, no quedan afuera.
    """
    from mcp.server.auth.routes import build_metadata

    md = build_metadata(
        issuer_url=issuer_url,
        service_documentation_url=None,
        client_registration_options=opciones_de_registro(),
        revocation_options=opciones_de_revocacion(),
    )
    md.token_endpoint_auth_methods_supported = [METODO_DE_AUTENTICACION]
    return md


def ruta_de_metadata(issuer_url):
    """La metadata anterior, como `Route` para insertar ANTES de las del SDK.

    Starlette resuelve por orden y gana la primera; `custom_starlette_routes` se
    agrega al final, así que desde ahí el pedido nunca llegaría.
    """
    from mcp.server.auth.handlers.metadata import MetadataHandler
    from mcp.server.auth.routes import cors_middleware
    from starlette.routing import Route

    handler = MetadataHandler(metadata_publicada(issuer_url))
    return Route(RUTA_DE_METADATA,
                 endpoint=cors_middleware(handler.handle, ["GET", "OPTIONS"]),
                 methods=["GET", "OPTIONS"])


# ── Por qué falló ────────────────────────────────────────────────────────────

_RUTAS_VIGILADAS = frozenset({"/authorize", "/token", "/register", "/revoke"})


def _credenciales_presentadas(scope) -> str:
    """Cómo vino autenticado el pedido. **El esquema, jamás el valor.**"""
    for clave, valor in scope.get("headers") or ():
        if clave == b"authorization":
            esquema = valor.split(b" ")[0].decode("ascii", "replace")
            return f"Authorization: {esquema}"
    return "sin header Authorization"


class LogDeFallosOAuth:
    """Deja en el log el motivo de un fallo de OAuth.

    Sin esto, un flujo roto se ve como `POST /token 401` y nada más: el SDK
    contesta el motivo al cliente, el cliente lo traduce a "no se pudo vincular
    la cuenta", y del lado del servidor no queda rastro. Encontrar la causa del
    401 de Google exigió interrogar el endpoint desde afuera, con pedidos
    fabricados a mano contra producción. Esa arqueología es lo que esto evita.

    Dos formas de fallar, porque OAuth tiene dos:

    - **4xx** en cualquiera de los endpoints: el cuerpo trae `error` y
      `error_description`, que es exactamente el diagnóstico.
    - **302 con `error=` en el `Location`**, que es como falla /authorize.
      Devuelve 302 igual que un éxito, así que sin mirar el destino un rechazo
      es indistinguible de un flujo sano. El `invalid_scope` que estuvo vivo
      hasta hoy caía justo acá.

    Es ASGI puro y no HTTP middleware de Starlette a propósito: los mensajes
    pasan sin tocarse y las rutas que no son de OAuth ni entran. `/mcp` hace
    streaming, y bufferearlo lo rompería.

    No se registra ningún secreto: del pedido solo el ESQUEMA de autenticación,
    y del `Location` solo cuando lleva `error=` — nunca cuando lleva el `code`.
    """

    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope.get("type") != "http" or scope.get("path") not in _RUTAS_VIGILADAS:
            await self.app(scope, receive, send)
            return

        estado: dict = {"status": 200, "motivo": ""}
        cuerpo = bytearray()

        async def espiar(mensaje):
            if mensaje["type"] == "http.response.start":
                estado["status"] = mensaje["status"]
                for clave, valor in mensaje.get("headers") or ():
                    if clave.lower() == b"location":
                        destino = valor.decode("utf-8", "replace")
                        if "error=" in destino:
                            estado["motivo"] = destino.split("?", 1)[-1]
            elif mensaje["type"] == "http.response.body" and estado["status"] >= 400:
                cuerpo.extend(mensaje.get("body") or b"")
            await send(mensaje)

        await self.app(scope, receive, espiar)

        motivo = estado["motivo"] or cuerpo.decode("utf-8", "replace")
        if estado["status"] >= 400 or estado["motivo"]:
            logger.warning(
                "OAuth RECHAZADO %s %s → %s | %s | %s",
                scope.get("method"), scope.get("path"), estado["status"],
                _credenciales_presentadas(scope), motivo[:500])


def purgar_vencidas() -> int:
    """Borra lo vencido. Se llama al arrancar: sin esto la tabla crece para
    siempre con códigos de 60 segundos y refrescos viejos."""
    from app.database import Session, get_session
    from app.models import OAuthGrant

    s = get_session()
    try:
        n = s.query(OAuthGrant).filter(OAuthGrant.expires_at <= _ahora()).delete()
        s.commit()
        return int(n or 0)
    except Exception:
        s.rollback()
        return 0
    finally:
        Session.remove()
