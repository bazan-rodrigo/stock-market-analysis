"""Tokens de conexión de IA: generar, revocar y resolver.

Un token identifica a un USUARIO ante el servidor MCP. No tiene nada que ver
con la cuenta del proveedor de IA (Claude, ChatGPT, …): esa se queda en el
cliente del usuario y esta aplicación nunca la ve — es toda la ventaja de haber
elegido MCP en vez de un panel propio.

Hace falta porque el servidor MCP corre fuera de Flask: no hay `current_user`,
y sin saber quién pregunta no se puede aplicar el gate de visibilidad. Sin
token, la única alternativa sería un servidor público donde cualquiera lee las
definiciones privadas de todos.

Se guarda el HASH, nunca el token. Como con la contraseña: si alguien lee la
base, no obtiene credenciales utilizables.
"""
import hashlib
import secrets
from datetime import datetime

from app.ai.caller import SCOPE_READ, AiCaller

# Prefijo reconocible: si el token termina en un log, en un archivo de
# configuración subido a un repo o pegado en un chat, se ve de qué es y se
# puede revocar. Los escáneres de secretos también trabajan por prefijo.
PREFIJO = "sma_"

# 32 bytes = 256 bits de entropía. Adivinarlo no es un escenario.
_BYTES = 32


def _hash(token: str) -> str:
    """SHA-256 hex del token.

    No es bcrypt a propósito, y la diferencia con `User.password_hash` es
    deliberada: una contraseña es corta y adivinable, así que conviene que
    verificarla sea lenta. Un token de 256 bits aleatorios no se adivina, y
    bcrypt tendría dos costos acá — latencia en CADA llamada MCP, y sobre todo
    que al saltear cada hash haría imposible BUSCAR por hash: habría que traer
    todos los usuarios y comparar uno por uno. Con SHA-256 la resolución es un
    índice único.
    """
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def generar(user_id: int) -> str:
    """Genera un token nuevo para el usuario y devuelve el texto EN CLARO.

    Es la única vez que el texto existe: después solo queda el hash. Generar de
    nuevo **invalida el anterior** (hay un token por usuario), lo cual es
    también la forma de rotarlo si se filtró.
    """
    from app.database import get_session
    from app.models import User

    s = get_session()
    user = s.query(User).filter(User.id == int(user_id)).first()
    if user is None:
        raise ValueError(f"No existe el usuario id={user_id}.")

    token = PREFIJO + secrets.token_urlsafe(_BYTES)
    user.mcp_token_hash = _hash(token)
    user.mcp_token_created_at = datetime.utcnow()
    try:
        s.commit()
    except Exception:
        s.rollback()
        raise
    return token


def revocar(user_id: int) -> bool:
    """Deja al usuario sin token. True si había uno."""
    from app.database import get_session
    from app.models import User

    s = get_session()
    user = s.query(User).filter(User.id == int(user_id)).first()
    if user is None:
        raise ValueError(f"No existe el usuario id={user_id}.")
    tenia = user.mcp_token_hash is not None
    user.mcp_token_hash = None
    user.mcp_token_created_at = None
    try:
        s.commit()
    except Exception:
        s.rollback()
        raise
    return tenia


def estado(user_id: int) -> dict:
    """{'tiene': bool, 'creado': datetime|None} para mostrarlo en la pantalla.
    Nunca devuelve el hash: no le sirve a nadie y no tiene por qué viajar."""
    from app.database import get_session
    from app.models import User

    s = get_session()
    user = s.query(User).filter(User.id == int(user_id)).first()
    if user is None:
        raise ValueError(f"No existe el usuario id={user_id}.")
    return {"tiene": user.mcp_token_hash is not None,
            "creado": user.mcp_token_created_at}


def resolver(token: str | None) -> AiCaller | None:
    """Token → AiCaller, o None si no resuelve.

    Es la puerta de entrada del servidor MCP. Devuelve None (y no una excepción
    con detalle) ante cualquier problema — token vacío, inexistente, revocado o
    de un usuario dado de baja — para no darle al que prueba ninguna pista de
    en cuál de esos casos cayó.

    El rol sale del usuario, no del token: la capa de IA no puede ver más que
    la pantalla equivalente. Un usuario desactivado no resuelve, igual que no
    podría entrar por la web.
    """
    from app.database import get_session
    from app.models import User

    if not token or not isinstance(token, str):
        return None
    token = token.strip()
    if not token:
        return None

    s = get_session()
    user = s.query(User).filter(User.mcp_token_hash == _hash(token)).first()
    if user is None or not user.active:
        return None

    # En la fase 1 todo es lectura. Cuando entren la escritura por packs y los
    # jobs, el scope va a salir de acá (probablemente del rol, para no inventar
    # un permiso que la pantalla no tiene).
    return AiCaller(user_id=user.id, is_admin=user.is_admin,
                    scopes=frozenset({SCOPE_READ}))
