"""Registro de herramientas: la ÚNICA superficie que la IA puede tocar.

Una herramienta es un adaptador delgado sobre `app/services/*`. No lleva lógica
de negocio: la inteligencia cuantitativa se queda en la aplicación. Lo que sí
lleva, y es su razón de existir, son las tres cosas que los servicios no hacen
solos:

1. **Re-aplicar el gate de visibilidad** (ver `caller.AiCaller`).
2. **Acotar el tamaño de la respuesta.** Los topes de la UI están pensados para
   una grilla (`data_explorer_service.MAX_ROWS = 5000`) y son absurdos para el
   contexto de un modelo. Acá el tope es chico y lo declara cada herramienta.
3. **Ser una allowlist.** Lo que no está registrado no existe para la IA. No
   hay "llamar a cualquier servicio": hay este archivo.

El transporte (MCP) va aparte y encima: convierte `all_tools()` en su formato y
`call()` en su despacho. Este módulo no sabe nada de red, y por eso se puede
probar entero con la suite normal.
"""
from dataclasses import dataclass
from typing import Any, Callable

from app.ai.caller import SCOPE_READ, AiCaller

# Tope duro de filas para CUALQUIER herramienta. Una respuesta de 200 filas ya
# son decenas de miles de tokens; el modelo tiene que pedir agregados o acotar
# el filtro, no traerse la tabla. Un tope global además evita que una
# herramienta nueva se olvide de poner el suyo.
MAX_ROWS_TOPE = 200


class HerramientaDesconocida(KeyError):
    """Nombre que no está en el registro. La allowlist es el registro."""


# Familias de capacidad: el vocabulario con el que el MANUAL le cuenta al
# usuario qué puede hacer la IA con su token (docs/manual/790-conexion-ia.md,
# clave `familias_ia` de su front-matter). Cada herramienta declara la suya y
# `tests/test_contract_coverage.py` exige que las dos listas coincidan.
#
# Por qué existe: el manual no puede enumerar herramientas por su nombre
# técnico —lo lee alguien que no programa—, así que sin este puente la única
# garantía de que esté al día es que la persona se acuerde. Y no se acordó: la
# sección estuvo describiendo 8 de 15 herramientas durante días, sin mencionar
# que la IA corre backtests y simula carteras.
#
# Estrenar una familia rompe la suite hasta que el manual la describa. Es
# deliberado: una capacidad nueva que el usuario no sabe que tiene es una
# capacidad que no existe.
FAMILIAS = frozenset({
    "catalogo",     # qué existe: indicadores, señales, estrategias
    "indicadores",  # cómo se reparten los datos entre activos
    "ranking",      # resultados ya calculados de una estrategia
    "backtest",     # medir una estrategia contra la historia, sin persistir
    "carteras",     # ver carteras y simular hipotéticas, sin crearlas
    "manual",       # el manual de esta instalación
    "packs",        # el formato publicado + ensayar un pack, sin importarlo
})


@dataclass(frozen=True)
class Tool:
    name: str
    description: str
    input_schema: dict          # JSON Schema del objeto de argumentos
    handler: Callable
    familia: str = ""           # una de FAMILIAS — obligatoria, ver `tool()`
    scope: str = SCOPE_READ
    max_rows: int | None = None   # None = no devuelve listas de filas

    def __post_init__(self):
        if self.max_rows is not None and self.max_rows > MAX_ROWS_TOPE:
            raise ValueError(
                f"{self.name}: max_rows={self.max_rows} supera el tope global "
                f"de {MAX_ROWS_TOPE}")
        if self.familia not in FAMILIAS:
            raise ValueError(
                f"{self.name}: familia={self.familia!r} no está en FAMILIAS "
                f"({', '.join(sorted(FAMILIAS))}). Toda herramienta declara a "
                f"qué capacidad pertenece, porque es como el manual se la "
                f"cuenta al usuario. Si de verdad es una capacidad nueva, "
                f"sumala a FAMILIAS y describila en la sección Conexión IA.")


_REGISTRO: dict[str, Tool] = {}


def tool(*, name: str, description: str, input_schema: dict, familia: str,
         scope: str = SCOPE_READ, max_rows: int | None = None):
    """Decorador de registro. El handler recibe `(caller, **argumentos)`.

    `familia` es obligatoria y sin default: elegirla es lo que ata la
    herramienta nueva a su párrafo del manual (ver FAMILIAS).
    """

    def deco(fn: Callable) -> Callable:
        if name in _REGISTRO:
            raise ValueError(f"herramienta duplicada: {name}")
        _REGISTRO[name] = Tool(name=name, description=description,
                               input_schema=input_schema, handler=fn,
                               familia=familia, scope=scope, max_rows=max_rows)
        return fn

    return deco


def all_tools() -> list[Tool]:
    """Todas las registradas, en orden estable (el orden afecta el caché de
    prompt de los clientes: una lista que se reordena sola lo invalida)."""
    _cargar()
    return [_REGISTRO[k] for k in sorted(_REGISTRO)]


def get(name: str) -> Tool:
    _cargar()
    try:
        return _REGISTRO[name]
    except KeyError:
        raise HerramientaDesconocida(
            f"no existe la herramienta '{name}'. Disponibles: "
            f"{', '.join(sorted(_REGISTRO))}") from None


def call(name: str, caller: AiCaller, arguments: dict | None = None) -> Any:
    """Único punto de invocación: resuelve, exige el scope y despacha.

    El `caller` es obligatorio y no tiene default a propósito — que una llamada
    sin identidad no compile es más barato que descubrirla en producción.
    """
    herramienta = get(name)
    caller.exigir(herramienta.scope)
    return herramienta.handler(caller, **(arguments or {}))


def limite(pedido: int | None, tope: int) -> int:
    """Cuántas filas devolver: lo pedido, acotado al tope de la herramienta.
    Se acota EN SILENCIO en vez de fallar — el modelo pide 1000 sin malicia, y
    un error ahí solo gasta un turno."""
    if pedido is None:
        return tope
    return max(1, min(int(pedido), tope))


def _cargar() -> None:
    """Importa los módulos de herramientas la primera vez (el decorador corre
    al importar). Explícito y no por descubrimiento de archivos: el mismo
    criterio que `app/__init__.py` usa con las páginas — sin registro, no
    existe."""
    if _REGISTRO:
        return
    from app.ai.tools import (backtest, borrador, cartera,  # noqa: F401
                              catalogo, estrategias, manual, packs)
