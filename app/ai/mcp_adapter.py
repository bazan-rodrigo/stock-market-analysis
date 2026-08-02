"""Traducción entre el registro de herramientas y el protocolo MCP.

Este módulo **no importa el SDK de MCP a propósito**. Todo lo que se puede
equivocar al exponer la capa —qué herramientas se publican, cómo se resuelve el
token del header, qué mensaje de error ve el modelo, qué NO tiene que ver— vive
acá y se prueba con la suite normal. `mcp_server.py` queda como un caparazón
delgado que solo habla el protocolo.

No es una elección estética: el SDK no está instalado en la PC de desarrollo
(como `yfinance`), así que cualquier lógica que viviera junto a él sería lógica
sin tests hasta llegar a Railway, que es producción.
"""
import datetime as _dt
import decimal
import logging

from app.ai import registry, tokens
from app.ai.caller import AiCaller, ScopeDenegado

logger = logging.getLogger(__name__)

_BEARER = "bearer "

# Valor de MCP_PUBLIC_URL cuando nadie la define: sirve para correr el servidor
# a mano en la máquina propia. En un deploy hay que definirla siempre.
URL_PUBLICA_POR_DEFECTO = "http://127.0.0.1:8000"


def normalizar_url_publica(valor: str | None) -> str:
    """Completa el esquema si falta y saca la barra final.

    Railway entrega el dominio **pelado** al generarlo
    (`ia-production-2197.up.railway.app`), y es lo que uno copia y pega. Sin
    esquema, `AnyHttpUrl` lo rechaza y el contenedor no arranca: el traceback
    de pydantic dice "Input should be a valid URL" sin mencionar en ningún lado
    que lo que falta es el `https://`. Pasó en el primer deploy.

    Mismo criterio que `Config._normalize_db_url` con las cadenas `postgres://`
    que entrega Railway: aceptar lo que la plataforma da y normalizarlo acá, en
    vez de exigirle al operador que adivine el formato exacto.
    """
    v = (valor or "").strip().rstrip("/")
    if not v:
        return URL_PUBLICA_POR_DEFECTO
    if "://" not in v:
        return "https://" + v
    return v


def url_publica() -> str:
    """La URL pública del servicio, normalizada. Único lugar donde se lee
    `MCP_PUBLIC_URL`: si cada módulo la leyera por su cuenta, uno normalizaría
    y otro no, y el flujo de OAuth armaría redirecciones inconsistentes."""
    import os

    return normalizar_url_publica(os.environ.get("MCP_PUBLIC_URL"))


def hosts_permitidos(url: str) -> list[str]:
    """Los hosts que el servidor acepta, derivados de la URL pública.

    El SDK trae protección contra DNS rebinding y **solo acepta localhost por
    defecto**: sin esta lista, un deploy devuelve error a todo. Se incluyen el
    host con y sin puerto porque detrás de un proxy el header `Host` puede
    traerlo, y el comodín `host:*` para cualquier puerto.
    """
    sin_esquema = normalizar_url_publica(url).split("://", 1)[-1]
    host = sin_esquema.split("/", 1)[0]
    solo_host = host.split(":", 1)[0]
    return sorted({host, solo_host, f"{solo_host}:*"})


def tool_specs() -> list[dict]:
    """El registro en el formato que espera un cliente MCP.

    `inputSchema` en camelCase: es el nombre del campo en el protocolo, no una
    inconsistencia con el resto del código.
    """
    return [
        {"name": t.name,
         "description": t.description,
         "inputSchema": t.input_schema}
        for t in registry.all_tools()
    ]


def caller_desde_autorizacion(header: str | None) -> AiCaller | None:
    """Header `Authorization` → AiCaller, o None.

    Devuelve None ante cualquier problema (ausente, mal formado, token
    inexistente, revocado, usuario dado de baja) sin distinguir cuál: el que
    prueba no tiene por qué saber en qué caso cayó.
    """
    if not header or not isinstance(header, str):
        return None
    header = header.strip()
    if not header.lower().startswith(_BEARER):
        return None
    return tokens.resolver(header[len(_BEARER):].strip())


def _serializable(valor):
    """Convierte a tipos que se puedan pasar a JSON.

    Las herramientas ya devuelven fechas como texto, pero esto es la última
    barrera: un tipo nuevo que se cuele —un Decimal de una columna numérica, un
    date de una consulta que alguien agregue— reventaría la respuesta entera
    después de haber hecho todo el trabajo.
    """
    if isinstance(valor, dict):
        return {str(k): _serializable(v) for k, v in valor.items()}
    if isinstance(valor, (list, tuple, set)):
        return [_serializable(v) for v in valor]
    if isinstance(valor, (_dt.date, _dt.datetime)):
        return valor.isoformat()
    if isinstance(valor, decimal.Decimal):
        return float(valor)
    return valor


def ejecutar(nombre: str, caller: AiCaller | None,
             argumentos: dict | None = None) -> dict:
    """Despacha una herramienta y devuelve SIEMPRE un dict serializable.

    `{"ok": True, "resultado": …}` o `{"ok": False, "error": "…"}`. No propaga
    excepciones: del otro lado hay un protocolo, y una excepción cruda se
    convertiría en una desconexión en vez de en algo que el modelo pueda leer.

    Los mensajes de error están escritos para que el modelo se CORRIJA solo
    (qué herramientas hay, qué permiso falta, qué argumento sobra) en vez de
    reintentar lo mismo. La excepción es el error inesperado: ahí el detalle se
    va al log del servidor y afuera va un mensaje genérico, porque el texto de
    una excepción interna puede traer SQL, rutas o nombres de tablas.
    """
    if caller is None:
        return {"ok": False, "error":
                "No estás autenticado. Configurá tu token de la pantalla "
                "«Conexión IA» como Authorization: Bearer <token>."}

    try:
        resultado = registry.call(nombre, caller, argumentos or {})
    except registry.HerramientaDesconocida as exc:
        return {"ok": False, "error": str(exc)}
    except ScopeDenegado as exc:
        return {"ok": False, "error": str(exc)}
    except TypeError as exc:
        # Argumentos que no encajan con la firma: el esquema los declara, así
        # que devolver el detalle le permite al modelo arreglar la llamada.
        return {"ok": False, "error":
                f"argumentos inválidos para '{nombre}': {exc}"}
    except ValueError as exc:
        # Las herramientas usan ValueError para lo esperable (no existe / no la
        # ves / fecha sin datos) con mensajes redactados para el modelo.
        return {"ok": False, "error": str(exc)}
    except Exception:                                   # noqa: BLE001
        logger.exception("Error inesperado en la herramienta %s", nombre)
        return {"ok": False, "error":
                f"la herramienta '{nombre}' falló por un error interno; "
                f"quedó registrado en el servidor"}

    return {"ok": True, "resultado": _serializable(resultado)}
