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
from html import escape

from mcp import types
from mcp.server import Server, ServerRequestContext
from mcp.server.auth.middleware.auth_context import get_access_token
from mcp.server.auth.provider import AccessToken, TokenVerifier
from mcp.server.auth.settings import AuthSettings
from mcp.server.transport_security import TransportSecuritySettings
from pydantic import AnyHttpUrl
from starlette.requests import Request
from starlette.responses import HTMLResponse, RedirectResponse
from starlette.routing import Route

from app.ai import mcp_adapter, oauth, tokens
from app.ai.caller import AiCaller
from app.logging_setup import configure_logging

logger = logging.getLogger(__name__)

# URL pública del servicio. Hace falta para dos cosas distintas: el SDK la
# publica como identificador del recurso, y la protección contra DNS rebinding
# exige declarar los hosts aceptados (por defecto solo entra localhost, así que
# sin esto un deploy devuelve error a todo).
#
# La normalización vive en mcp_adapter —no acá— porque este archivo no lo ve la
# suite: el primer deploy se cayó justamente por una URL sin esquema, que es el
# tipo de error que tiene que estar cubierto por un test.
_URL_PUBLICA = mcp_adapter.normalizar_url_publica(os.environ.get("MCP_PUBLIC_URL"))

# Uno solo, compartido: lo usan el verificador de tokens y el servidor de
# autorización. Si fueran dos instancias no habría bug (no tiene estado), pero
# tenerlo explícito deja claro que es el mismo proveedor de las dos puntas.
_PROVEEDOR = oauth.ProveedorOAuth()


class _VerificadorDeToken(TokenVerifier):
    """Valida el token que llega en `Authorization`, venga por donde venga.

    Hay DOS formas de presentar la misma identidad y las dos tienen que entrar
    por acá, porque el SDK valida todo pedido al recurso con este verificador:

    1. **El token de «Conexión IA» directo** — para clientes que permiten
       mandar un header (Claude Code, cualquier cliente programático).
    2. **Un token de acceso emitido por nuestro propio OAuth** — para los
       conectores remotos, que NO permiten mandar un header y exigen el flujo
       completo.

    Que faltara la segunda es un hueco fácil de dejar: el flujo OAuth entero
    funciona, emite tokens perfectamente válidos… y después el recurso los
    rechaza. Lo detectó el ensayo de punta a punta, no los tests unitarios,
    porque cada mitad andaba bien por separado.

    Devuelve None ante cualquier problema sin distinguir cuál: quien prueba no
    tiene por qué saber en qué caso cayó. El rol viaja en `claims` para no
    volver a consultar la base en cada herramienta.
    """

    async def verify_token(self, token: str) -> AccessToken | None:
        from app.database import Session

        try:
            return await oauth.resolver_cualquier_token(token)
        except Exception:                                  # noqa: BLE001
            logger.exception("Error resolviendo un token")
            return None
        finally:
            # La sesión con ámbito es del hilo: si no se suelta, queda una
            # transacción abierta por request. En PostgreSQL eso fija el xmin
            # horizon y frena autovacuum en TODA la base — el problema que ya
            # apareció en las corridas del Centro de Datos.
            Session.remove()


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
    specs = mcp_adapter.tool_specs()
    # Se registra a propósito: cuando un cliente "no ve" una herramienta nueva,
    # lo primero que hay que saber es si llegó a preguntar y qué se le contestó.
    # Sin esta línea no había forma de distinguir un caché del cliente de un
    # deploy que no tomó el código nuevo.
    logger.info("MCP tools/list → %d herramientas: %s",
                len(specs), ", ".join(s["name"] for s in specs))
    return types.ListToolsResult(
        tools=[types.Tool(**spec) for spec in specs])


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


# ── Página de autorización ───────────────────────────────────────────────────
# Los conectores remotos de las aplicaciones de IA no dejan pegar un token a
# mano: exigen OAuth. Esta es la pantalla del medio, y pide el token de
# «Conexión IA» en vez de usuario y contraseña — así este servicio nunca ve una
# contraseña y queda UN solo lugar donde cortar el acceso.

_PAGINA = """<!DOCTYPE html>
<html lang="es" data-bs-theme="dark"><head><meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Autorizar acceso — Stock Market Analysis</title>
<link href="https://cdn.jsdelivr.net/npm/bootstrap@5.3.3/dist/css/bootstrap.min.css" rel="stylesheet">
<style>body{{background:#222;color:#dee2e6}}
.card{{background:#2d3338;border:1px solid #495057}}
.form-control,.form-control:focus{{background:#1a1d20;color:#dee2e6;border-color:#495057}}</style>
</head><body><div class="container"><div class="row justify-content-center mt-5">
<div class="col-md-6"><div class="card shadow p-4">
<h5 class="mb-3">Autorizar acceso</h5>
<p class="small mb-3"><strong>{cliente}</strong> quiere leer los datos que vos
ves en Stock Market Analysis. Solo podrá <strong>consultar</strong>: no puede
modificar ni borrar nada, ni ver lo que vos no verías.</p>
{error}
<form method="post" action="/ia/autorizar">
  <input type="hidden" name="solicitud" value="{solicitud}">
  <div class="mb-3">
    <label class="form-label small">Token de Conexión IA</label>
    <input type="password" name="token" class="form-control" autofocus required
           placeholder="sma_...">
    <div class="form-text">Lo generás en la aplicación, en el menú de tu
      usuario → <strong>Conexión IA</strong>.</div>
  </div>
  <button type="submit" class="btn btn-primary w-100">Autorizar</button>
</form>
</div></div></div></div></body></html>"""

_ERROR = '<div class="alert alert-danger py-2 small">{}</div>'


def _render(solicitud: str, cliente: str, error: str = "") -> HTMLResponse:
    return HTMLResponse(_PAGINA.format(
        solicitud=escape(solicitud), cliente=escape(cliente),
        error=_ERROR.format(escape(error)) if error else ""))


async def _autorizar_get(request: Request):
    solicitud = request.query_params.get("solicitud", "")
    datos = oauth.resolver_solicitud(solicitud)
    if datos is None:
        return HTMLResponse(
            "<p>Esta solicitud de autorización no existe o venció. "
            "Volvé a intentar desde tu aplicación de IA.</p>", status_code=400)
    return _render(solicitud, datos["client_name"])


async def _autorizar_post(request: Request):
    form = await request.form()
    solicitud = str(form.get("solicitud") or "")
    datos = oauth.resolver_solicitud(solicitud)
    if datos is None:
        return HTMLResponse(
            "<p>Esta solicitud de autorización no existe o venció. "
            "Volvé a intentar desde tu aplicación de IA.</p>", status_code=400)

    destino = oauth.aprobar(solicitud, str(form.get("token") or ""))
    if destino is None:
        # Un solo mensaje para token inválido, revocado o usuario dado de baja:
        # distinguirlos le diría a quien prueba en cuál caso cayó.
        return _render(solicitud, datos["client_name"],
                       "Ese token no es válido. Verificá que lo hayas copiado "
                       "completo desde la pantalla Conexión IA.")
    return RedirectResponse(destino, status_code=302)


_RUTAS = [
    Route("/ia/autorizar", _autorizar_get, methods=["GET"]),
    Route("/ia/autorizar", _autorizar_post, methods=["POST"]),
]


configure_logging()

# Al arrancar, decir con qué configuración quedó: si un cliente recibe error de
# host, esta línea es la que lo explica sin tener que adivinar.
logger.info("Servidor MCP — URL pública: %s | hosts aceptados: %s",
            _URL_PUBLICA, ", ".join(mcp_adapter.hosts_permitidos(_URL_PUBLICA)))
# Qué versión del catálogo quedó arriba. Con esta línea, mirar los logs después
# de un deploy alcanza para saber si el código nuevo tomó, sin necesitar un
# cliente conectado para averiguarlo.
_SPECS = mcp_adapter.tool_specs()
logger.info("Herramientas publicadas (%d): %s",
            len(_SPECS), ", ".join(s["name"] for s in _SPECS))
if os.environ.get("MCP_PUBLIC_URL") is None:
    logger.warning(
        "MCP_PUBLIC_URL no está definida: se asume %s. En un deploy hay que "
        "definirla con el dominio público del servicio o TODO pedido externo "
        "va a ser rechazado.", _URL_PUBLICA)

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
        allowed_hosts=mcp_adapter.hosts_permitidos(_URL_PUBLICA),
    ),
    token_verifier=_VerificadorDeToken(),
    # El proveedor OAuth convive con el verificador de tokens: un cliente que
    # puede mandar un header usa el token directo; un conector remoto —que no
    # puede— pasa por el flujo completo. Los dos terminan en el mismo usuario.
    auth_server_provider=_PROVEEDOR,
    custom_starlette_routes=_RUTAS,
    auth=AuthSettings(
        issuer_url=AnyHttpUrl(_URL_PUBLICA),
        resource_server_url=AnyHttpUrl(_URL_PUBLICA.rstrip("/") + "/mcp"),
        # Las dos salen de `oauth` —no se arman acá— para que la metadata que se
        # publica más abajo describa exactamente esta configuración y no una
        # copia que se despegue con el tiempo.
        client_registration_options=oauth.opciones_de_registro(),
        revocation_options=oauth.opciones_de_revocacion(),
    ),
)

# El SDK anuncia métodos de autenticación de cliente que este servidor ya no
# usa. Se inserta ADELANTE porque Starlette resuelve por orden: las rutas
# propias del SDK se registran primero y `custom_starlette_routes` va al final,
# así que es el único lugar desde donde se puede corregir.
app.router.routes.insert(0, oauth.ruta_de_metadata(AnyHttpUrl(_URL_PUBLICA)))

# Envuelve todo: sin esto, un flujo de OAuth que se rompe deja en el log un
# `401` pelado y ninguna pista de por qué.
app = oauth.LogDeFallosOAuth(app)

# Higiene: sin esto la tabla crece para siempre con códigos de 60 segundos y
# refrescos viejos. Best-effort — si la migración 0100 todavía no se aplicó, no
# tiene que impedir que el servidor arranque.
try:
    _purgadas = oauth.purgar_vencidas()
    if _purgadas:
        logger.info("OAuth: %d concesiones vencidas purgadas al arranque", _purgadas)
except Exception as _exc:                                   # noqa: BLE001
    logger.warning("No se pudieron purgar las concesiones OAuth: %s", _exc)
