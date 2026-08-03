"""Distribución de un indicador ENTRE activos, para calibrar señales.

Una señal traduce un indicador a un puntaje de −100 a +100 con cortes elegidos
a mano: el `min`/`max` de `range`, los tramos de `threshold`, las categorías de
`discrete_map`. Si esos cortes caen fuera de donde vive la masa de los datos la
señal **no discrimina**, y el modo de fallar es silencioso: con `clamp` todos
los activos saturan en ±100, la señal aporta el mismo número a todos y el
ranking —que es transversal— deja de ordenar por ella sin que nada dé error.
Al revés (rango demasiado ancho) todos se apiñan cerca de 0 y pasa lo mismo.

Esto mide dónde vive la masa, para que esos cortes salgan de percentiles
medidos en vez de doctrina.

**Lee con la misma semántica que el motor de señales** (`query_values_asof`:
última fila ≤ la fecha, por columna), así que lo que devuelve es la
distribución que la señal efectivamente ve, no una aproximación. Los
indicadores sin historia (`keep_history=False`) solo tienen valor vigente y se
leen de `current_indicator_values`, igual que hace `signal_service`.

Nada de esto escribe.
"""
import logging
from datetime import date as _date
from datetime import datetime as _datetime

import numpy as np

logger = logging.getLogger(__name__)

# Percentiles reportados. Incluye las colas (1/99) porque son las que dicen si
# un `clamp` está recortando a un puñado de activos o a media base.
PERCENTILES = (1, 5, 10, 25, 50, 75, 90, 95, 99)

# Tope de categorías distintas a devolver. Un indicador categórico del sistema
# tiene 10 o 12; el tope es una red por si alguna vez uno guarda basura.
MAX_CATEGORIAS = 30


def parse_fecha(valor) -> _date | None:
    """Texto ISO / date / datetime → date. None se propaga.

    Existe para que la comparación contra la columna `date` sea entre fechas y
    no entre una fecha y un string: en PostgreSQL eso último no compara como
    uno espera y el síntoma es "no hay datos", no un error.
    """
    if valor is None or isinstance(valor, _date) and not isinstance(valor, _datetime):
        return valor
    if isinstance(valor, _datetime):
        return valor.date()
    texto = str(valor).strip()
    if not texto:
        return None
    try:
        return _date.fromisoformat(texto[:10])
    except ValueError as exc:
        raise ValueError(
            f"fecha inválida: {valor!r}. Se espera AAAA-MM-DD.") from exc


def _saturacion(arr: np.ndarray, escala) -> dict | None:
    """Qué porcentaje de los activos quedaría recortado por una escala
    `range` propuesta. Es la respuesta directa a "¿mis umbrales están bien
    puestos?", sin que quien pregunta tenga que hacer la cuenta con los
    percentiles.

    `min` puede ser mayor que `max` (así se invierte una señal), por eso los
    extremos se ordenan antes de comparar: lo que importa acá es el intervalo,
    no hacia qué lado puntúa.
    """
    if not escala:
        return None
    try:
        a, b = float(escala["min"]), float(escala["max"])
    except (KeyError, TypeError, ValueError) as exc:
        raise ValueError(
            "escala debe traer 'min' y 'max' numéricos") from exc
    if a == b:
        raise ValueError("escala: min y max no pueden ser iguales")
    lo, hi = (a, b) if a < b else (b, a)
    n = arr.size
    bajo = int(np.count_nonzero(arr < lo))
    sobre = int(np.count_nonzero(arr > hi))
    return {
        "min": a, "max": b,
        "pct_debajo_del_rango": round(bajo / n * 100, 2),
        "pct_encima_del_rango": round(sobre / n * 100, 2),
        "pct_saturado": round((bajo + sobre) / n * 100, 2),
        "pct_dentro": round((n - bajo - sobre) / n * 100, 2),
    }


def resumen_numerico(valores, total_activos: int, escala=None) -> dict:
    """Estadísticos de una lista de valores numéricos. Lógica pura."""
    limpios = []
    for v in valores:
        try:
            f = float(v)
        except (TypeError, ValueError):
            continue
        if np.isfinite(f):
            limpios.append(f)

    n = len(limpios)
    if n == 0:
        return {"n": 0, "cobertura_pct": 0.0,
                "nota": "ningún activo tiene valor para este indicador"}

    arr = np.asarray(limpios, dtype=float)
    ps = np.percentile(arr, PERCENTILES)
    salida = {
        "n": n,
        "cobertura_pct": (round(n / total_activos * 100, 2)
                          if total_activos else None),
        "min": round(float(arr.min()), 4),
        "max": round(float(arr.max()), 4),
        "media": round(float(arr.mean()), 4),
        "desvio": round(float(arr.std(ddof=0)), 4),
        "percentiles": {f"p{p}": round(float(v), 4)
                        for p, v in zip(PERCENTILES, ps)},
    }
    sat = _saturacion(arr, escala)
    if sat:
        salida["escala_propuesta"] = sat
    return salida


def resumen_categorico(valores, total_activos: int) -> dict:
    """Frecuencia de cada categoría. Lógica pura.

    Para un `discrete_map` esto es el equivalente de los percentiles: dice qué
    categorías existen de verdad y con qué peso, y —sobre todo— cuáles hay que
    mapear sí o sí, porque una categoría sin mapear deja la señal MUDA ese día
    y una señal muda no cuenta como cero: se saltea y los pesos se renormalizan
    entre las demás.
    """
    conteo: dict[str, int] = {}
    for v in valores:
        if v is None:
            continue
        conteo[str(v)] = conteo.get(str(v), 0) + 1

    n = sum(conteo.values())
    if n == 0:
        return {"n": 0, "cobertura_pct": 0.0,
                "nota": "ningún activo tiene valor para este indicador"}

    orden = sorted(conteo.items(), key=lambda kv: (-kv[1], kv[0]))
    return {
        "n": n,
        "cobertura_pct": (round(n / total_activos * 100, 2)
                          if total_activos else None),
        "categorias": [{"valor": k, "n": c, "pct": round(c / n * 100, 2)}
                       for k, c in orden[:MAX_CATEGORIAS]],
        "categorias_distintas": len(conteo),
    }


def distribucion_indicador(code: str, fecha=None, escala=None) -> dict:
    """Distribución transversal de un indicador: todos los activos, una fecha.

    `fecha` None = la última fecha con precios cargados (la misma que usa el
    pipeline). Para un indicador sin historia la fecha no aplica: solo existe
    el valor vigente, y pedirlo para una fecha pasada sería sesgo de
    anticipación — se devuelve el vigente y se dice en `fecha_efectiva`.
    """
    from app.database import get_session
    from app.models import Asset
    from app.models.indicator_definition import IndicatorDefinition
    from app.models.indicator_store import (CurrentIndicatorValue,
                                            query_values_asof)

    s = get_session()
    d = (s.query(IndicatorDefinition)
         .filter(IndicatorDefinition.code == code).first())
    if d is None:
        raise ValueError(
            f"el indicador '{code}' no existe en esta instalación")

    total_activos = s.query(Asset).count()
    con_historia = bool(d.keep_history)
    fecha = parse_fecha(fecha)

    if con_historia:
        if fecha is None:
            from app.services.group_score_service import get_default_target_date
            fecha = get_default_target_date()
        valores = list(query_values_asof(s, code, fecha).values())
        fecha_efectiva = str(fecha)
    else:
        filas = (s.query(CurrentIndicatorValue.value_num,
                         CurrentIndicatorValue.value_str)
                 .filter(CurrentIndicatorValue.code == code).all())
        valores = [num if num is not None else txt for num, txt in filas]
        fecha_efectiva = "vigente"

    if d.type == "str":
        resumen = resumen_categorico(valores, total_activos)
    else:
        resumen = resumen_numerico(valores, total_activos, escala)

    return {
        "code": d.code,
        "name": d.name,
        "type": d.type,
        "scale": d.scale,
        "keep_history": con_historia,
        "fecha_efectiva": fecha_efectiva,
        "total_activos": total_activos,
        **resumen,
    }
