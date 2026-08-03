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
import json
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
    d, total_activos = _definicion(code)
    por_activo, fecha_efectiva = _leer_valores(d, fecha)
    valores = list(por_activo.values())

    if d.type == "str":
        resumen = resumen_categorico(valores, total_activos)
    else:
        resumen = resumen_numerico(valores, total_activos, escala)

    return {
        "code": d.code,
        "name": d.name,
        "type": d.type,
        "scale": d.scale,
        "keep_history": bool(d.keep_history),
        "fecha_efectiva": fecha_efectiva,
        "total_activos": total_activos,
        **resumen,
    }


# ══════════════════════════════════════════════════════════════════════════════
# Lectura compartida
# ══════════════════════════════════════════════════════════════════════════════

def _definicion(code: str):
    """(IndicatorDefinition, total de activos) o ValueError si no existe."""
    from app.database import get_session
    from app.models import Asset
    from app.models.indicator_definition import IndicatorDefinition

    s = get_session()
    d = (s.query(IndicatorDefinition)
         .filter(IndicatorDefinition.code == code).first())
    if d is None:
        raise ValueError(f"el indicador '{code}' no existe en esta instalación")
    return d, s.query(Asset).count()


def _leer_valores(d, fecha) -> tuple[dict, str]:
    """{asset_id: valor} + la fecha que se terminó usando.

    Un indicador sin historia solo tiene valor vigente: pedirlo para una fecha
    pasada sería sesgo de anticipación, así que se devuelve el vigente y se
    dice en la fecha efectiva en vez de fingir que se leyó esa fecha.
    """
    from app.database import get_session
    from app.models.indicator_store import (CurrentIndicatorValue,
                                            query_values_asof)

    s = get_session()
    fecha = parse_fecha(fecha)
    if bool(d.keep_history):
        if fecha is None:
            from app.services.group_score_service import get_default_target_date
            fecha = get_default_target_date()
        return query_values_asof(s, d.code, fecha), str(fecha)

    filas = (s.query(CurrentIndicatorValue.asset_id,
                     CurrentIndicatorValue.value_num,
                     CurrentIndicatorValue.value_str)
             .filter(CurrentIndicatorValue.code == d.code).all())
    return ({aid: (num if num is not None else txt)
             for aid, num, txt in filas if (num is not None or txt is not None)},
            "vigente")


# ══════════════════════════════════════════════════════════════════════════════
# Histograma y distribución del puntaje (lógica pura)
# ══════════════════════════════════════════════════════════════════════════════

BINS_DEFAULT = 40

# Recorte por defecto del histograma, en percentiles. Sin esto un solo activo
# extremo (se midió un volumen relativo de 162 contra una mediana de 1) estira
# el eje y aplasta toda la masa en la primera barra: el gráfico queda vacío y
# parece que no hay datos.
RECORTE_DEFAULT = (1, 99)


def histograma(valores, bins: int = BINS_DEFAULT, recorte=RECORTE_DEFAULT) -> dict:
    """Conteo por intervalo, con las colas recortadas SOLO para el dibujo.

    Devuelve los bordes, los conteos y cuántos quedaron fuera del recorte a
    cada lado — que se informan, no se esconden: son los activos que un `clamp`
    va a saturar.
    """
    limpios = [float(v) for v in valores
               if isinstance(v, (int, float)) and np.isfinite(float(v))]
    if not limpios:
        return {"bins": [], "conteos": [], "fuera_izq": 0, "fuera_der": 0}

    arr = np.asarray(limpios, dtype=float)
    lo, hi = (float(np.percentile(arr, recorte[0])),
              float(np.percentile(arr, recorte[1]))) if recorte else (arr.min(), arr.max())
    if lo == hi:                      # todos iguales: un solo intervalo
        lo, hi = lo - 0.5, hi + 0.5
    dentro = arr[(arr >= lo) & (arr <= hi)]
    conteos, bordes = np.histogram(dentro, bins=bins, range=(lo, hi))
    return {
        "bins": [round(float(b), 6) for b in bordes],
        "conteos": [int(c) for c in conteos],
        "fuera_izq": int(np.count_nonzero(arr < lo)),
        "fuera_der": int(np.count_nonzero(arr > hi)),
    }


def resumen_de_scores(valores, formula_type: str, params) -> dict:
    """Distribución del PUNTAJE que la señal produciría con esos valores.

    Es la vista más directa de todo esto: la saturación se ve como dos picos en
    ±100 y los empates de un `threshold` como columnas. Un porcentaje hay que
    interpretarlo; esto se mira.

    `sin_puntaje` es la otra mitad de la historia: un valor que la fórmula no
    puntúa (una categoría fuera del mapa) no vale cero, deja al activo sin ese
    componente y le renormaliza los pesos a favor.
    """
    from app.services import signal_engine

    texto = params if isinstance(params, str) else json.dumps(params or {})
    scores, sin_puntaje = [], 0
    for v in valores:
        try:
            s = signal_engine.evaluate(formula_type, texto, v)
        except Exception:
            s = None
        if s is None:
            sin_puntaje += 1
        else:
            scores.append(float(s))

    n = len(scores)
    if n == 0:
        return {"n": 0, "sin_puntaje": sin_puntaje,
                "nota": "la fórmula no puntúa en ningún activo"}
    arr = np.asarray(scores, dtype=float)
    return {
        "n": n,
        "sin_puntaje": sin_puntaje,
        "media": round(float(arr.mean()), 2),
        "mediana": round(float(np.median(arr)), 2),
        "pct_en_tope": round(float(np.count_nonzero(arr >= 99.999)) / n * 100, 2),
        "pct_en_piso": round(float(np.count_nonzero(arr <= -99.999)) / n * 100, 2),
        # Recorrido del cuartil central: cuánto score le queda a la mitad del
        # universo. Ojo que solo NO alcanza — una escala tan angosta que todos
        # saturan da un recorrido enorme (de −100 a +100) y ordena pésimo. Se
        # lee junto con los dos topes.
        "recorrido_iqr": round(float(np.percentile(arr, 75)
                                     - np.percentile(arr, 25)), 1),
        # Puntajes DISTINTOS sobre el total: la medida directa de los empates.
        # Un `threshold` de cinco tramos da 5 valores para todo el universo, o
        # sea que el ranking transversal queda con cinco bloques y adentro de
        # cada uno el orden lo decide el desempate, no la señal. No se ve en la
        # saturación ni en el recorrido: hace falta contarlo.
        "puntajes_distintos": len(set(scores)),
        "pct_distintos": round(len(set(scores)) / n * 100, 2),
        "histograma": histograma(scores, bins=41, recorte=None),
    }


# ══════════════════════════════════════════════════════════════════════════════
# El análisis completo (pantalla de calibración)
# ══════════════════════════════════════════════════════════════════════════════

def _grupos_por_activo(atributo: str) -> tuple[dict, str]:
    """({asset_id: nombre del grupo}, etiqueta del atributo).

    Reusa las MISMAS fuentes que el filtro de estrategias: la query de
    atributos y el índice id→nombre del catálogo de packs. Si se armara acá una
    consulta propia, un activo podría caer en un grupo distinto del que le
    asigna el filtro y los dos números no se podrían comparar.
    """
    from app.database import get_session
    from app.services import pack_service
    from app.services import strategy_filter as sf

    if atributo not in sf.ATTRIBUTE_KEYS:
        raise ValueError(f"atributo desconocido: {atributo!r}. "
                         f"Disponibles: {', '.join(sorted(sf.ATTRIBUTE_KEYS))}")

    s = get_session()
    nombres = {valor: nombre
               for valor, nombre in pack_service.attribute_pairs(s)[atributo]}
    salida = {}
    for fila in sf.asset_attributes_query(s).all():
        valor = sf.attributes_from_asset_row(fila)[atributo]
        salida[fila.id] = nombres.get(valor, str(valor))
    return salida, atributo


def analisis_indicador(code: str, fechas=None, escala=None, por=None,
                       formula_type=None, params=None,
                       bins: int = BINS_DEFAULT) -> dict:
    """Todo lo que hace falta para calibrar una señal, en una sola lectura.

    - `fechas`: una o varias. Varias es el punto: los indicadores que se
      reinician con el calendario (retorno del mes, del trimestre, del año)
      ensanchan su dispersión a lo largo del período, así que una escala que
      recorta el 10% a mitad de camino puede recortar el 30% al final. Con una
      sola fecha ese defecto es invisible.
    - `escala`: una escala `range` tentativa; se informa cuánto recortaría en
      CADA fecha.
    - `por`: atributo de agrupación (tipo de instrumento, sector, …). El ATR%
      de una cripto y el de una utility no viven en la misma escala, y un rango
      único puede estar bien para una e inservible para la otra.
    - `formula_type`/`params`: la fórmula de la señal, para devolver además la
      distribución del PUNTAJE resultante.
    """
    d, total_activos = _definicion(code)
    fechas = list(fechas) if fechas else [None]

    por_fecha = []
    primera_valores: dict = {}
    for i, f in enumerate(fechas):
        por_activo, efectiva = _leer_valores(d, f)
        if i == 0:
            primera_valores = por_activo
        valores = list(por_activo.values())
        resumen = (resumen_categorico(valores, total_activos) if d.type == "str"
                   else resumen_numerico(valores, total_activos, escala))
        por_fecha.append({"fecha_efectiva": efectiva, **resumen})

    salida = {
        "code": d.code,
        "name": d.name,
        "type": d.type,
        "scale": d.scale,
        "description": d.description,
        "keep_history": bool(d.keep_history),
        "total_activos": total_activos,
        "fechas": por_fecha,
    }

    if d.type != "str":
        salida["histograma"] = histograma(list(primera_valores.values()), bins)

    if formula_type:
        salida["scores"] = resumen_de_scores(
            list(primera_valores.values()), formula_type, params)

    if por:
        grupos, _ = _grupos_por_activo(por)
        por_grupo: dict = {}
        for aid, valor in primera_valores.items():
            por_grupo.setdefault(grupos.get(aid, "—"), []).append(valor)
        # Cuántos activos tiene cada grupo EN TOTAL (no solo los que tienen
        # dato): sin eso la cobertura por grupo daría siempre 100% y se
        # perdería justo lo que interesa — qué grupo no tiene el indicador.
        tamaño: dict = {}
        for g in grupos.values():
            tamaño[g] = tamaño.get(g, 0) + 1
        filas = []
        for g, vals in por_grupo.items():
            resumen = (resumen_categorico(vals, tamaño.get(g, len(vals)))
                       if d.type == "str"
                       else resumen_numerico(vals, tamaño.get(g, len(vals)), escala))
            filas.append({"grupo": g, "activos": tamaño.get(g, len(vals)),
                          **resumen})
        salida["grupos"] = sorted(filas, key=lambda r: -r["n"])
        salida["agrupado_por"] = por

    return salida
