"""Backtest de una estrategia: correr sin guardar, y leer lo guardado.

La pieza que hace posible esto es la separación entre computar y persistir
(`backtest_service.compute_backtest` / `save_backtest_run`): la IA corre
backtests **sin dejar rastro**, así que probar cinco variantes no llena la base
de corridas de prueba ni la pantalla de basura. Guardar sigue siendo una acción
humana desde la aplicación.

Lo que la IA NO puede hacer acá: persistir. No existe la herramienta.
"""
from app.ai import prudencia
from app.ai.caller import AiCaller
from app.ai.registry import limite, tool
from app.ai.tools.estrategias import _estrategia_visible

_TOPE_RUNS = 20
_TOPE_HORIZONTES = 4

# Las dos herramientas que CORREN algo (no las que leen un run guardado)
# comparten el holdout reservado y el contador de intentos con las de borrador:
# el sobreajuste no distingue si la estrategia existe o no, y un corte distinto
# por herramienta haría que dos mediciones no se puedan comparar.
_HOLDOUT_SCHEMA = {
    "type": "boolean",
    "description": ("Correr SOLO el tramo de historia reservado, el que no "
                    "entra en las corridas normales. Una vez y al final, "
                    "cuando ya elegiste: mirarlo antes de decidir lo "
                    "convierte en un tramo más de exploración."),
}


def _ventana(caller, date_from, date_to, revelar_holdout):
    from app.database import get_session

    return prudencia.ventana(get_session(), date_from, date_to,
                             revelar_holdout)


def _prudencia(caller, vent: dict) -> dict:
    """Los campos de holdout y contador que acompañan a toda corrida."""
    n = prudencia.registrar_intento(caller)
    salida = {"modo": vent["modo"], "corte_holdout": vent["corte"],
              "holdout": vent["nota"], "simulaciones_en_esta_sesion": n}
    aviso = prudencia.aviso_intentos(n)
    if aviso:
        salida["aviso_sobreajuste"] = aviso
    return salida


@tool(
    name="list_backtest_runs",
    familia="backtest",
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
    familia="backtest",
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


_TRAMOS = 4

# Viaja en la respuesta a propósito: sin esto, el modelo lee "ic_medio 0.09" y
# lo reporta como una mejora. El número solo significa algo acompañado de cómo
# se lee, y quien lo interpreta es el modelo, no un humano leyendo una tabla.
_COMO_LEERLO = (
    "`ic_in_sample` está medido sobre las MISMAS fechas con las que se eligió "
    "la variante, así que está inflado si probaste varias combinaciones: con "
    "suficientes intentos siempre aparece una que se ajusta al ruido. Mirá "
    "`estabilidad` antes de concluir nada, y compará los tramos ENTRE SÍ, no "
    "solo su signo. Hay dos formas de que el promedio mienta: que el signo se "
    "dé vuelta entre tramos, o —más engañosa— que todos sean positivos pero "
    "uno sea mucho más grande que el resto (por ejemplo 0,40 / 0,01 / 0,01 / "
    "0,01 promedia 0,11 y no hay señal, hay un tramo con suerte). Una relación "
    "que se sostiene se parece en todos los tramos. Ojo con `ic_ultimo_tramo`: "
    "es el último tramo de la ventana de exploración y NO es una prueba "
    "independiente —lo estás mirando igual que a los demás para elegir—. La "
    "prueba independiente es el tramo reservado, que no está en estos números "
    "y se pide aparte con `revelar_holdout` cuando ya te decidiste. Al "
    "informarle esto a la persona, mostrale los tramos, no solo el promedio."
)


def _estabilidad(datos: dict, n_tramos: int = _TRAMOS) -> dict:
    """El IC partido en tramos consecutivos, y el último aparte (holdout).

    Por qué está: el IC medio de todo el período es **in-sample** — se mide
    sobre los mismos datos con los que se eligieron los componentes, así que
    está contaminado por la elección. Probar muchas variantes y quedarse con la
    mejor no encuentra la mejor estrategia: encuentra la que mejor se ajustó al
    ruido de esa historia. Con suficientes intentos siempre hay una que parece
    excelente por casualidad, y la casualidad no se repite.

    Partir en tramos no convierte el número en honesto, pero **hace visible el
    problema**: un IC medio de 0,08 que sale de 0,22 / 0,01 / −0,03 / 0,05 no
    es una señal estable, es un tramo bueno arrastrando al promedio. Y el
    último tramo es lo más parecido a un holdout que se puede dar sin rehacer
    la elección: vale solo si quien eligió los componentes no lo miró.

    Sale gratis: son los mismos `ic_points` ya calculados, agrupados por fecha.
    """
    fechas = sorted({p["date"] for p in datos["ic_points"]})
    if len(fechas) < n_tramos * 2:
        return {"tramos": None,
                "motivo": (f"hacen falta al menos {n_tramos * 2} fechas para "
                           f"partir en {n_tramos} tramos comparables")}

    corte = len(fechas) // n_tramos
    limites = [(fechas[i * corte],
                fechas[(i + 1) * corte - 1] if i < n_tramos - 1 else fechas[-1])
               for i in range(n_tramos)]

    por_horizonte: dict = {}
    for h in datos["config"]["horizons"]:
        tramos = []
        for desde, hasta in limites:
            ics = [p["ic"] for p in datos["ic_points"]
                   if p["horizon"] == h and p["ic"] is not None
                   and desde <= p["date"] <= hasta]
            tramos.append({
                "desde": str(desde), "hasta": str(hasta),
                "ic_medio": round(sum(ics) / len(ics), 4) if ics else None,
                "n_fechas": len(ics),
            })
        if not any(t["ic_medio"] is not None for t in tramos):
            continue
        medidos = [t["ic_medio"] for t in tramos if t["ic_medio"] is not None]
        por_horizonte[str(h)] = {
            "tramos": tramos,
            # NO se llama holdout: es el último tramo de la ventana que la IA
            # mira entera para elegir, así que no prueba nada por sí solo. El
            # holdout de verdad quedó afuera del período (app/ai/prudencia.py),
            # y un campo con ese nombre acá haría creer que ya se lo vio.
            "ic_ultimo_tramo": tramos[-1]["ic_medio"],
            "tramos_positivos": sum(1 for x in medidos if x > 0),
            "tramos_medidos": len(medidos),
        }
    return {"tramos": por_horizonte}


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
    familia="backtest",
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
            "revelar_holdout": _HOLDOUT_SCHEMA,
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
                              date_to: str | None = None,
                              revelar_holdout: bool = False) -> dict:
    from app.services import backtest_service

    strat = _estrategia_visible(caller, strategy_id)
    vent = _ventana(caller, date_from, date_to, revelar_holdout)

    cfg = {"date_from": vent["date_from"], "date_to": vent["date_to"]}
    if horizons:
        cfg["horizons"] = list(horizons)[:_TOPE_HORIZONTES]
    if n_quantiles:
        cfg["n_quantiles"] = int(n_quantiles)

    datos = backtest_service.compute_variant_backtest(
        strat.id, list(components), cfg)

    return {
        "strategy_id": strat.id,
        "name": strat.name,
        "guardado": False,
        **_prudencia(caller, vent),
        "config": datos["config"],
        "duration_seconds": round(datos.get("duration_seconds") or 0, 2),
        "base": {"ic_in_sample": _resumen_ic(datos["base"]),
                 "estabilidad": _estabilidad(datos["base"]),
                 "quantiles": datos["base"]["quantile_stats"],
                 "n_dates": datos["base"]["n_dates"]},
        "variante": {"componentes": components,
                     "ic_in_sample": _resumen_ic(datos["variante"]),
                     "estabilidad": _estabilidad(datos["variante"]),
                     "quantiles": datos["variante"]["quantile_stats"],
                     "n_dates": datos["variante"]["n_dates"]},
        "como_leerlo": _COMO_LEERLO,
        "nota": ("Nada de esto se guardó ni se creó. La variante se evaluó "
                 "sobre la misma elegibilidad que la estrategia base, así que "
                 "la diferencia de IC aísla el efecto de los componentes."),
    }


@tool(
    name="run_backtest_preview",
    familia="backtest",
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
            "revelar_holdout": _HOLDOUT_SCHEMA,
        },
        "required": ["strategy_id"],
        "additionalProperties": False,
    },
)
def run_backtest_preview(caller: AiCaller, strategy_id: int,
                         horizons: list | None = None,
                         n_quantiles: int | None = None,
                         date_from: str | None = None,
                         date_to: str | None = None,
                         revelar_holdout: bool = False) -> dict:
    from app.services import backtest_service

    strat = _estrategia_visible(caller, strategy_id)
    vent = _ventana(caller, date_from, date_to, revelar_holdout)

    cfg = {"date_from": vent["date_from"], "date_to": vent["date_to"]}
    if horizons:
        # El tope no es capricho: cada horizonte es una cross-section más por
        # fecha, así que el cómputo crece linealmente con la lista.
        cfg["horizons"] = list(horizons)[:_TOPE_HORIZONTES]
    if n_quantiles:
        cfg["n_quantiles"] = int(n_quantiles)

    datos = backtest_service.compute_backtest(strat.id, cfg)
    resumen = _resumen_ic(datos)

    return {
        "strategy_id": strat.id,
        "name": strat.name,
        "guardado": False,
        **_prudencia(caller, vent),
        "config": datos["config"],
        "date_from": str(datos["date_from"]),
        "date_to": str(datos["date_to"]),
        "n_dates": datos["n_dates"],
        "duration_seconds": round(datos.get("duration_seconds") or 0, 2),
        "ic_in_sample": resumen,
        "estabilidad": _estabilidad(datos),
        "quantiles": datos["quantile_stats"],
        "como_leerlo": _COMO_LEERLO,
        "nota": ("Este resultado NO se guardó. Para conservarlo hay que correr "
                 "el backtest desde la pantalla de Backtest de la aplicación."),
    }
