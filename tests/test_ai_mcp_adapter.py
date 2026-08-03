"""El adaptador MCP: qué se publica, quién entra y qué sale ante un error.

Está separado del SDK a propósito (ver `app/ai/mcp_adapter`), así que todo lo
que puede salir mal al exponer la capa se prueba acá y no en Railway.
"""
import datetime
from pathlib import Path

import pytest
import sqlalchemy as sa

from app.ai import mcp_adapter, registry, tokens
from app.ai.caller import SCOPE_READ, AiCaller
from app.database import Base, Session, engine, get_session


@pytest.fixture()
def db():
    import app.models  # noqa: F401

    Session.remove()
    Base.metadata.create_all(engine)
    with engine.begin() as conn:
        conn.execute(sa.text("DELETE FROM users"))
        conn.execute(sa.text("DELETE FROM strategy"))
    yield
    with engine.begin() as conn:
        conn.execute(sa.text("DELETE FROM users"))
        conn.execute(sa.text("DELETE FROM strategy"))
    Session.remove()


def _usuario(username="ana", role="analyst") -> int:
    from app.models import User

    s = get_session()
    u = User(username=username, role=role, active=True)
    u.set_password("x")
    s.add(u)
    s.commit()
    return u.id


# ── Qué se publica ────────────────────────────────────────────────────────────

def test_publica_todas_las_del_registro():
    assert len(mcp_adapter.tool_specs()) == len(registry.all_tools())


def test_cada_spec_trae_lo_que_el_protocolo_pide():
    for spec in mcp_adapter.tool_specs():
        assert set(spec) == {"name", "description", "inputSchema"}
        assert spec["inputSchema"]["type"] == "object"
        assert spec["description"]


def test_el_esquema_es_el_mismo_objeto_que_declara_la_herramienta():
    """Que no haya una segunda copia del esquema que se pueda desincronizar."""
    por_nombre = {t.name: t for t in registry.all_tools()}
    for spec in mcp_adapter.tool_specs():
        assert spec["inputSchema"] is por_nombre[spec["name"]].input_schema


# ── La URL pública ────────────────────────────────────────────────────────────

@pytest.mark.parametrize("crudo,esperado", [
    # EL CASO QUE TIRÓ ABAJO EL PRIMER DEPLOY: Railway entrega el dominio
    # pelado al generarlo, y es lo que uno copia y pega. Sin esquema,
    # AnyHttpUrl lo rechaza y el contenedor no arranca — con un traceback de
    # pydantic que no menciona en ningún lado que falta el "https://".
    ("ia-production-2197.up.railway.app", "https://ia-production-2197.up.railway.app"),
    ("https://mcp.example.com", "https://mcp.example.com"),
    ("https://mcp.example.com/", "https://mcp.example.com"),
    ("  https://mcp.example.com  ", "https://mcp.example.com"),
    ("http://127.0.0.1:8000", "http://127.0.0.1:8000"),
    ("127.0.0.1:8000", "https://127.0.0.1:8000"),
])
def test_la_url_publica_se_normaliza(crudo, esperado):
    assert mcp_adapter.normalizar_url_publica(crudo) == esperado


@pytest.mark.parametrize("vacio", [None, "", "   "])
def test_sin_url_publica_se_asume_local(vacio):
    assert (mcp_adapter.normalizar_url_publica(vacio)
            == mcp_adapter.URL_PUBLICA_POR_DEFECTO)


# ── La dirección que se le muestra al usuario ────────────────────────────────
# Era el dato que no estaba en ningún lado y se transmitía de boca en boca: se
# probó con la de la aplicación web, con la de descubrimiento del protocolo y
# con el dominio pelado antes de dar con la buena. Ningún cliente avisa que el
# problema sea la dirección.

@pytest.mark.parametrize("crudo,esperado", [
    ("ia-production-2197.up.railway.app",
     "https://ia-production-2197.up.railway.app/mcp"),
    ("https://mcp.example.com", "https://mcp.example.com/mcp"),
    ("https://mcp.example.com/", "https://mcp.example.com/mcp"),
])
def test_la_direccion_del_conector_es_la_publica_mas_la_ruta(monkeypatch, crudo,
                                                             esperado):
    monkeypatch.setenv("MCP_PUBLIC_URL", crudo)

    assert mcp_adapter.url_del_conector() == esperado


@pytest.mark.parametrize("vacio", ["", "   "])
def test_sin_declarar_no_se_inventa_una_direccion(monkeypatch, vacio):
    """None y no el default de desarrollo: la pantalla la ofrece para copiar, y
    un `127.0.0.1` con la misma cara que el valor bueno es peor que nada — quien
    lo pega no tiene cómo saber que está mal."""
    monkeypatch.setenv("MCP_PUBLIC_URL", vacio)

    assert mcp_adapter.url_del_conector() is None


def test_sin_la_variable_tampoco(monkeypatch):
    monkeypatch.delenv("MCP_PUBLIC_URL", raising=False)

    assert mcp_adapter.url_del_conector() is None


def test_la_direccion_que_se_muestra_es_la_que_el_servidor_atiende():
    """La pantalla y el servidor tienen que decir lo mismo. Si se escribieran a
    mano en cada lado, la pantalla podría enseñar una dirección que no existe y
    nadie se enteraría hasta que alguien no pudiera conectarse."""
    fuente = (Path(__file__).resolve().parents[1] / "mcp_server.py").read_text(
        encoding="utf-8")

    assert "mcp_adapter.RUTA_MCP" in fuente
    assert '+ "/mcp"' not in fuente


def test_la_url_normalizada_es_valida_para_el_validador_del_sdk():
    """El contrato real: lo que salga de acá tiene que poder construir el
    AnyHttpUrl que mcp_server le pasa al SDK. Sin esto el test de arriba
    verificaría un formato que igual podría ser rechazado."""
    from pydantic import AnyHttpUrl

    for crudo in ("ia-production-2197.up.railway.app", "https://mcp.example.com",
                  "mcp.example.com/", None):
        AnyHttpUrl(mcp_adapter.normalizar_url_publica(crudo))


@pytest.mark.parametrize("url,esperado", [
    ("https://mcp.example.com", ["mcp.example.com", "mcp.example.com:*"]),
    ("mcp.example.com", ["mcp.example.com", "mcp.example.com:*"]),
    ("http://127.0.0.1:8000",
     ["127.0.0.1", "127.0.0.1:*", "127.0.0.1:8000"]),
])
def test_los_hosts_aceptados_incluyen_con_y_sin_puerto(url, esperado):
    """Detrás de un proxy el header `Host` puede traer el puerto; si no está en
    la lista, el SDK rechaza el pedido por protección de DNS rebinding."""
    assert mcp_adapter.hosts_permitidos(url) == esperado


# ── Autenticación ─────────────────────────────────────────────────────────────

def test_un_bearer_valido_resuelve_al_usuario(db):
    uid = _usuario()
    token = tokens.generar(uid)
    caller = mcp_adapter.caller_desde_autorizacion(f"Bearer {token}")

    assert caller is not None and caller.user_id == uid


def test_el_esquema_bearer_no_distingue_mayusculas(db):
    """Los clientes escriben "Bearer", "bearer" y "BEARER" indistintamente."""
    token = tokens.generar(_usuario())
    for prefijo in ("Bearer", "bearer", "BEARER"):
        assert mcp_adapter.caller_desde_autorizacion(f"{prefijo} {token}") is not None


@pytest.mark.parametrize("header", [
    None, "", "   ", "Bearer", "Bearer ", "sma_suelto_sin_esquema",
    "Basic dXNlcjpwYXNz", "Bearer sma_inventado", 12345,
])
def test_lo_que_no_resuelve_devuelve_none(db, header):
    _usuario()
    assert mcp_adapter.caller_desde_autorizacion(header) is None


def test_un_token_revocado_deja_de_entrar(db):
    uid = _usuario()
    header = f"Bearer {tokens.generar(uid)}"
    assert mcp_adapter.caller_desde_autorizacion(header) is not None

    tokens.revocar(uid)
    Session.remove()
    assert mcp_adapter.caller_desde_autorizacion(header) is None


# ── Ejecutar: nunca propaga, siempre serializa ────────────────────────────────

def test_sin_caller_no_ejecuta_nada(db):
    out = mcp_adapter.ejecutar("list_strategies", None)
    assert out["ok"] is False
    assert "Conexión IA" in out["error"]


def test_una_llamada_valida_devuelve_el_resultado(db):
    out = mcp_adapter.ejecutar("list_strategies", AiCaller(user_id=1))
    assert out["ok"] is True
    assert out["resultado"]["strategies"] == []


def test_una_herramienta_desconocida_lista_las_disponibles(db):
    out = mcp_adapter.ejecutar("borrar_todo", AiCaller(user_id=1))
    assert out["ok"] is False
    assert "list_strategies" in out["error"]


def test_sin_scope_lo_dice(db):
    sin_nada = AiCaller(user_id=1, scopes=frozenset())
    out = mcp_adapter.ejecutar("list_strategies", sin_nada)
    assert out["ok"] is False and "read" in out["error"]


def test_un_argumento_que_no_existe_no_revienta(db):
    out = mcp_adapter.ejecutar("list_strategies", AiCaller(user_id=1),
                               {"inventado": 1})
    assert out["ok"] is False
    assert "argumentos inválidos" in out["error"]


def test_un_error_esperable_llega_con_su_mensaje(db):
    """Los ValueError de las herramientas están redactados para el modelo."""
    out = mcp_adapter.ejecutar("strategy_ranking", AiCaller(user_id=1),
                               {"strategy_id": 999_999})
    assert out["ok"] is False
    assert "list_strategies" in out["error"]      # le dice cómo corregirse


def test_un_error_inesperado_no_filtra_el_detalle(db, monkeypatch):
    """Una excepción interna puede traer SQL, rutas o nombres de tablas. Al
    modelo (y por lo tanto al usuario) va un mensaje genérico; el detalle al
    log del servidor."""
    def explota(*a, **k):
        raise RuntimeError("SELECT secreto FROM users WHERE ... /ruta/interna")

    monkeypatch.setattr(registry, "call", explota)
    out = mcp_adapter.ejecutar("list_strategies", AiCaller(user_id=1))

    assert out["ok"] is False
    assert "secreto" not in out["error"]
    assert "/ruta/interna" not in out["error"]
    assert "error interno" in out["error"]


def test_nunca_propaga_una_excepcion(db, monkeypatch):
    """Del otro lado hay un protocolo: una excepción cruda sería una
    desconexión en vez de algo que el modelo pueda leer."""
    for exc in (RuntimeError("x"), KeyError("y"), OSError("z")):
        monkeypatch.setattr(registry, "call",
                            lambda *a, _e=exc, **k: (_ for _ in ()).throw(_e))
        assert mcp_adapter.ejecutar("list_strategies",
                                    AiCaller(user_id=1))["ok"] is False


# ── Serialización ─────────────────────────────────────────────────────────────

@pytest.mark.parametrize("crudo,esperado", [
    (datetime.date(2026, 8, 1), "2026-08-01"),
    (datetime.datetime(2026, 8, 1, 12, 30), "2026-08-01T12:30:00"),
])
def test_las_fechas_salen_en_iso(crudo, esperado):
    assert mcp_adapter._serializable(crudo) == esperado


def test_serializa_en_profundidad():
    import decimal

    crudo = {"a": [{"f": datetime.date(2026, 8, 1)}],
             "b": {"c": decimal.Decimal("1.5")}}
    assert mcp_adapter._serializable(crudo) == {
        "a": [{"f": "2026-08-01"}], "b": {"c": 1.5}}


def test_el_resultado_de_una_herramienta_es_json(db):
    """Prueba de integración de la serialización: lo que sale de una
    herramienta real tiene que poder viajar por el protocolo."""
    import json

    out = mcp_adapter.ejecutar("get_catalog", AiCaller(user_id=1))
    assert out["ok"] is True
    json.dumps(out)          # revienta si quedó un tipo no serializable


# ── El circuito completo ──────────────────────────────────────────────────────

def test_de_header_a_resultado_sin_flask(db):
    """Exactamente lo que va a hacer mcp_server.py en cada llamada."""
    uid = _usuario("ana", role="analyst")
    header = f"Bearer {tokens.generar(uid)}"

    caller = mcp_adapter.caller_desde_autorizacion(header)
    out = mcp_adapter.ejecutar("list_strategies", caller)

    assert caller.user_id == uid
    assert caller.scopes == frozenset({SCOPE_READ})
    assert out["ok"] is True
