"""Estrategias que NO existen: medirlas antes de decidir si vale crearlas.

El resto de las herramientas de backtest parten de una estrategia ya creada —
`run_backtest_preview` lee su historia calculada y `backtest_strategy_variant`
hereda de ella la elegibilidad. Eso dejaba un agujero grande y silencioso: en
una instalación sin ninguna estrategia todavía, la IA no tenía forma de medir
NADA, así que solo podía proponer ideas de memoria, sin un número que las
respalde. Que es exactamente lo contrario de para qué existe esta plataforma.

Acá la estrategia viaja entera en la llamada —componentes, pesos y filtro— y se
puntúa en memoria contra la historia real de señales. No se crea, no se guarda,
no queda rastro: la escritura sigue siendo una acción humana, y el camino para
materializar lo que valga la pena es armar un pack (`get_pack_spec`,
`preview_pack`) e importarlo desde la aplicación.

Las dos herramientas contestan preguntas distintas y se usan en ese orden:

  1. `backtest_strategy_draft` — ¿este mix ORDENA bien los activos? (IC y
     cuantiles: la pregunta barata, que descarta rápido).
  2. `simulate_strategy_draft_portfolio` — ¿y cuánto habría RENDIDO comprando
     los mejores? (curva de equity con costos, contra el benchmark).

Un IC lindo que no sobrevive al segundo paso es habitual: ordenar bien y ganar
plata después de costos no son la misma cosa.

Las dos respetan el holdout reservado y el contador de intentos de
`app.ai.prudencia`, que es lo que evita que "probar sale gratis" termine en una
estrategia elegida por casualidad.
"""
from app.ai import prudencia
from app.ai.caller import AiCaller
from app.ai.registry import tool

_TOPE_COMPONENTES = 8
_TOPE_HORIZONTES = 4
_TOPE_TOPN = 100

# Paso de fechas por defecto CON filtro. Sin filtro no hay motivo para saltear
# (leer los scores ya calculados es barato); con filtro, cada fecha son varias
# queries de operandos, y las cross-sections de días consecutivos están tan
# correlacionadas que medir una de cada cinco no mueve el IC medio.
_PASO_CON_FILTRO = 5


def _sesion():
    from app.database import get_session

    return get_session()


def _componentes(components: list) -> list:
    """Valida cantidad y forma. Los pesos los valida el servicio (fuente única:
    `strategy_service.parse_component_weight`)."""
    if not components:
        raise ValueError(
            "indicá al menos un componente: [{\"signal_key\": ..., "
            "\"weight\": ...}]. list_signals devuelve las keys disponibles.")
    if len(components) > _TOPE_COMPONENTES:
        raise ValueError(
            f"máximo {_TOPE_COMPONENTES} componentes. Una estrategia con más "
            f"señales que eso no es más precisa: reparte el peso hasta que "
            f"ninguna decide nada, y encima multiplica las combinaciones "
            f"posibles, que es como se llega a un resultado bueno por azar.")
    return list(components)


def _filtro(filter_conditions) -> str | None:
    """El árbol de elegibilidad como TEXTO JSON validado, o None.

    Acepta objeto o string porque un modelo manda cualquiera de los dos, y la
    diferencia importa: `strategy_filter.parse_tree` recibe texto y ante un
    JSON que no puede leer devuelve None —o sea, **corre sin filtro y sin
    avisar**—. Un borrador que se midiera sobre todo el universo creyendo que
    filtró sería un resultado equivocado imposible de detectar leyéndolo. Por
    eso acá se valida contra los catálogos vigentes y se falla fuerte.
    """
    import json

    from app.services import strategy_service

    if filter_conditions in (None, "", {}, []):
        return None
    texto = (filter_conditions if isinstance(filter_conditions, str)
             else json.dumps(filter_conditions))
    errores = strategy_service.validate_filter_conditions(texto)
    if errores:
        raise ValueError(
            "el filtro de elegibilidad tiene errores: " + "; ".join(errores)
            + ". La sintaxis del árbol está en la sección 6 del contrato de "
              "packs: pedila con get_pack_spec.")
    return texto


def _paso(date_step, filtro) -> int:
    if date_step:
        return max(1, int(date_step))
    return _PASO_CON_FILTRO if filtro else 1


def _cfg(vent: dict, horizons=None, n_quantiles=None) -> dict:
    cfg = {"date_from": vent["date_from"], "date_to": vent["date_to"]}
    if horizons:
        cfg["horizons"] = list(horizons)[:_TOPE_HORIZONTES]
    if n_quantiles:
        cfg["n_quantiles"] = int(n_quantiles)
    return cfg


_FILTRO_DESC = (
    "Árbol de elegibilidad: quién entra al ranking. Mismo formato que el "
    "filtro de un pack (sección 6 del contrato — pedila con get_pack_spec): "
    "{\"op\":\"AND\",\"children\":[{\"cond\":{...}}]}. Sin filtro rankea a "
    "todos los activos con dato, que suele ser lo que querés para una primera "
    "medición. Un dato faltante cuenta como condición NO cumplida."
)

_COMPONENTES_DESC = (
    "Los componentes del score: señales con su peso. El peso puede ser "
    "NEGATIVO —la señal aporta al revés— que es cómo se pide 'momentum alto "
    "pero volatilidad baja' sin necesitar una señal invertida. 0 no se acepta."
)


def _comun(caller, vent: dict, cobertura: dict, paso: int) -> dict:
    """Los campos que toda respuesta de borrador comparte."""
    n = prudencia.registrar_intento(caller)
    salida = {
        "guardado": False,
        "modo": vent["modo"],
        "date_from": vent["date_from"],
        "date_to": vent["date_to"],
        "corte_holdout": vent["corte"],
        "date_step": paso,
        "cobertura_pct": cobertura,
        "simulaciones_en_esta_sesion": n,
        "holdout": vent["nota"],
        "nota": ("No se creó ni se guardó nada: esta estrategia no existe en "
                 "la base. Si el resultado vale la pena, el camino para "
                 "materializarla es armar un pack (get_pack_spec para el "
                 "formato, preview_pack para ensayarlo) e importarlo desde la "
                 "pantalla de Señales y Estrategias."),
    }
    aviso = prudencia.aviso_intentos(n)
    if aviso:
        salida["aviso_sobreajuste"] = aviso
    if cobertura and min(cobertura.values()) < 80:
        salida["aviso_cobertura"] = (
            "Hay componentes con cobertura baja. Un activo sin dato en una "
            "señal NO queda afuera: su score se renormaliza sobre las señales "
            "que sí tiene, así que suele terminar mejor rankeado que uno "
            "completo, y el ranking termina midiendo quién tiene datos en vez "
            "de quién está mejor. Si vas a usar esa señal, pedí el dato "
            "también en el filtro de elegibilidad.")
    return salida


@tool(
    name="backtest_strategy_draft",
    familia="backtest",
    description=(
        "Mide una estrategia que NO EXISTE: le pasás los componentes, los "
        "pesos y (opcional) el filtro de elegibilidad, y devuelve qué tan bien "
        "ordena a los activos — IC por horizonte y rendimiento por cuantil. No "
        "crea nada.\n\n"
        "Es la herramienta para diseñar desde cero: si la instalación todavía "
        "no tiene ninguna estrategia creada, empezá por acá en vez de decir "
        "que no se puede medir. Las keys de señal salen de list_signals.\n\n"
        "IMPORTANTE — el resultado NO incluye toda la historia. El tramo final "
        "queda RESERVADO como prueba independiente y no entra en estos "
        "números. Explorá acá todo lo que necesites; recién cuando te hayas "
        "decidido por una configuración, volvé a pedirla con "
        "revelar_holdout=true para ver cómo le fue en el tramo que no miraste. "
        "Mirarlo antes de decidir lo desperdicia."
    ),
    input_schema={
        "type": "object",
        "properties": {
            "components": {
                "type": "array",
                "description": _COMPONENTES_DESC,
                "items": {
                    "type": "object",
                    "properties": {
                        "signal_key": {"type": "string"},
                        "weight": {"type": "number"},
                    },
                    "required": ["signal_key", "weight"],
                    "additionalProperties": False,
                },
            },
            "filter_conditions": {"type": "object", "description": _FILTRO_DESC},
            "horizons": {"type": "array", "items": {"type": "integer",
                                                    "minimum": 1},
                         "description": f"Ruedas hacia adelante a medir "
                                        f"(máximo {_TOPE_HORIZONTES}). Por "
                                        f"defecto 1, 5, 20 y 60."},
            "n_quantiles": {"type": "integer", "minimum": 2, "maximum": 20},
            "date_from": {"type": "string",
                          "description": "AAAA-MM-DD. Por defecto, los últimos "
                                         "5 años antes del corte."},
            "date_to": {"type": "string", "description": "AAAA-MM-DD."},
            "date_step": {
                "type": "integer", "minimum": 1,
                "description": ("Medir una fecha de cada N. Con filtro el "
                                "default es 5, que abarata mucho sin cambiar "
                                "el IC medio (los días consecutivos están casi "
                                "perfectamente correlacionados)."),
            },
            "revelar_holdout": {
                "type": "boolean",
                "description": ("Correr SOLO el tramo reservado. Usalo una vez "
                                "y al final, cuando ya elegiste."),
            },
        },
        "required": ["components"],
        "additionalProperties": False,
    },
)
def backtest_strategy_draft(caller: AiCaller, components: list,
                            filter_conditions=None, horizons: list | None = None,
                            n_quantiles: int | None = None,
                            date_from: str | None = None,
                            date_to: str | None = None,
                            date_step: int | None = None,
                            revelar_holdout: bool = False) -> dict:
    from app.ai.tools.backtest import _COMO_LEERLO, _estabilidad, _resumen_ic
    from app.services import backtest_service

    comps = _componentes(components)
    filtro = _filtro(filter_conditions)
    vent = prudencia.ventana(_sesion(), date_from, date_to, revelar_holdout)
    paso = _paso(date_step, filtro)

    datos = backtest_service.compute_draft_backtest(
        comps, filtro, _cfg(vent, horizons, n_quantiles), date_step=paso)

    salida = _comun(caller, vent, datos.get("cobertura") or {}, paso)
    salida.update({
        "componentes": comps,
        "filtro": filtro,
        "config": datos["config"],
        "n_dates": datos["n_dates"],
        "duration_seconds": round(datos.get("duration_seconds") or 0, 2),
        "ic": _resumen_ic(datos),
        "estabilidad": _estabilidad(datos),
        "quantiles": datos["quantile_stats"],
        "como_leerlo": _COMO_LEERLO,
    })
    return salida


@tool(
    name="simulate_strategy_draft_portfolio",
    familia="carteras",
    description=(
        "Simula la CARTERA de una estrategia que no existe: compra los N "
        "mejores del ranking, los rebalancea cada tantas ruedas y descuenta "
        "costos, contra un benchmark que compra todo el universo. Devuelve "
        "retorno, CAGR, volatilidad, Sharpe, Sortino y máxima caída, más los "
        "mismos números por tramos. No crea nada.\n\n"
        "Es el segundo paso, después de backtest_strategy_draft: ordenar bien "
        "los activos y ganar plata después de costos no son lo mismo, y una "
        "estrategia con buen IC puede perder contra el benchmark si rota "
        "demasiado.\n\n"
        "Igual que el backtest, esto NO incluye el tramo final de la historia: "
        "queda reservado hasta que lo pidas con revelar_holdout."
    ),
    input_schema={
        "type": "object",
        "properties": {
            "components": {
                "type": "array",
                "description": _COMPONENTES_DESC,
                "items": {
                    "type": "object",
                    "properties": {
                        "signal_key": {"type": "string"},
                        "weight": {"type": "number"},
                    },
                    "required": ["signal_key", "weight"],
                    "additionalProperties": False,
                },
            },
            "filter_conditions": {"type": "object", "description": _FILTRO_DESC},
            "top_n": {"type": "integer", "minimum": 1, "maximum": _TOPE_TOPN,
                      "description": "Cuántos activos se compran (default 10)."},
            "rebalance_every": {
                "type": "integer", "minimum": 1,
                "description": ("Cada cuántas ruedas se rearma la cartera "
                                "(default 20, o sea aproximadamente mensual). "
                                "Rebalancear todos los días multiplica los "
                                "costos."),
            },
            "cost_bps": {
                "type": "number", "minimum": 0,
                "description": ("Costo por operación en puntos básicos (100 = "
                                "1%). Default 0. Poné el real: es lo que "
                                "separa una estrategia rentable de una que "
                                "solo le gana a la comisión."),
            },
            "date_from": {"type": "string", "description": "AAAA-MM-DD."},
            "date_to": {"type": "string", "description": "AAAA-MM-DD."},
            "date_step": {"type": "integer", "minimum": 1},
            "revelar_holdout": {"type": "boolean"},
        },
        "required": ["components"],
        "additionalProperties": False,
    },
)
def simulate_strategy_draft_portfolio(caller: AiCaller, components: list,
                                      filter_conditions=None,
                                      top_n: int | None = None,
                                      rebalance_every: int | None = None,
                                      cost_bps: float | None = None,
                                      date_from: str | None = None,
                                      date_to: str | None = None,
                                      date_step: int | None = None,
                                      revelar_holdout: bool = False) -> dict:
    from app.ai.tools.cartera import _por_tramos, _solo_kpis
    from app.services import backtest_service
    from app.services import portfolio_backtest_service as pbs

    comps = _componentes(components)
    filtro = _filtro(filter_conditions)
    vent = prudencia.ventana(_sesion(), date_from, date_to, revelar_holdout)
    paso = _paso(date_step, filtro)
    tope = min(int(top_n or 10), _TOPE_TOPN)

    borrador = backtest_service.draft_score_rows(
        comps, filtro, _cfg(vent), date_step=paso)
    resultado = pbs.run_draft_portfolio_backtest(
        borrador["score_rows"], top_n=tope,
        rebalance_every=max(1, int(rebalance_every or 20)),
        cost_bps=float(cost_bps or 0.0))

    fechas = resultado["dates"]

    def _curva(res):
        return {**res, "dates": fechas}

    salida = _comun(caller, vent, borrador.get("cobertura") or {}, paso)
    salida.update({
        "componentes": comps,
        "filtro": filtro,
        "top_n": tope,
        "rebalance_every": max(1, int(rebalance_every or 20)),
        "cost_bps": float(cost_bps or 0.0),
        "n_ruedas": len(fechas),
        "desde": str(fechas[0]) if fechas else None,
        "hasta": str(fechas[-1]) if fechas else None,
        # La curva completa NO viaja: son miles de puntos y nadie los lee. Los
        # KPIs y los tramos son lo que se mira para decidir.
        "kpis": _solo_kpis(resultado["ranking"]),
        "kpis_por_tramo": _por_tramos(_curva(resultado["ranking"])),
        "benchmark_equiponderado": _solo_kpis(resultado["benchmark_ew"]),
        "como_leerlo": (
            "Compará SIEMPRE contra `benchmark_equiponderado`, que es comprar "
            "todo el universo sin seleccionar nada: si la estrategia no le "
            "gana, el ranking no está aportando y toda la maquinaria sobra. "
            "Después mirá `kpis_por_tramo`: una cartera que se sostiene se "
            "parece en todos los tramos, y un Sharpe alto que sale de uno solo "
            "no es una buena cartera, es un buen período. Y acordate de que "
            "estos números salen del mismo período con el que elegiste los "
            "pesos, así que están inflados por construcción."),
    })
    return salida
