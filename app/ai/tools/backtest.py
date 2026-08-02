"""Backtest de una estrategia: correr sin guardar, y leer lo guardado.

La pieza que hace posible esto es la separación entre computar y persistir
(`backtest_service.compute_backtest` / `save_backtest_run`): la IA corre
backtests **sin dejar rastro**, así que probar cinco variantes no llena la base
de corridas de prueba ni la pantalla de basura. Guardar sigue siendo una acción
humana desde la aplicación.

Lo que la IA NO puede hacer acá: persistir. No existe la herramienta.
"""
from app.ai.caller import AiCaller
from app.ai.registry import limite, tool
from app.ai.tools.estrategias import _estrategia_visible

_TOPE_RUNS = 20
_TOPE_HORIZONTES = 4


@tool(
    name="list_backtest_runs",
    description=(
        "Los backtests ya guardados de una estrategia, del más reciente al más "
        "viejo, con su configuración y el período analizado. Un backtest "
        "guardado es una FOTO: la historia de la estrategia se reescribe con "
        "cada recálculo, así que un run viejo puede no ser reproducible hoy."
    ),
    input_schema={
        "type": "object",
        "properties": {
            "strategy_id": {"type": "integer"},
            "limit": {"type": "integer", "minimum": 1},
        },
        "required": ["strategy_id"],
        "additionalProperties": False,
    },
    max_rows=_TOPE_RUNS,
)
def list_backtest_runs(caller: AiCaller, strategy_id: int,
                       limit: int | None = None) -> dict:
    import json

    from app.services import backtest_service

    strat = _estrategia_visible(caller, strategy_id)
    tope = limite(limit, _TOPE_RUNS)
    runs = backtest_service.list_runs([strat.id])[:tope]
    return {
        "strategy_id": strat.id,
        "name": strat.name,
        "runs": [
            {"run_id": r.id, "status": r.status, "error": r.error,
             "date_from": str(r.date_from) if r.date_from else None,
             "date_to": str(r.date_to) if r.date_to else None,
             "n_dates": r.n_dates, "duration_seconds": r.duration_seconds,
             "created_at": str(r.created_at),
             "config": json.loads(r.config) if r.config else None}
            for r in runs
        ],
    }


@tool(
    name="get_backtest_results",
    description=(
        "El resultado de un backtest guardado: rendimiento medio por cuantil y "
        "horizonte, más el resumen del IC (correlación entre el puntaje y el "
        "retorno posterior). Un IC medio positivo y consistente indica que el "
        "puntaje ordena bien; cercano a cero, que no aporta información."
    ),
    input_schema={
        "type": "object",
        "properties": {"run_id": {"type": "integer"}},
        "required": ["run_id"],
        "additionalProperties": False,
    },
)
def get_backtest_results(caller: AiCaller, run_id: int) -> dict:
    from app.services import backtest_service

    datos = backtest_service.get_run_results(int(run_id))
    if datos is None:
        raise ValueError(f"no existe el backtest {run_id}.")
    # El run se pide por id: hay que chequear que la estrategia sea visible, o
    # se leerían los resultados de una estrategia ajena probando números.
    strat = _estrategia_visible(caller, datos["run"].strategy_id)

    run = datos["run"]
    return {
        "run_id": run.id, "strategy_id": strat.id, "name": strat.name,
        "status": run.status,
        "date_from": str(run.date_from) if run.date_from else None,
        "date_to": str(run.date_to) if run.date_to else None,
        "n_dates": run.n_dates,
        "config": datos.get("config"),
        "ic": datos.get("ic_summary"),
        "quantiles": [
            {"horizon": q.horizon, "quantile": q.quantile,
             "n_dates": q.n_dates, "mean_ret": q.mean_ret,
             "median_ret": q.median_ret, "pct_pos": q.pct_pos}
            for q in datos.get("quantile_stats", [])
        ],
    }


def _resumen_ic(datos: dict) -> dict:
    """El IC punto a punto puede ser de miles de fechas; al modelo le va el
    resumen por horizonte, que es lo que se lee para decidir."""
    resumen = {}
    for h in datos["config"]["horizons"]:
        ics = [p["ic"] for p in datos["ic_points"]
               if p["horizon"] == h and p["ic"] is not None]
        if not ics:
            continue
        n = len(ics)
        media = sum(ics) / n
        desvio = None
        if n > 1:
            desvio = (sum((x - media) ** 2 for x in ics) / (n - 1)) ** 0.5
        resumen[str(h)] = {
            "ic_medio": round(media, 4),
            "ic_desvio": round(desvio, 4) if desvio else None,
            "pct_fechas_positivas": round(sum(1 for x in ics if x > 0) / n, 4),
            "n_fechas": n,
        }
    return resumen


@tool(
    name="backtest_strategy_variant",
    description=(
        "Prueba una VARIANTE de una estrategia —otros componentes u otros "
        "pesos— y la compara con la original, sin crear nada. Contesta '¿y si "
        "le subo el peso al momentum?' o '¿y si le agrego esta señal?'.\n\n"
        "La variante hereda el filtro de elegibilidad de la estrategia base: "
        "se evalúa sobre los mismos activos y fechas, así que la comparación "
        "aísla el efecto de los componentes. Para cambiar el universo hay que "
        "editar la estrategia en la aplicación.\n\n"
        "El peso puede ser NEGATIVO: la señal aporta al revés (el activo "
        "puntúa alto donde esa señal puntúa bajo). Es cómo se pide 'momentum "
        "alto pero volatilidad baja' sin necesitar una señal invertida."
    ),
    input_schema={
        "type": "object",
        "properties": {
            "strategy_id": {"type": "integer",
                            "description": "La estrategia base a variar."},
            "components": {
                "type": "array",
                "description": "Los componentes de la VARIANTE (reemplazan a "
                               "los de la base, no se suman).",
                "items": {
                    "type": "object",
                    "properties": {
                        "signal_key": {"type": "string",
                                       "description": "La key de la señal "
                                                      "(list_signals la da)."},
                        "weight": {"type": "number",
                                   "description": "Puede ser negativo. 0 no."},
                    },
                    "required": ["signal_key", "weight"],
                    "additionalProperties": False,
                },
            },
            "horizons": {"type": "array", "items": {"type": "integer", "minimum": 1},
                         "description": f"Máximo {_TOPE_HORIZONTES}."},
            "n_quantiles": {"type": "integer", "minimum": 2, "maximum": 20},
            "date_from": {"type": "string", "description": "AAAA-MM-DD."},
            "date_to": {"type": "string", "description": "AAAA-MM-DD."},
        },
        "required": ["strategy_id", "components"],
        "additionalProperties": False,
    },
)
def backtest_strategy_variant(caller: AiCaller, strategy_id: int,
                              components: list,
                              horizons: list | None = None,
                              n_quantiles: int | None = None,
                              date_from: str | None = None,
                              date_to: str | None = None) -> dict:
    from app.services import backtest_service

    strat = _estrategia_visible(caller, strategy_id)

    cfg = {}
    if horizons:
        cfg["horizons"] = list(horizons)[:_TOPE_HORIZONTES]
    if n_quantiles:
        cfg["n_quantiles"] = int(n_quantiles)
    if date_from:
        cfg["date_from"] = date_from
    if date_to:
        cfg["date_to"] = date_to

    datos = backtest_service.compute_variant_backtest(
        strat.id, list(components), cfg)

    return {
        "strategy_id": strat.id,
        "name": strat.name,
        "guardado": False,
        "config": datos["config"],
        "duration_seconds": round(datos.get("duration_seconds") or 0, 2),
        "base": {"ic": _resumen_ic(datos["base"]),
                 "quantiles": datos["base"]["quantile_stats"],
                 "n_dates": datos["base"]["n_dates"]},
        "variante": {"componentes": components,
                     "ic": _resumen_ic(datos["variante"]),
                     "quantiles": datos["variante"]["quantile_stats"],
                     "n_dates": datos["variante"]["n_dates"]},
        "nota": ("Nada de esto se guardó ni se creó. La variante se evaluó "
                 "sobre la misma elegibilidad que la estrategia base, así que "
                 "la diferencia de IC aísla el efecto de los componentes. "
                 "Cuidado con leer una mejora chica como una mejora real: "
                 "probar muchas variantes sobre la misma historia sobreajusta."),
    }


@tool(
    name="run_backtest_preview",
    description=(
        "Corre un backtest de cuantiles y devuelve el resultado SIN guardarlo. "
        "Sirve para explorar: probar otro horizonte o período no deja rastro "
        "ni ocupa lugar. Si el resultado vale la pena, el usuario lo guarda "
        "desde la pantalla de Backtest.\n\n"
        "Tarda: acota el período con date_from/date_to en vez de correr toda "
        "la historia. Requiere que la estrategia tenga historia calculada."
    ),
    input_schema={
        "type": "object",
        "properties": {
            "strategy_id": {"type": "integer"},
            "horizons": {
                "type": "array", "items": {"type": "integer", "minimum": 1},
                "description": (
                    f"Ruedas hacia adelante a medir (máximo {_TOPE_HORIZONTES}). "
                    f"Por defecto 1, 5, 20 y 60."),
            },
            "n_quantiles": {"type": "integer", "minimum": 2, "maximum": 20,
                            "description": "Cuantiles (por defecto 10)."},
            "date_from": {"type": "string", "description": "AAAA-MM-DD."},
            "date_to": {"type": "string", "description": "AAAA-MM-DD."},
        },
        "required": ["strategy_id"],
        "additionalProperties": False,
    },
)
def run_backtest_preview(caller: AiCaller, strategy_id: int,
                         horizons: list | None = None,
                         n_quantiles: int | None = None,
                         date_from: str | None = None,
                         date_to: str | None = None) -> dict:
    from app.services import backtest_service

    strat = _estrategia_visible(caller, strategy_id)

    cfg = {}
    if horizons:
        # El tope no es capricho: cada horizonte es una cross-section más por
        # fecha, así que el cómputo crece linealmente con la lista.
        cfg["horizons"] = list(horizons)[:_TOPE_HORIZONTES]
    if n_quantiles:
        cfg["n_quantiles"] = int(n_quantiles)
    if date_from:
        cfg["date_from"] = date_from
    if date_to:
        cfg["date_to"] = date_to

    datos = backtest_service.compute_backtest(strat.id, cfg)
    resumen = _resumen_ic(datos)

    return {
        "strategy_id": strat.id,
        "name": strat.name,
        "guardado": False,
        "config": datos["config"],
        "date_from": str(datos["date_from"]),
        "date_to": str(datos["date_to"]),
        "n_dates": datos["n_dates"],
        "duration_seconds": round(datos.get("duration_seconds") or 0, 2),
        "ic": resumen,
        "quantiles": datos["quantile_stats"],
        "nota": ("Este resultado NO se guardó. Para conservarlo hay que correr "
                 "el backtest desde la pantalla de Backtest de la aplicación."),
    }
