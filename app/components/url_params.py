"""Preselección de un dropdown desde la query string de la URL.

Dos pantallas reciben `?asset_id=N` desde los links del screener (Análisis de
Activo e Historial de Señales). El `value` NO se puede escribir antes que las
`options`: el `dcc.Dropdown` **borra todo value que no esté en sus options**
(el efecto de `async-dropdown.js` hace `valueSet.has(value) || setProps({value:
null})`). Un value que gana la carrera contra las options se pierde en
silencio y el selector queda vacío — era un bug intermitente real, con dos
callbacks independientes escribiendo el mismo componente sin orden garantizado.

De ahí la regla que implementa este módulo: **nunca emitir un value que las
options todavía no contengan**. Mientras eso no se cumpla la respuesta correcta
es `no_update` (el callback vuelve a disparar cuando llegan las options), y no
el value crudo.
"""
from urllib.parse import parse_qs

from dash import no_update


def int_param_from_search(search: str | None, param: str) -> int | None:
    """Entero del parámetro `param` en la query string, o None si no está,
    está vacío o no es un entero (una URL editada a mano no debe explotar)."""
    if not search:
        return None
    values = parse_qs(search.lstrip("?")).get(param, [])
    if not values:
        return None
    try:
        return int(values[0])
    except (ValueError, TypeError):
        return None


def option_values(options) -> set:
    """Values de una lista de options de dropdown (dicts o escalares pelados)."""
    return {opt.get("value") if isinstance(opt, dict) else opt
            for opt in (options or [])}


def preselect_from_options(options, search: str | None, param: str = "asset_id"):
    """Value a poner en el dropdown, o `no_update`.

    Devuelve el id de la URL **solo si ya figura entre las options**: eso es lo
    que hace la preselección determinista, sin importar cuál de los dos
    callbacks conteste primero. Un id inexistente en el catálogo también cae
    acá (deja el selector como estaba, en vez de vaciarlo).
    """
    target = int_param_from_search(search, param)
    if target is None or target not in option_values(options):
        return no_update
    return target


def text_param_from_search(search: str | None, param: str) -> str | None:
    """Texto del parámetro, sin espacios alrededor, o None si no está o está
    vacío. Para los parámetros que no son ids: la `key` de una señal, por
    ejemplo (`/admin/signals?editar=rsi_daily`)."""
    if not search:
        return None
    values = parse_qs(search.lstrip("?")).get(param, [])
    valor = (values[0] if values else "").strip()
    return valor or None


def float_param_from_search(search: str | None, param: str) -> float | None:
    """Número del parámetro, o None si no está o no es un número. Lo usa el
    puente Calibración → editor de Señales para llevar un min/max propuesto."""
    texto = text_param_from_search(search, param)
    if texto is None:
        return None
    try:
        return float(texto)
    except (ValueError, TypeError):
        return None
