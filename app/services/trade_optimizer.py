"""
Optimizador de parámetros del simulador de trades (grid search honesto).

Lógica pura (sin BD): recibe los mismos arrays que trade_simulator y la spec
ACTIVA del usuario, y prueba una grilla GRUESA de valores para las
condiciones tildadas — la estructura (qué condiciones participan) no se
toca: la elige el usuario. Devuelve el top-N por retorno total compuesto en
el tramo de ENTRENAMIENTO, con la validación out-of-sample al lado.

Decisiones metodológicas (acordadas con el usuario, 15-jul-2026):
- Objetivo: retorno total compuesto de los trades CERRADOS (producto de
  (1+ret) − 1). El % de ganadores solo es gameable (muchos +1% y un −30%)
  y el retorno medio ignora la frecuencia.
- Filtro duro: mínimo de trades cerrados en train (default 10) — descarta
  configs "ganadoras" por un solo trade afortunado.
- Anti-sobreajuste: grilla gruesa (4-7 valores por parámetro, no barrido
  fino) y validación train/test — se optimiza sobre el primer train_frac
  de las barras y se reporta cómo rindió el top en el tramo restante, que
  el optimizador nunca vio. La columna test es la que separa una config
  robusta de curve-fitting.
- Poda de coherencia: se descartan combos que entran y salen en la barra
  siguiente por construcción (Abs< >= entrada Sc, Abs> <= entrada Sc,
  Percentil< >= entrada Pct).
El sobreajuste residual sigue existiendo (se optimiza UN activo): la
versión robusta es optimizar sobre el universo (fase 2 del backtest).
"""
import copy
from itertools import product

from app.services.trade_simulator import simulate_trades

# Grillas GRUESAS por condición — pocas opciones a propósito (anti-fitting).
GRIDS = {
    ("entries", "score"):          [-20, 0, 10, 20, 30, 40, 60],
    ("entries", "pct"):            [70, 80, 90, 95],
    ("score_exits", "absolute"):       [-40, -20, 0, 10, 20],
    ("score_exits", "absolute_above"): [60, 70, 80, 90],
    ("score_exits", "delta_entry"):    [10, 20, 30, 50],
    ("score_exits", "trailing_score"): [10, 20, 30, 50],
    ("score_exits", "score_ma"):       [5, 10, 20, 40],
    ("score_exits", "percentile"):     [30, 50, 70, 80],
    ("caps", "max_bars"):      [20, 60, 120, 250],
    ("caps", "stop_loss"):     [5, 10, 15, 25],
    ("caps", "trailing_stop"): [10, 15, 25],
    ("caps", "take_profit"):   [10, 20, 40],
    ("cooldown", None):        [0, 5, 10, 20],
}

_PARAM_KEY = {"score_ma": "k", "max_bars": "n"}

MAX_COMBOS = 3000
MIN_TRAIN_BARS = 60
MIN_TEST_BARS = 20

# Etiquetas para describir un combo en la UI (mismos nombres que el panel)
_LABELS = {
    ("entries", "score"): "Score≥", ("entries", "pct"): "Percentil≥",
    ("score_exits", "absolute"): "Abs<",
    ("score_exits", "absolute_above"): "Abs>",
    ("score_exits", "delta_entry"): "Ent−Δ",
    ("score_exits", "trailing_score"): "Máx−Δ",
    ("score_exits", "score_ma"): "Media k",
    ("score_exits", "percentile"): "Percentil<",
    ("caps", "max_bars"): "Ruedas",
    ("caps", "stop_loss"): "SL%",
    ("caps", "trailing_stop"): "TS%",
    ("caps", "take_profit"): "TP%",
}


def build_axes(spec) -> list:
    """Ejes de la grilla: uno por condición ACTIVA con parámetro numérico.
    Cada eje: ((sección, tipo, clave_del_parámetro), [valores])."""
    axes = []
    for e in spec.get("entries") or []:
        axes.append((("entries", e["type"], "th"),
                     GRIDS[("entries", e["type"])]))
    for x in spec.get("score_exits") or []:
        key = _PARAM_KEY.get(x["type"], "x")
        axes.append((("score_exits", x["type"], key),
                     GRIDS[("score_exits", x["type"])]))
    for c in spec.get("caps") or []:
        key = _PARAM_KEY.get(c["type"], "pct")
        axes.append((("caps", c["type"], key), GRIDS[("caps", c["type"])]))
    if spec.get("cooldown"):
        axes.append((("cooldown", None, None), GRIDS[("cooldown", None)]))
    return axes


def _apply_assignment(spec, axes, values) -> dict:
    s = copy.deepcopy(spec)
    for (section, typ, key), val in zip([a[0] for a in axes], values):
        if section == "cooldown":
            s["cooldown"] = val
        else:
            for item in s[section]:
                if item["type"] == typ:
                    item[key] = val
                    break
    return s


def _coherent(s) -> bool:
    """Descarta combos que entran y salen en la barra siguiente por
    construcción (la salida 'pisa' la zona de entrada)."""
    ent = {e["type"]: e["th"] for e in s.get("entries") or []}
    for x in s.get("score_exits") or []:
        if x["type"] == "absolute" and "score" in ent and x["x"] >= ent["score"]:
            return False
        if x["type"] == "absolute_above" and "score" in ent and x["x"] <= ent["score"]:
            return False
        if x["type"] == "percentile" and "pct" in ent and x["x"] >= ent["pct"]:
            return False
    return True


def build_combos(spec, max_combos=MAX_COMBOS) -> list[dict]:
    axes = build_axes(spec)
    if not axes:
        raise ValueError(
            "Ninguna condición activa con parámetros para optimizar — "
            "tildá al menos una condición de entrada.")
    raw = 1
    for _, vals in axes:
        raw *= len(vals)
    if raw > max_combos:
        raise ValueError(
            f"{raw} combinaciones superan el máximo ({max_combos}). "
            "Desactivá alguna condición y volvé a intentar.")
    combos = [_apply_assignment(spec, axes, values)
              for values in product(*[vals for _, vals in axes])]
    return [c for c in combos if _coherent(c)]


def perf_metrics(trades) -> dict:
    """Métricas de los trades CERRADOS: n, % ganadores, retorno medio y
    retorno total compuesto (el objetivo del ranking)."""
    closed = [t for t in trades
              if t["exit_idx"] is not None and t["ret"] is not None]
    n = len(closed)
    if not n:
        return {"n": 0, "win": None, "avg": None, "total": None}
    total = 1.0
    for t in closed:
        total *= (1 + t["ret"])
    rets = [t["ret"] for t in closed]
    return {
        "n": n,
        "win": sum(1 for r in rets if r > 0) / n,
        "avg": sum(rets) / n,
        "total": total - 1,
    }


def describe_spec(spec) -> str:
    """Descripción compacta de un combo para la tabla de resultados."""
    parts = []
    for e in spec.get("entries") or []:
        parts.append(f"{_LABELS[('entries', e['type'])]}{e['th']:g}")
    for x in spec.get("score_exits") or []:
        key = _PARAM_KEY.get(x["type"], "x")
        parts.append(f"{_LABELS[('score_exits', x['type'])]}{x[key]:g}")
    for c in spec.get("caps") or []:
        key = _PARAM_KEY.get(c["type"], "pct")
        parts.append(f"{_LABELS[('caps', c['type'])]} {c[key]:g}")
    if spec.get("rearm"):
        parts.append("Cruce")
    if spec.get("cooldown"):
        parts.append(f"Enfr.{spec['cooldown']}")
    return " · ".join(parts)


def optimize(closes, scores, percentiles, spec, *, min_trades=10,
             train_frac=0.7, top_n=10, max_combos=MAX_COMBOS) -> dict:
    """Grid search sobre la estructura activa de `spec`.

    Rankea por retorno total compuesto en el tramo TRAIN (primer train_frac
    de las barras, mínimo min_trades cerrados) y devuelve el top con la
    validación en el tramo TEST (que el ranking nunca vio; el estado del
    simulador arranca de cero en test — media móvil, armado, etc.).
    """
    n = len(closes)
    split = int(n * train_frac)
    if split < MIN_TRAIN_BARS or n - split < MIN_TEST_BARS:
        raise ValueError(
            f"Historia insuficiente para optimizar ({n} barras con score: "
            f"hacen falta ≥{MIN_TRAIN_BARS} de train y ≥{MIN_TEST_BARS} "
            "de test).")

    pct_train = percentiles[:split] if percentiles is not None else None
    pct_test = percentiles[split:] if percentiles is not None else None

    combos = build_combos(spec, max_combos=max_combos)
    ranked = []
    for c in combos:
        m = perf_metrics(simulate_trades(closes[:split], scores[:split],
                                         c, pct_train))
        if m["n"] < min_trades:
            continue
        ranked.append((c, m))
    ranked.sort(key=lambda r: r[1]["total"], reverse=True)

    results = []
    for c, m_train in ranked[:top_n]:
        m_test = perf_metrics(simulate_trades(closes[split:], scores[split:],
                                              c, pct_test))
        results.append({"spec": c, "label": describe_spec(c),
                        "train": m_train, "test": m_test})
    return {
        "results": results,
        "n_combos": len(combos),
        "n_valid": len(ranked),
        "split_idx": split,
        "min_trades": min_trades,
    }
