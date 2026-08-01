"""Qué existe en ESTA instalación: indicadores, señales y estrategias visibles.

Es la mitad variable del estándar de packs (la fija es `strategy_packs/SPEC.md`,
igual en todas las instalaciones). Sin esto un modelo no puede saber qué
`indicator_key` son válidos: cambian de una base a otra.
"""
from app.ai.registry import limite, tool
from app.ai.caller import AiCaller


@tool(
    name="get_catalog",
    description=(
        "Catálogo de esta instalación: indicadores disponibles con su tipo, "
        "categoría y valores posibles; sectores, mercados, países e industrias "
        "cargados; y las señales y estrategias que existen y podés ver. Es lo "
        "que hace falta para razonar sobre esta base en concreto, porque cambia "
        "de una instalación a otra. Pedilo una vez al empezar."
    ),
    input_schema={"type": "object", "properties": {}, "additionalProperties": False},
)
def get_catalog(caller: AiCaller) -> dict:
    from app.services import pack_service, signal_service, strategy_service

    user_id, is_admin = caller.viewer()
    catalogo = pack_service.build_catalog()

    # build_catalog() enumera TODAS las señales y estrategias: lo escribió el
    # botón "Catálogo", que es admin-only, así que nunca necesitó filtrar. Acá
    # el caller puede ser un analista, así que esas dos claves se reemplazan por
    # la vista del usuario. Se reemplaza en vez de tocar pack_service para no
    # cambiar lo que baja el botón, que es un artefacto de admin.
    catalogo["signals"] = [
        {"key": sg.key, "name": sg.name, "indicator_key": sg.indicator_key,
         "formula_type": sg.formula_type, "publica": bool(sg.is_public)}
        for sg in signal_service.get_visible_signals(user_id, is_admin)
    ]
    catalogo["strategies"] = [
        {"id": st.id, "name": st.name, "publica": bool(st.is_public)}
        for st in strategy_service.get_visible_strategies(user_id, is_admin)
    ]
    catalogo["senales_solo_admin"] = True
    catalogo["nota"] = (
        "Las señales las crea únicamente un administrador desde la pantalla: "
        "el catálogo es curado, con una sola implementación por concepto, para "
        "que las estrategias sean comparables entre sí. Podés proponer una "
        "señal nueva, pero componé primero con las que ya existen. Para usar "
        "una señal 'al revés' no hace falta duplicarla: un componente de "
        "estrategia admite peso NEGATIVO."
    )
    return catalogo


@tool(
    name="list_signals",
    description=(
        "Las señales que podés ver (públicas más las tuyas; un administrador "
        "las ve todas), con su fórmula y sus parámetros. Una señal traduce un "
        "indicador a un puntaje comparable de −100 a +100."
    ),
    input_schema={
        "type": "object",
        "properties": {
            "limit": {"type": "integer", "minimum": 1,
                      "description": "Máximo de señales a devolver."},
        },
        "additionalProperties": False,
    },
    max_rows=200,
)
def list_signals(caller: AiCaller, limit: int | None = None) -> dict:
    from app.services import signal_service

    user_id, is_admin = caller.viewer()
    tope = limite(limit, 200)
    filas = signal_service.get_visible_signals(user_id, is_admin)
    return {
        "total": len(filas),
        "devueltas": min(len(filas), tope),
        "signals": [
            {"key": s.key, "name": s.name, "description": s.description,
             "indicator_key": s.indicator_key, "formula_type": s.formula_type,
             "params": s.params, "publica": bool(s.is_public)}
            for s in filas[:tope]
        ],
    }
