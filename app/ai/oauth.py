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
        from app.database import Session, get_session
        from app.models import OAuthClient

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
