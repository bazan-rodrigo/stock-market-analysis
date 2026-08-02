"""Estrategias visibles, su ranking vigente y la historia de un score.

Los servicios de lectura de estrategias reciben un `strategy_id` y devuelven lo
que haya: `get_strategy_results`, `get_available_dates` y
`get_strategy_score_history` NO chequean visibilidad — el gate era que la
pantalla ya hubiera resuelto qué estrategias ofrecer en el desplegable. Acá no
hay pantalla, así que toda herramienta resuelve la estrategia con
`_estrategia_visible()` antes de tocar nada.
"""
from app.ai.caller import AiCaller
from app.ai.registry import limite, tool

_TOPE_RANKING = 100
_TOPE_HISTORIA = 200


def _estrategia_visible(caller: AiCaller, strategy_id: int):
    """La estrategia, o ValueError. Mismo mensaje exista o no: si el usuario no
    la puede ver, tampoco debería poder deducir que existe probando ids."""
    from app.services import strategy_service
    from app.services.visibility import can_view

    user_id, is_admin = caller.viewer()
    strat = strategy_service.get_strategy_by_id(int(strategy_id))
    if strat is None or not can_view(strat.owner_id, strat.is_public,
                                     user_id, is_admin):
        raise ValueError(
            f"no existe una estrategia con id={strategy_id} que puedas ver. "
            f"Usá list_strategies para ver las disponibles.")
    return strat


@tool(
    name="list_strategies",
    description=(
        "Las estrategias que podés ver (públicas más las tuyas; un "
        "administrador las ve todas). Devuelve el id de cada una, que es lo "
        "que piden las demás herramientas de estrategia."
    ),
    input_schema={
        "type": "object",
        "properties": {
            "limit": {"type": "integer", "minimum": 1},
        },
        "additionalProperties": False,
    },
    max_rows=200,
)
def list_strategies(caller: AiCaller, limit: int | None = None) -> dict:
    from app.services import strategy_service

    from app.services import signal_service

    user_id, is_admin = caller.viewer()
    tope = limite(limit, 200)
    filas = strategy_service.get_visible_strategies(user_id, is_admin)

    # Los componentes se devuelven por `signal_key`, no por el id interno. Con
    # el id la herramienta era casi inútil para lo primero que uno pregunta
    # ("¿de qué está hecha esta estrategia?"): `list_signals` identifica por
    # key y no expone ids, así que las dos respuestas no se podían cruzar.
    # La key es además el identificador del formato de packs.
    por_id = {s.id: s for s in signal_service.get_visible_signals(user_id, is_admin)}

    def _componentes(st):
        salida = []
        for c in st.components:
            sig = por_id.get(c.signal_id)
            salida.append({
                "signal_key": sig.key if sig else None,
                "signal_name": sig.name if sig else None,
                "weight": c.weight,
            })
        return salida

    return {
        "total": len(filas),
        "devueltas": min(len(filas), tope),
        "strategies": [
            {"id": st.id, "name": st.name, "description": st.description,
             "publica": bool(st.is_public),
             "componentes": _componentes(st),
             "filter_conditions": st.filter_conditions}
            for st in filas[:tope]
        ],
    }


@tool(
    name="strategy_ranking",
    description=(
        "El ranking de una estrategia en una fecha: los activos ordenados por "
        "su puntaje, del mejor al peor. Sin fecha usa la última calculada. El "
        "ranking es TRANSVERSAL: la posición de un activo depende de todos los "
        "demás de esa fecha, así que no se puede leer un activo aislado."
    ),
    input_schema={
        "type": "object",
        "properties": {
            "strategy_id": {"type": "integer",
                            "description": "Id que devuelve list_strategies."},
            "date": {"type": "string",
                     "description": "Fecha AAAA-MM-DD. Vacío = la última calculada."},
            "limit": {"type": "integer", "minimum": 1,
                      "description": f"Cuántos activos. Máximo {_TOPE_RANKING}."},
        },
        "required": ["strategy_id"],
        "additionalProperties": False,
    },
    max_rows=_TOPE_RANKING,
)
def strategy_ranking(caller: AiCaller, strategy_id: int,
                     date: str | None = None, limit: int | None = None) -> dict:
    from app.services import strategy_service

    strat = _estrategia_visible(caller, strategy_id)
    fechas = strategy_service.get_available_dates(strat.id)
    if not fechas:
        return {"strategy_id": strat.id, "name": strat.name, "date": None,
                "ranking": [],
                "aviso": ("la estrategia no tiene historia calculada; hay que "
                          "correr el pipeline de señales y estrategias")}

    if date:
        objetivo = next((d for d in fechas if str(d) == date), None)
        if objetivo is None:
            raise ValueError(
                f"la estrategia no tiene resultados en {date}. Última "
                f"calculada: {fechas[0]}.")
    else:
        objetivo = fechas[0]

    tope = limite(limit, _TOPE_RANKING)
    filas = strategy_service.get_strategy_results(strat.id, objetivo)
    return {
        "strategy_id": strat.id,
        "name": strat.name,
        "date": str(objetivo),
        "total_activos": len(filas),
        "devueltos": min(len(filas), tope),
        "ranking": [
            {"puesto": i + 1, "asset_id": r["asset_id"], "ticker": r["ticker"],
             "name": r["name"], "score": r["score"]}
            for i, r in enumerate(filas[:tope])
        ],
    }


@tool(
    name="strategy_score_history",
    description=(
        "Cómo evolucionó el puntaje de una estrategia para uno o más activos. "
        "Sirve para ver si un activo viene mejorando o deteriorándose. Acotá "
        "el rango de fechas: la serie completa puede ser de años."
    ),
    input_schema={
        "type": "object",
        "properties": {
            "strategy_id": {"type": "integer"},
            "asset_ids": {"type": "array", "items": {"type": "integer"},
                          "description": "Ids de activo (los da strategy_ranking)."},
            "date_from": {"type": "string", "description": "AAAA-MM-DD."},
            "date_to": {"type": "string", "description": "AAAA-MM-DD."},
            "limit": {"type": "integer", "minimum": 1,
                      "description": f"Puntos por activo. Máximo {_TOPE_HISTORIA}."},
        },
        "required": ["strategy_id", "asset_ids"],
        "additionalProperties": False,
    },
    max_rows=_TOPE_HISTORIA,
)
def strategy_score_history(caller: AiCaller, strategy_id: int,
                           asset_ids: list, date_from: str | None = None,
                           date_to: str | None = None,
                           limit: int | None = None) -> dict:
    from app.services import strategy_service

    strat = _estrategia_visible(caller, strategy_id)
    if not asset_ids:
        raise ValueError("indicá al menos un asset_id.")
    # El tope se aplica también a la CANTIDAD de activos: 50 activos × 200
    # puntos serían 10.000 filas por una sola llamada.
    ids = [int(a) for a in asset_ids][:20]
    tope = limite(limit, _TOPE_HISTORIA)

    series = strategy_service.get_strategy_score_history(
        strat.id, ids, date_from or None, date_to or None)
    return {
        "strategy_id": strat.id,
        "name": strat.name,
        "series": {
            str(aid): {
                "puntos": len(puntos),
                "devueltos": min(len(puntos), tope),
                # La cola: lo reciente es lo que se pregunta.
                "valores": [{"date": str(d), "score": sc}
                            for d, sc in puntos[-tope:]],
            }
            for aid, puntos in series.items()
        },
    }
