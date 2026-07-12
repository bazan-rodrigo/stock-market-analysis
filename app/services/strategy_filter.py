"""
Filtro de elegibilidad de estrategias: árbol de condiciones AND/OR que se
evalúa antes del scoring — el activo que no cumple no aparece en
strategy_result.

Esquema del árbol (Strategy.filter_conditions, JSON):

  grupo:  {"op": "AND"|"OR", "children": [nodo, ...]}
  hoja:   {"cond": {"left": <operando>, "operator": <op>, "right": <operando>,
                    "resolution": "historic"|"current"}}

  operando:
    {"type": "indicator", "key": "rsi_daily"}     valor del indicador
    {"type": "signal",    "key": "rsi_low"}       score de la señal (signal.key)
    {"type": "attribute", "key": "sector"}        atributo del activo (FK id)
    {"type": "const",     "value": 70 | "bullish" | [1, 4]}

  operadores: = != > >= < <=   (numéricos)
              = != in not_in   (categóricos / atributos)

Semántica:
  - Todo se evalúa contra target_date: indicadores desde ind_* con lookup
    as-of (última fila <= target_date, tope de antigüedad — los indicadores
    semanales/mensuales se guardan con fechas de fin de período, no
    diarias), señales desde signal_value con fecha exacta (misma semántica
    que el scoring). resolution="current" (opt-in por condición)
    lee CurrentIndicatorValue — el valor vigente para CUALQUIER fecha, o sea
    sesgo de anticipación deliberado (diagnóstico in-sample de indicadores
    full-sample tipo best_sma; ver uses_current_resolution y el badge en la
    UI de cálculo).
  - Dato faltante = condición no cumplida. Un filtro que deja pasar activos
    que no pudo evaluar sería una trampa silenciosa.
  - Tipos incompatibles (num vs str) = condición falsa (y error al validar).

Este módulo es puro en la evaluación (evaluate_tree no toca la DB); la carga
batch de operandos (load_operand_values) hace una query por operando
distinto, nunca por activo.
"""
import json
import logging
from datetime import timedelta

import sqlalchemy as sa

logger = logging.getLogger(__name__)

# Lookup "as-of" de indicadores: máxima antigüedad aceptada del último valor.
# Los indicadores semanales/mensuales se guardan con fechas de fin de período
# (el resample etiqueta las semanas en domingo), así que una fecha diaria
# arbitraria no tiene fila exacta — se usa la última fila <= target_date.
# El tope evita levantar valores zombie de activos que dejaron de cotizar
# (45 días cubre etiquetas mensuales + feriados largos).
_ASOF_MAX_LOOKBACK_DAYS = 45

GROUP_OPS = frozenset({"AND", "OR"})

NUMERIC_OPERATORS     = frozenset({"=", "!=", ">", ">=", "<", "<="})
CATEGORICAL_OPERATORS = frozenset({"=", "!=", "in", "not_in"})
ALL_OPERATORS         = NUMERIC_OPERATORS | CATEGORICAL_OPERATORS

OPERAND_TYPES = frozenset({"indicator", "signal", "attribute", "const"})

# Atributos de Asset filtrables — mismos cinco que resuelve
# compute_strategy_results para los scopes de grupo (asset_groups).
ATTRIBUTE_KEYS = frozenset({
    "sector", "market", "industry", "country", "instrument_type",
})

RESOLUTIONS = frozenset({"historic", "current"})


# ── Parseo ────────────────────────────────────────────────────────────────────

def parse_tree(filter_conditions: str | None) -> dict | None:
    """None si no hay filtro (o el JSON es inválido — se loguea y se trata
    como sin filtro para no tumbar el cálculo entero; la validación al
    guardar impide llegar acá con un árbol roto)."""
    if not filter_conditions:
        return None
    try:
        tree = json.loads(filter_conditions)
    except (json.JSONDecodeError, TypeError):
        logger.error("strategy_filter: filter_conditions inválido: %r",
                     filter_conditions[:200])
        return None
    return tree or None


# ── Recolección de operandos ──────────────────────────────────────────────────

def collect_operands(tree: dict) -> set[tuple]:
    """Set de (type, key, resolution) de todos los operandos no-const del
    árbol. resolution solo distingue para type=indicator ("" para el resto)."""
    found: set[tuple] = set()

    def _walk(node: dict) -> None:
        if "cond" in node:
            cond = node["cond"]
            resolution = cond.get("resolution") or "historic"
            for side in (cond.get("left"), cond.get("right")):
                if not isinstance(side, dict):
                    continue
                t = side.get("type")
                if t == "indicator":
                    found.add((t, side.get("key"), resolution))
                elif t in ("signal", "attribute"):
                    found.add((t, side.get("key"), ""))
            return
        for child in node.get("children", []):
            _walk(child)

    _walk(tree)
    return found


def uses_current_resolution(tree: dict | None) -> bool:
    """True si alguna condición lee el valor vigente (resolution=current):
    para target_date pasadas eso es sesgo de anticipación deliberado y los
    resultados deben marcarse como diagnóstico in-sample."""
    if not tree:
        return False
    return any(res == "current" for t, _, res in collect_operands(tree)
               if t == "indicator")


# ── Carga batch de valores ────────────────────────────────────────────────────

def load_operand_values(session, tree: dict, target_date) -> dict[tuple, dict]:
    """Carga los valores de todos los operandos del árbol para target_date.

    Devuelve {(type, key, resolution): {asset_id: valor}}. Los atributos no
    se cargan acá: ya vienen resueltos en asset_groups (ver evaluate_tree).
    Una query por operando distinto — nunca por activo.
    """
    from app.models import SignalDefinition, SignalValue
    from app.models.indicator_store import CurrentIndicatorValue, get_ind_table

    values: dict[tuple, dict] = {}
    operands = collect_operands(tree)

    signal_keys = {key for t, key, _ in operands if t == "signal"}
    sig_ids_by_key = {}
    if signal_keys:
        sig_ids_by_key = {
            r.key: r.id
            for r in session.query(SignalDefinition.key, SignalDefinition.id)
            .filter(SignalDefinition.key.in_(signal_keys)).all()
        }

    for t, key, resolution in operands:
        if t == "indicator" and resolution == "current":
            rows = session.query(
                CurrentIndicatorValue.asset_id,
                CurrentIndicatorValue.value_num,
                CurrentIndicatorValue.value_str,
            ).filter(CurrentIndicatorValue.code == key).all()
            values[(t, key, resolution)] = {
                aid: (num if num is not None else s)
                for aid, num, s in rows
                if num is not None or s is not None
            }
        elif t == "indicator":
            try:
                tbl = get_ind_table(key)
            except sa.exc.NoSuchTableError:
                logger.warning("strategy_filter: tabla ind_%s no existe", key)
                values[(t, key, resolution)] = {}
                continue
            # As-of: última fila <= target_date por activo (con tope de
            # antigüedad). Los indicadores semanales/mensuales no tienen
            # fila en fechas diarias arbitrarias — un match exacto dejaría
            # el filtro vacío casi siempre (ver _ASOF_MAX_LOOKBACK_DAYS).
            cutoff = target_date - timedelta(days=_ASOF_MAX_LOOKBACK_DAYS)
            latest = (
                sa.select(tbl.c.asset_id,
                          sa.func.max(tbl.c.date).label("mx"))
                .where(tbl.c.date <= target_date, tbl.c.date >= cutoff)
                .group_by(tbl.c.asset_id)
                .subquery()
            )
            rows = session.execute(
                sa.select(tbl.c.asset_id, tbl.c.value)
                .select_from(tbl.join(
                    latest,
                    sa.and_(tbl.c.asset_id == latest.c.asset_id,
                            tbl.c.date == latest.c.mx),
                ))
            ).fetchall()
            values[(t, key, resolution)] = {
                aid: v for aid, v in rows if v is not None
            }
        elif t == "signal":
            sig_id = sig_ids_by_key.get(key)
            if sig_id is None:
                logger.warning("strategy_filter: señal '%s' no encontrada", key)
                values[(t, key, resolution)] = {}
                continue
            rows = session.query(SignalValue.asset_id, SignalValue.score).filter(
                SignalValue.signal_id == sig_id,
                SignalValue.date == target_date,
            ).all()
            values[(t, key, resolution)] = {aid: score for aid, score in rows}

    return values


# ── Evaluación ────────────────────────────────────────────────────────────────

def _resolve(side: dict, asset_id: int, resolution: str,
             operand_values: dict[tuple, dict], attributes: dict):
    t = side.get("type")
    if t == "const":
        return side.get("value")
    if t == "attribute":
        return attributes.get(side.get("key"))
    if t == "indicator":
        return operand_values.get((t, side.get("key"), resolution), {}).get(asset_id)
    if t == "signal":
        return operand_values.get((t, side.get("key"), ""), {}).get(asset_id)
    return None


def _as_number(value):
    """float o None si el valor no es numérico. bool queda excluido a
    propósito (no hay indicadores booleanos)."""
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return float(value)
    return None


def _compare(left, right, operator: str) -> bool:
    if left is None or right is None:
        return False

    if operator in ("in", "not_in"):
        if not isinstance(right, (list, tuple, set)):
            return False
        # str(x) a ambos lados: los atributos guardan ids (int) pero la UI
        # puede persistir la lista como strings — y viceversa.
        member = str(left) in {str(v) for v in right}
        return member if operator == "in" else not member

    ln, rn = _as_number(left), _as_number(right)
    if ln is not None and rn is not None:
        if operator == "=":
            return ln == rn
        if operator == "!=":
            return ln != rn
        if operator == ">":
            return ln > rn
        if operator == ">=":
            return ln >= rn
        if operator == "<":
            return ln < rn
        if operator == "<=":
            return ln <= rn
        return False

    # Al menos un lado no numérico → solo igualdad/desigualdad de strings
    if operator == "=":
        return str(left) == str(right)
    if operator == "!=":
        return str(left) != str(right)
    return False


def evaluate_tree(tree: dict, asset_id: int,
                  operand_values: dict[tuple, dict], attributes: dict) -> bool:
    """attributes: {"sector": id, "market": id, ...} del activo (el dict de
    asset_groups que compute_strategy_results ya arma)."""
    if "cond" in tree:
        cond = tree["cond"]
        resolution = cond.get("resolution") or "historic"
        left  = _resolve(cond.get("left", {}),  asset_id, resolution,
                         operand_values, attributes)
        right = _resolve(cond.get("right", {}), asset_id, resolution,
                         operand_values, attributes)
        return _compare(left, right, cond.get("operator", ""))

    op = tree.get("op")
    children = tree.get("children", [])
    if not children:
        # Grupo vacío: no filtra nada (la validación lo rechaza al guardar,
        # pero un árbol legacy/editado a mano no debe excluir todo en silencio)
        return True
    results = (evaluate_tree(c, asset_id, operand_values, attributes)
               for c in children)
    return any(results) if op == "OR" else all(results)


# ── Detección de operandos sin historia ──────────────────────────────────────
#
# Un indicador keep_history=False no tiene tabla ind_* — a fecha pasada solo
# existe su valor vigente. La UI usa esto para avisar ("sesgo de
# anticipación") y fijar resolution=current en la condición.

def non_history_indicator_codes(session) -> set[str]:
    from app.models.indicator_definition import IndicatorDefinition
    return {
        d.code for d in session.query(IndicatorDefinition.code).filter(
            IndicatorDefinition.keep_history.is_(False)
        ).all()
    }


def non_history_signal_keys(session) -> set[str]:
    """Keys de señales cuya cadena de indicadores incluye alguno sin
    historia (composites resueltas recursivamente).

    Nota: el score de una señal se historiza en signal_value aunque el
    indicador subyacente no tenga historia — para fechas en que la señal ya
    corría, el filtro usa esa foto. El aviso es porque NO se puede
    reconstruir el score de fechas anteriores a la creación de la señal."""
    import json
    from app.models import SignalDefinition

    no_hist = non_history_indicator_codes(session)
    signals = session.query(
        SignalDefinition.key, SignalDefinition.indicator_key,
        SignalDefinition.formula_type, SignalDefinition.params,
    ).all()

    direct: set[str] = set()
    composite_refs: dict[str, set[str]] = {}
    for key, ind_key, ftype, params in signals:
        if ftype == "composite":
            try:
                comps = json.loads(params).get("components", [])
            except (json.JSONDecodeError, TypeError):
                comps = []
            composite_refs[key] = {
                c.get("signal_key") for c in comps if c.get("signal_key")
            }
        elif ind_key in no_hist:
            direct.add(key)

    # Propagar por las composites hasta el punto fijo
    tainted = set(direct)
    changed = True
    while changed:
        changed = False
        for key, refs in composite_refs.items():
            if key not in tainted and refs & tainted:
                tainted.add(key)
                changed = True
    return tainted


# ── Compatibilidad: asset_filter legacy → árbol ──────────────────────────────

_LEGACY_ATTR_BY_COLUMN = {
    "sector_id":          "sector",
    "market_id":          "market",
    "industry_id":        "industry",
    "country_id":         "country",
    "instrument_type_id": "instrument_type",
}


def legacy_asset_filter_to_tree(asset_filter: str | None) -> str | None:
    """Convierte el formato viejo de asset_filter ({"sector_id": 3, ...}) a un
    árbol equivalente. Misma conversión que la migración 0061 — acá para que
    los Excel exportados antes del cambio sigan importando."""
    if not asset_filter:
        return None
    try:
        flt = json.loads(asset_filter) or {}
    except (json.JSONDecodeError, TypeError):
        return None
    children = [
        {"cond": {
            "left":     {"type": "attribute", "key": attr},
            "operator": "=",
            "right":    {"type": "const", "value": flt[col]},
        }}
        for col, attr in _LEGACY_ATTR_BY_COLUMN.items()
        if flt.get(col) is not None
    ]
    if not children:
        return None
    return json.dumps({"op": "AND", "children": children})


# ── Validación (al guardar) ───────────────────────────────────────────────────

def validate_tree(tree, *, indicator_codes: dict[str, str],
                  signal_keys: set[str],
                  categorical_values: dict[str, frozenset]) -> list[str]:
    """Lista de errores (vacía si el árbol es válido).

    indicator_codes: {code: type} con type 'num'|'str' (IndicatorDefinition).
    categorical_values: catálogo code → valores posibles (indicator_catalog).
    """
    errors: list[str] = []

    def _operand_kind(side, path: str) -> str | None:
        """'num' | 'str' | None (desconocido/inválido)."""
        if not isinstance(side, dict):
            errors.append(f"{path}: operando inválido")
            return None
        t = side.get("type")
        if t not in OPERAND_TYPES:
            errors.append(f"{path}: tipo de operando desconocido: {t!r}")
            return None
        if t == "const":
            v = side.get("value")
            if v is None:
                errors.append(f"{path}: constante sin valor")
                return None
            if isinstance(v, (list, tuple)):
                return "list"
            return "num" if _as_number(v) is not None else "str"
        key = side.get("key")
        if not key:
            errors.append(f"{path}: operando sin key")
            return None
        if t == "indicator":
            if key not in indicator_codes:
                errors.append(f"{path}: indicador desconocido: {key!r}")
                return None
            return indicator_codes[key]
        if t == "signal":
            if key not in signal_keys:
                errors.append(f"{path}: señal desconocida: {key!r}")
                return None
            return "num"  # los scores son numéricos
        if t == "attribute":
            if key not in ATTRIBUTE_KEYS:
                errors.append(f"{path}: atributo desconocido: {key!r}")
                return None
            return "str"  # ids: comparables solo por igualdad/pertenencia

    def _walk(node, path: str) -> None:
        if not isinstance(node, dict):
            errors.append(f"{path}: nodo inválido (se esperaba objeto)")
            return

        if "cond" in node:
            cond = node["cond"]
            if not isinstance(cond, dict):
                errors.append(f"{path}: condición inválida")
                return
            operator = cond.get("operator")
            if operator not in ALL_OPERATORS:
                errors.append(f"{path}: operador desconocido: {operator!r}")
                return
            resolution = cond.get("resolution") or "historic"
            if resolution not in RESOLUTIONS:
                errors.append(f"{path}: resolution desconocida: {resolution!r}")

            lkind = _operand_kind(cond.get("left"),  f"{path}.left")
            rkind = _operand_kind(cond.get("right"), f"{path}.right")
            if lkind is None or rkind is None:
                return

            left, right = cond.get("left", {}), cond.get("right", {})
            if left.get("type") == "const":
                errors.append(f"{path}: el operando izquierdo no puede ser constante")
            if operator in ("in", "not_in"):
                if right.get("type") != "const" or rkind != "list":
                    errors.append(
                        f"{path}: {operator} requiere una lista de valores a la derecha")
            elif rkind == "list":
                errors.append(f"{path}: una lista solo se admite con in/not_in")
            elif operator not in ("=", "!="):
                # Operadores ordenados: ambos lados numéricos
                if lkind != "num" or rkind != "num":
                    errors.append(
                        f"{path}: {operator!r} requiere operandos numéricos "
                        f"({lkind} vs {rkind})")
            elif lkind != rkind and "num" in (lkind, rkind):
                errors.append(f"{path}: tipos incompatibles ({lkind} vs {rkind})")

            # Valores discretos dentro del catálogo
            if left.get("type") == "indicator" and right.get("type") == "const":
                allowed = categorical_values.get(left.get("key"))
                if allowed:
                    vals = right.get("value")
                    vals = vals if isinstance(vals, (list, tuple)) else [vals]
                    unknown = [v for v in vals if str(v) not in allowed]
                    if unknown:
                        errors.append(
                            f"{path}: valores fuera del catálogo de "
                            f"{left.get('key')}: {unknown!r}")
            return

        op = node.get("op")
        if op not in GROUP_OPS:
            errors.append(f"{path}: op de grupo desconocido: {op!r}")
            return
        children = node.get("children")
        if not isinstance(children, list) or not children:
            errors.append(f"{path}: grupo sin condiciones")
            return
        for i, child in enumerate(children):
            _walk(child, f"{path}.{i}")

    _walk(tree, "filtro")
    return errors
