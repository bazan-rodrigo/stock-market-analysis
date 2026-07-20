"""
Callbacks del manual de usuario.

Solo el buscador: la navegación entre secciones la resuelve el router de Dash
(cada dcc.Link vuelve a ejecutar layout() con el slug nuevo), así que no hace
falta un callback para eso.
"""
from dash import Input, Output, State, callback

from app.pages.manual import current_role, search_children, toc_children
from app.services import manual_service as ms

# Menos de 2 caracteres no filtra: con 1 letra casi todo matchea y el índice
# se vuelve ruido.
_MIN_QUERY = 2


@callback(
    Output("manual-toc", "children"),
    Input("manual-search", "value"),
    State("manual-active-slug", "data"),
    prevent_initial_call=True,
)
def buscar_en_manual(query, active_slug):
    """Reemplaza el índice por los resultados mientras se escribe.

    Se recalcula la visibilidad en cada llamada en vez de confiar en lo que
    llegó del cliente: el filtrado por rol no puede depender del navegador.
    """
    visibles = ms.visible(ms.load_sections(), ms.level_of(current_role()))
    q = (query or "").strip()
    if len(q) < _MIN_QUERY:
        return toc_children(visibles, active_slug)
    return search_children(ms.search(visibles, q), q)
