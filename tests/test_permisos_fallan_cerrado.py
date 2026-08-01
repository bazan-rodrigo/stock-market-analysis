"""Trinquete: ningún parámetro de permiso puede tener default permisivo.

De dónde sale. Al cerrar la escritura de señales (1-ago-2026) apareció que
`save_signal` tenía `acting_is_admin: bool = True` "por comodidad para scripts
y tests". Con ese default, un caller que se olvide del flag **escribe como
administrador por omisión** — y el olvido no se nota, porque el camino feliz
funciona. Lo mismo del lado de lectura: `get_all_signals_flat` devolvía TODAS
las señales, incluidas las privadas de otros, si nadie pasaba el viewer.

Por qué un trinquete y no arreglarlos y listo. Los tres sitios que había se
arreglaron a mano; lo que este archivo impide es el CUARTO, el que todavía no
existe. Es especialmente relevante para la capa de IA/MCP en diseño: sus
herramientas van a llamar a estos servicios desde fuera de un request Flask,
donde no hay `current_user` del que deducir el rol. Ahí, un default permisivo
no es una comodidad: es el agujero.

Se analiza con `ast` en vez de importar los módulos: no depende de que
importar un servicio sea libre de efectos, y ve también el código que ninguna
prueba ejecuta.
"""
import ast
import pathlib

import pytest

_SERVICES = pathlib.Path(__file__).resolve().parent.parent / "app" / "services"

# Nombres que denotan una decisión de permiso o de alcance de visibilidad.
# `user_id` NO entra: su default None significa "anónimo", que ya es lo cerrado.
_PERMISO = {"is_admin", "acting_is_admin"}

# El valor seguro de cada uno. Si algún día hace falta otro parámetro de
# permiso que no sea booleano, este mapa es el lugar donde se declara.
_CERRADO = False


def _defaults_de(fn: ast.FunctionDef) -> dict[str, ast.expr]:
    """{nombre: nodo del default} para posicionales y keyword-only."""
    out: dict[str, ast.expr] = {}
    args = fn.args
    posicionales = args.posonlyargs + args.args
    # Los defaults aplican a los ÚLTIMOS N posicionales
    for arg, default in zip(posicionales[len(posicionales) - len(args.defaults):],
                            args.defaults):
        out[arg.arg] = default
    for arg, default in zip(args.kwonlyargs, args.kw_defaults):
        if default is not None:
            out[arg.arg] = default
    return out


def _funciones_con_permiso():
    """[(archivo, función, parámetro, nodo del default)] de todo app/services."""
    encontrados = []
    for path in sorted(_SERVICES.glob("*.py")):
        arbol = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for nodo in ast.walk(arbol):
            if not isinstance(nodo, (ast.FunctionDef, ast.AsyncFunctionDef)):
                continue
            for nombre, default in _defaults_de(nodo).items():
                if nombre in _PERMISO:
                    encontrados.append((path.name, nodo.name, nombre, default))
    return encontrados


def test_hay_parametros_de_permiso_para_revisar():
    """Si esto falla, o se renombraron los parámetros o el scanner se rompió —
    y en cualquiera de los dos casos el trinquete dejó de proteger nada."""
    assert _funciones_con_permiso(), (
        "el scanner no encontró ningún parámetro de permiso en app/services: "
        "revisá _PERMISO antes de creer que está todo bien")


@pytest.mark.parametrize(
    "archivo,funcion,parametro,default",
    _funciones_con_permiso(),
    ids=lambda v: v if isinstance(v, str) else "",
)
def test_el_default_de_un_permiso_es_cerrado(archivo, funcion, parametro, default):
    assert isinstance(default, ast.Constant) and default.value is _CERRADO, (
        f"{archivo}::{funcion} tiene `{parametro}` con default "
        f"{ast.unparse(default)}. Un parámetro de permiso tiene que fallar "
        f"CERRADO (False): quien necesite privilegio lo pide explícito. "
        f"Con el default permisivo, un caller que se olvide del flag obtiene "
        f"acceso de administrador sin que nada lo señale."
    )


def test_los_tres_sitios_que_motivaron_el_trinquete_siguen_cerrados():
    """Nombrados a propósito: si alguno vuelve a True, el mensaje de arriba
    dice cuál, pero este test dice POR QUÉ importaba cada uno."""
    import inspect

    from app.services import (signal_history_service, signal_service,
                              strategy_service)

    # Escritura de señales: exclusiva de admin en los cuatro caminos.
    for fn in (signal_service.save_signal, signal_service.delete_signal):
        assert inspect.signature(fn).parameters["acting_is_admin"].default is False

    # Escritura de estrategias: dueño o admin. Cerrado = solo lo propio.
    for fn in (strategy_service.save_strategy, strategy_service.delete_strategy):
        assert inspect.signature(fn).parameters["acting_is_admin"].default is False

    # LECTURA con visibilidad: cerrado = solo públicas, no las privadas ajenas.
    assert inspect.signature(
        signal_history_service.get_all_signals_flat).parameters["is_admin"].default is False
