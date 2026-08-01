"""Trinquetes de la capa de capacidades para IA (app/ai).

Estos tests NO prueban que las herramientas devuelvan datos lindos: prueban las
tres invariantes que hacen que la capa sea segura, y están escritos para que
una herramienta NUEVA los rompa si se olvida de cumplirlas.

1. **Toda herramienta recibe un caller y ninguna puede no recibirlo.** El gate
   de visibilidad de esta aplicación vive en las pantallas, no en los servicios
   (`data_explorer_service.fetch()` no filtra nada), y `current_viewer()`
   depende de flask_login, que no existe fuera de un request. Una herramienta
   que no propague el viewer devuelve datos de otro usuario.
2. **La allowlist es el registro.** Lo que no está registrado no se puede
   invocar, y lo destructivo no puede ni mencionarse en `app/ai/`.
3. **Los topes de filas son chicos.** Los de la UI (5000) son para una grilla.
"""
import ast
import inspect
import pathlib

import pytest

from app.ai import registry
from app.ai.caller import (SCOPE_READ, SCOPE_RUN_JOBS, SCOPE_WRITE_PACKS,
                           AiCaller, ScopeDenegado)

_AI_DIR = pathlib.Path(registry.__file__).resolve().parent


def _fuentes_de_herramientas():
    return sorted((_AI_DIR / "tools").glob("*.py"))


# ── 1. El caller es obligatorio ───────────────────────────────────────────────

def test_hay_herramientas_registradas():
    """Si el registro queda vacío, todo lo demás pasa por vacuidad."""
    assert registry.all_tools(), "no se registró ninguna herramienta"


@pytest.mark.parametrize("t", registry.all_tools(), ids=lambda t: t.name)
def test_toda_herramienta_recibe_el_caller_como_primer_argumento(t):
    params = list(inspect.signature(t.handler).parameters)
    assert params and params[0] == "caller", (
        f"{t.name}: el primer parámetro tiene que ser `caller`. Es lo que "
        f"transporta la identidad del usuario; sin él la herramienta no puede "
        f"filtrar por visibilidad y devuelve datos de cualquiera.")


@pytest.mark.parametrize("t", registry.all_tools(), ids=lambda t: t.name)
def test_ninguna_herramienta_usa_current_viewer(t):
    """`current_viewer()` lee flask_login: fuera de un request devolvería
    anónimo (o reventaría), y el bug sería silencioso — se vería como "no hay
    datos" en vez de como un error."""
    fuente = inspect.getsource(t.handler)
    assert "current_viewer" not in fuente, (
        f"{t.name} usa current_viewer(); tiene que usar caller.viewer()")


def test_call_exige_caller_sin_default():
    """Que una invocación sin identidad no compile es más barato que
    descubrirla en producción."""
    p = inspect.signature(registry.call).parameters["caller"]
    assert p.default is inspect.Parameter.empty


# ── 2. La allowlist ───────────────────────────────────────────────────────────

# Nada de esto puede aparecer en app/ai/: son operaciones destructivas o
# escrituras que la IA no tiene por qué poder invocar. El chequeo es sobre el
# TEXTO del paquete, así que también atrapa a quien las importe "solo para leer
# algo de paso".
_PROHIBIDO = (
    # Destructivo
    "reset_to_fresh_install", "clean_data", "truncate_all_tables",
    "purge_assets", "wipe_table", "drop_all_percode_tables",
    "drop_sig_table", "drop_strat_table", "drop_signal_storage",
    "drop_strategy_storage",
    # Escritura de definiciones — las señales son SOLO por pantalla de admin,
    # ninguna IA las escribe (ver signal_service.ADMIN_ONLY_MOTIVO)
    "save_signal", "delete_signal", "import_signal_rows",
    "import_signals_file", "import_signals_excel", "import_pack",
    "save_strategy", "delete_strategy",
    # Corridas pesadas: van por el job asíncrono con run_lock, no por una
    # llamada directa que cuelgue la herramienta media hora
    "rebuild_signal_history", "update_signal_history", "run_recalculate",
    "compute_all_strategies",
    # SQL libre
    "text(", "execute(",
)


@pytest.mark.parametrize("path", _fuentes_de_herramientas(),
                         ids=lambda p: p.name)
def test_las_herramientas_no_mencionan_nada_prohibido(path):
    fuente = path.read_text(encoding="utf-8")
    # Se ignoran comentarios y docstrings: nombrar algo para explicar por qué
    # NO se usa es justamente lo que queremos que la gente escriba.
    arbol = ast.parse(fuente, filename=str(path))
    for nodo in ast.walk(arbol):
        if isinstance(nodo, ast.Constant) and isinstance(nodo.value, str):
            nodo.value = ""
    codigo = ast.unparse(arbol)
    encontrados = [p for p in _PROHIBIDO if p in codigo]
    assert not encontrados, (
        f"{path.name} menciona {encontrados}. La capa de IA es de LECTURA: "
        f"lo destructivo y la escritura de definiciones no se exponen. Si hace "
        f"falta una escritura, va por packs con confirmación humana (fase 2).")


def test_una_herramienta_desconocida_no_se_puede_invocar():
    with pytest.raises(registry.HerramientaDesconocida):
        registry.call("borrar_todo", AiCaller(user_id=1, is_admin=True))


def test_el_error_de_desconocida_lista_las_disponibles():
    """Para que el modelo se corrija solo en vez de insistir."""
    with pytest.raises(registry.HerramientaDesconocida, match="list_strategies"):
        registry.get("inventada")


# ── 3. Scopes ─────────────────────────────────────────────────────────────────

def test_sin_el_scope_la_llamada_se_rechaza():
    sin_lectura = AiCaller(user_id=1, is_admin=True, scopes=frozenset())
    with pytest.raises(ScopeDenegado, match="read"):
        registry.call("list_strategies", sin_lectura)


def test_el_scope_no_reemplaza_al_rol():
    """Un token de admin con todos los scopes sigue sin poder escribir señales:
    no existe la herramienta. El scope acota lo que se puede INTENTAR; el rol
    decide qué devuelve lo que sí existe."""
    AiCaller(user_id=1, is_admin=True,
             scopes=frozenset({SCOPE_READ, SCOPE_WRITE_PACKS, SCOPE_RUN_JOBS}))
    nombres = {t.name for t in registry.all_tools()}
    assert not (nombres & {"save_signal", "import_pack", "save_strategy"})


def test_un_scope_desconocido_no_se_puede_construir():
    with pytest.raises(ValueError, match="scopes desconocidos"):
        AiCaller(user_id=1, scopes=frozenset({"admin:todo"}))


@pytest.mark.parametrize("t", registry.all_tools(), ids=lambda t: t.name)
def test_en_la_fase_1_todo_es_de_lectura(t):
    assert t.scope == SCOPE_READ, (
        f"{t.name} declara scope '{t.scope}'. La fase 1 es solo lectura; la "
        f"escritura entra por packs con ensayo y confirmación humana.")


# ── 4. Topes de filas ─────────────────────────────────────────────────────────

@pytest.mark.parametrize("t", registry.all_tools(), ids=lambda t: t.name)
def test_los_topes_no_superan_el_tope_global(t):
    if t.max_rows is not None:
        assert t.max_rows <= registry.MAX_ROWS_TOPE


def test_el_tope_global_es_mucho_menor_que_el_de_la_ui():
    """Los 5000 de data_explorer son para una grilla; en el contexto de un
    modelo son cientos de miles de tokens."""
    from app.services.data_explorer_service import MAX_ROWS as UI_MAX

    assert registry.MAX_ROWS_TOPE * 10 < UI_MAX


@pytest.mark.parametrize("pedido,esperado", [
    (None, 50), (10, 10), (999, 50), (0, 1), (-5, 1), ("7", 7),
])
def test_el_limite_se_acota_en_silencio(pedido, esperado):
    """Acotar y no fallar: el modelo pide 1000 sin malicia y un error ahí solo
    gasta un turno."""
    assert registry.limite(pedido, 50) == esperado


@pytest.mark.parametrize("t", registry.all_tools(), ids=lambda t: t.name)
def test_toda_herramienta_que_devuelve_filas_declara_su_tope(t):
    """Heurística: si el esquema acepta `limit`, tiene que declarar max_rows."""
    props = t.input_schema.get("properties", {})
    if "limit" in props:
        assert t.max_rows is not None, (
            f"{t.name} acepta `limit` pero no declara max_rows")


# ── 5. Contrato de las descripciones ──────────────────────────────────────────

@pytest.mark.parametrize("t", registry.all_tools(), ids=lambda t: t.name)
def test_la_descripcion_le_sirve_al_modelo(t):
    """La descripción es lo único que el modelo lee para decidir si llamar.
    Una línea genérica hace que la herramienta no se use o se use mal."""
    assert len(t.description) >= 60, f"{t.name}: descripción demasiado corta"
    assert t.description[0].isupper()


@pytest.mark.parametrize("t", registry.all_tools(), ids=lambda t: t.name)
def test_el_esquema_es_un_objeto_cerrado(t):
    """`additionalProperties: false` hace que un argumento inventado falle acá
    y no adentro del servicio con un TypeError críptico."""
    assert t.input_schema.get("type") == "object"
    assert t.input_schema.get("additionalProperties") is False


@pytest.mark.parametrize("t", registry.all_tools(), ids=lambda t: t.name)
def test_los_argumentos_del_esquema_existen_en_el_handler(t):
    """Que el esquema publicado y la firma no se desincronicen: un argumento
    documentado que el handler no acepta revienta recién al invocarlo."""
    firma = set(inspect.signature(t.handler).parameters) - {"caller"}
    declarados = set(t.input_schema.get("properties", {}))
    assert declarados <= firma, (
        f"{t.name}: el esquema declara {sorted(declarados - firma)}, que el "
        f"handler no acepta")
    requeridos = set(t.input_schema.get("required", []))
    sin_default = {
        n for n, p in inspect.signature(t.handler).parameters.items()
        if n != "caller" and p.default is inspect.Parameter.empty
    }
    assert sin_default <= requeridos, (
        f"{t.name}: {sorted(sin_default - requeridos)} son obligatorios en el "
        f"handler pero el esquema no los marca como `required`")


def test_el_orden_de_las_herramientas_es_estable():
    """El cliente cachea la lista de herramientas: si se reordena sola, le
    invalida el caché de prompt en cada llamada."""
    assert [t.name for t in registry.all_tools()] == \
           [t.name for t in registry.all_tools()]
    assert [t.name for t in registry.all_tools()] == \
           sorted(t.name for t in registry.all_tools())
