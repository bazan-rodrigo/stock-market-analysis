"""Estado del servidor OAuth del MCP: clientes registrados y concesiones.

Hace falta porque los conectores remotos de las aplicaciones de IA no aceptan
un token pegado a mano: hacen **registro dinámico de cliente** y después el
baile de OAuth. Sin esto, agregar el conector falla con "no se pudo registrar
con el servicio de inicio de sesión".

**Todo se persiste, nada vive en memoria.** Un redeploy de Railway reinicia el
proceso: si los clientes registrados vivieran en memoria, cada deploy
desconectaría a todos los usuarios y habría que volver a agregar el conector a
mano — y peor, sin ningún error que explique por qué dejó de andar.
"""
from datetime import datetime

from sqlalchemy import (Boolean, Column, DateTime, Integer, String, Text)

from app.database import Base


class OAuthClient(Base):
    """Una aplicación de IA que se registró para conectarse.

    El `data` guarda el JSON completo que entregó el SDK
    (`OAuthClientInformationFull`) en vez de desarmarlo en columnas: es un
    documento del protocolo, no un modelo nuestro, y así una versión nueva del
    SDK que agregue campos no pierde información ni exige una migración.

    **No hay ningún secreto acá.** `ProveedorOAuth.register_client` registra a
    todos como clientes públicos (`token_endpoint_auth_method: none`, sin
    `client_secret`): el registro es abierto, así que un secreto autogenerado no
    acreditaría ninguna identidad. Lo que protege el canje es PKCE, y la
    identidad la pone la persona con su token de «Conexión IA». Filas viejas
    —anteriores a ese cambio— sí pueden traer un `client_secret` en claro en el
    JSON; se limpian volviendo a registrar el cliente.
    """

    __tablename__ = "oauth_client"

    client_id  = Column(String(255), primary_key=True)
    data       = Column(Text, nullable=False)
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)


class OAuthGrant(Base):
    """Todo lo que se emite durante el flujo, en una sola tabla.

    `kind` distingue las cuatro etapas:

    - `pending`: la autorización arrancó y falta que la persona se identifique.
      Guarda los parámetros del pedido para que la página de autorización no
      los reciba por la URL, donde podrían manipularse.
    - `code`: código de autorización, **de un solo uso** y de vida muy corta.
    - `access` / `refresh`: los tokens que usa la aplicación.

    Se guarda el HASH, nunca el valor. Igual que `users.mcp_token_hash`: si
    alguien lee la base, no obtiene credenciales utilizables.
    """

    __tablename__ = "oauth_grant"

    id         = Column(Integer, primary_key=True)
    kind       = Column(String(10), nullable=False, index=True)
    token_hash = Column(String(64), nullable=False, unique=True, index=True)
    client_id  = Column(String(255), nullable=False, index=True)
    # NULL mientras es `pending`: todavía no sabemos quién es. Sin FK a propósito
    # (igual que las tablas anchas): el borrado de un usuario lo limpia el
    # propio servicio, y una FK acá obligaría a ordenar los DELETE.
    user_id    = Column(Integer)
    scopes     = Column(Text)
    expires_at = Column(DateTime, index=True)
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)

    # Solo para `pending` y `code` (el SDK valida PKCE con code_challenge).
    state                  = Column(Text)
    code_challenge         = Column(String(255))
    redirect_uri           = Column(Text)
    redirect_uri_explicit  = Column(Boolean)
    resource               = Column(Text)
