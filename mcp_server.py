"""Servidor MCP: expone la capa de capacidades a un cliente de IA del usuario.

Es un caparazón delgado. Todo lo que se puede equivocar —qué herramientas se
publican, cómo se valida el token, qué mensaje ve el modelo ante un error, qué
NO tiene que ver— vive en `app/ai/` y está cubierto por la suite. Acá solo se
habla el protocolo.

Corre como un servicio APARTE (proceso `mcp` del Procfile), no dentro del web:
gunicorn tiene un solo worker con `--timeout 1800` para las corridas del Centro
de Datos, y el tráfico de un modelo no tiene por qué competir con eso ni tumbar
la UI si algo sale mal.

    uvicorn mcp_server:app --host 0.0.0.0 --port $PORT

Autenticación: el cliente manda `Authorization: Bearer <token>` con el token que
el usuario generó en la pantalla «Conexión IA». El SDK lo valida contra
`_VerificadorDeToken` antes de que ninguna herramienta corra.

**Fail-closed por construcción:** aunque el enganche de autenticación fallara,
`mcp_adapter.ejecutar()` rechaza toda llamada sin caller. El peor caso posible
es "no funciona nada", nunca "se expone todo".
"""
import json
import logging
import os

from mcp import types
from mcp.server import Server, ServerRequestContext
from mcp.server.auth.middleware.auth_context import get_access_token
from mcp.server.auth.provider import AccessToken, TokenVerifier
from mcp.server.auth.settings import AuthSettings
from mcp.server.transport_security import TransportSecuritySettings
from pydantic import AnyHttpUrl

from app.ai import mcp_adapter, tokens
from app.ai.caller import AiCaller
from app.logging_setup import configure_logging

logger = logging.getLogger(__name__)

# URL pública del servicio en Railway. Hace falta para dos cosas distintas:
# el SDK la publica como identificador del recurso, y la protección contra DNS
# rebinding exige declarar los hosts aceptados (por defecto solo entra
# localhost, así que sin esto Railway devolvería 421 a todo).
_URL_PUBLICA = os.environ.get("MCP_PUBLIC_URL", "http://127.0.0.1:8000")


def _hosts_permitidos(url: str) -> list[str]:
    """El host de la URL pública, con y sin puerto: el SDK compara contra el
    header `Host` tal como llega, y detrás de un proxy puede traer el puerto."""
    sin_esquema = url.split("://", 1)[-1].rstrip("/")
    host = sin_esquema.split("/", 1)[0]
    solo_host = host.split(":", 1)[0]
    return sorted({host, solo_host, f"{solo_host}:*"})


class _VerificadorDeToken(TokenVerifier):
    """Valida el token opaco de la aplicación. El SDK no opina sobre su forma.

    Devuelve None ante cualquier problema —inexistente, revocado, usuario dado
    de baja— sin distinguir cuál: quien prueba no tiene por qué saber en qué
    caso cayó. El rol viaja en `claims` para no volver a consultar la base en
    cada herramienta.
    """

    async def verify_token(self, token: str) -> AccessToken | None:
        from app.database import Session

        try:
            caller = tokens.resolver(token)
        except Exception:                                  # noqa: BLE001
            logger.exception("Error resolviendo un token de MCP")
            return None
        finally:
            # La sesión con ámbito es del hilo: si no se suelta, queda una
            # transacción abierta por request. En PostgreSQL eso fija el xmin
            # horizon y frena autovacuum en TODA la base — el problema que ya
            # apareció en las corridas del Centro de Datos.
            Session.remove()

        if caller is None:
            return None
        return AccessToken(
            token=token,
            client_id=str(caller.user_id),
            subject=str(caller.user_id),
            scopes=sorted(caller.scopes),
            claims={"is_admin": caller.is_admin},
        )


def _caller_autenticado() -> AiCaller | None:
    """El AiCaller del token que el SDK ya validó, o None.

    Se reconstruye de los claims en vez de volver a la base: el token se validó
    hace un instante y el rol no cambia dentro de una llamada.
    """
    token = get_access_token()
    if token is None or token.subject is None:
        return None
    try:
        return AiCaller(
            user_id=int(token.subject),
            is_admin=bool((token.claims or {}).get("is_admin", False)),
            scopes=frozenset(token.scopes or ()),
        )
    except (TypeError, ValueError):
        logger.warning("Token autenticado con subject/scopes inesperados")
        return None


async def _listar_herramientas(
    ctx: ServerRequestContext, params: types.PaginatedRequestParams | None
) -> types.ListToolsResult:
    # `tool_specs()` ya devuelve las claves del protocolo (`inputSchema`), que
    # el modelo de Tool acepta por alias.
    return types.ListToolsResult(
        tools=[types.Tool(**spec) for spec in mcp_adapter.tool_specs()])


async def _ejecutar_herramienta(
    ctx: ServerRequestContext, params: types.CallToolRequestParams
) -> types.CallToolResult:
    from app.database import Session

    caller = _caller_autenticado()
    try:
        salida = mcp_adapter.ejecutar(params.name, caller, params.arguments)
    finally:
        Session.remove()   # ver el comentario en _VerificadorDeToken

    if caller is not None:
        logger.info("MCP %s user=%s ok=%s", params.name, caller.user_id,
                    salida["ok"])

    texto = json.dumps(salida, ensure_ascii=False, default=str)
    return types.CallToolResult(
        content=[types.TextContent(type="text", text=texto)],
        is_error=not salida["ok"],
    )


configure_logging()

server = Server(
    "Stock Market Analysis",
    instructions=(
        "Datos de una plataforma de análisis técnico y fundamental. La lógica "
        "cuantitativa vive en la aplicación: pedile los números a las "
        "herramientas en vez de calcularlos por tu cuenta. Empezá por "
        "get_catalog, que dice qué existe en esta instalación, y consultá "
        "search_manual antes de explicar cómo funciona un cálculo: las reglas "
        "propias de este sistema no se deducen del conocimiento general de "
        "finanzas. Solo ves lo que el usuario dueño del token vería en pantalla."
    ),
    on_list_tools=_listar_herramientas,
    on_call_tool=_ejecutar_herramienta,
)

app = server.streamable_http_app(
    host="0.0.0.0",                                   # noqa: S104 — Railway
    transport_security=TransportSecuritySettings(
        allowed_hosts=_hosts_permitidos(_URL_PUBLICA),
    ),
    token_verifier=_VerificadorDeToken(),
    auth=AuthSettings(
        issuer_url=AnyHttpUrl(_URL_PUBLICA),
        resource_server_url=AnyHttpUrl(_URL_PUBLICA.rstrip("/") + "/mcp"),
    ),
)
