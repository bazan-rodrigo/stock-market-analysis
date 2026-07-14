"""
Motor de cómputo del backtest por deciles (nivel A: calidad de la señal).

Lógica pura (sin BD, sin Dash): recibe estructuras en memoria y devuelve
métricas. La orquestación (carga de datos con gate, persistencia, thread)
vive en backtest_service.py.

Metodología (fijada por tests/test_backtest_engine.py):

- **Retorno forward**: la señal se conoce al cierre de la barra i del PROPIO
  activo; se ejecuta al cierre de i+lag (default lag=1, sin look-ahead) y se
  mide hasta el cierre de i+lag+h (h = horizonte en RUEDAS propias, no días
  calendario). Si la serie no alcanza, el retorno es None (la fecha no
  cuenta para ese horizonte).
- **Cuantiles por fecha** (cross-section): en cada fecha, los activos con
  score Y retorno forward válidos se ordenan por score ascendente y se
  parten en n cuantiles por rango: cuantil = floor(rank * n / count) + 1.
  El cuantil n es el de MEJOR score. Empates de score se desempatan por el
  orden de entrada (estable, determinístico).
- **Agregación equal-weight por fecha**: el retorno del cuantil q en la
  fecha D es el promedio simple de sus activos (cartera diaria equal-weight
  rebalanceada). El agregado del run promedia esos retornos diarios (cada
  fecha pesa igual, sin importar cuántos activos tuvo).
- **IC (Information Coefficient)**: correlación de Spearman (ranks con
  empates promediados) entre score en D y retorno forward D→D+h, por fecha.
- **Spread**: retorno del cuantil top − retorno del cuantil bottom, por fecha.
- Una fecha se saltea para un horizonte si tiene menos de
  max(min_assets, n_quantiles) observaciones válidas.
"""

from math import floor, sqrt
from statistics import median


# ── Retornos forward ──────────────────────────────────────────────────────────

def forward_returns_for_series(closes, horizons, lag=1):
    """Retornos forward por barra para UNA serie de closes propia (ordenada).

    Devuelve una lista paralela a `closes`: en la posición i, un dict
    {h: ret | None} — ret = close[i+lag+h] / close[i+lag] − 1.
    """
    n = len(closes)
    out = []
    for i in range(n):
        rets = {}
        j = i + lag
        for h in horizons:
            k = j + h
            if k < n and j < n and closes[j] and closes[j] > 0:
                rets[h] = closes[k] / closes[j] - 1
            else:
                rets[h] = None
        out.append(rets)
    return out


# ── Ranks / Spearman ──────────────────────────────────────────────────────────

def _avg_ranks(values):
    """Ranks 1..n con empates promediados (necesario para un Spearman bien
    definido con scores discretos, donde los empates son la norma)."""
    order = sorted(range(len(values)), key=lambda i: values[i])
    ranks = [0.0] * len(values)
    i = 0
    while i < len(order):
        j = i
        while j + 1 < len(order) and values[order[j + 1]] == values[order[i]]:
            j += 1
        avg = (i + j) / 2 + 1  # promedio de posiciones 1-based
        for k in range(i, j + 1):
            ranks[order[k]] = avg
        i = j + 1
    return ranks


def spearman_ic(scores, rets):
    """Correlación de Spearman entre dos listas paralelas. None si hay menos
    de 3 pares o si alguna serie es constante (varianza cero)."""
    n = len(scores)
    if n < 3 or n != len(rets):
        return None
    rs, rr = _avg_ranks(scores), _avg_ranks(rets)
    mean_s = sum(rs) / n
    mean_r = sum(rr) / n
    cov = var_s = var_r = 0.0
    for a, b in zip(rs, rr):
        da, db = a - mean_s, b - mean_r
        cov += da * db
        var_s += da * da
        var_r += db * db
    if var_s == 0 or var_r == 0:
        return None
    return cov / sqrt(var_s * var_r)


# ── Cross-section de una fecha ────────────────────────────────────────────────

def quantile_index(rank, count, n_quantiles):
    """Cuantil 1..n para el rank 0-based ascendente por score.
    n_quantiles = mejor score."""
    return floor(rank * n_quantiles / count) + 1


def date_cross_section(pairs, n_quantiles=10, min_assets=20):
    """Métricas de UNA fecha para UN horizonte.

    pairs: lista de (score, fwd_ret) ya filtrada (ambos válidos, no None).
    Devuelve {"ic", "spread", "q_means": [m_1..m_n], "n"} o None si la fecha
    no alcanza el mínimo de observaciones.
    """
    n = len(pairs)
    if n < max(min_assets, n_quantiles):
        return None

    order = sorted(range(n), key=lambda i: pairs[i][0])  # ascendente, estable
    q_sums = [0.0] * n_quantiles
    q_counts = [0] * n_quantiles
    for rank, idx in enumerate(order):
        q = quantile_index(rank, n, n_quantiles) - 1
        q_sums[q] += pairs[idx][1]
        q_counts[q] += 1
    q_means = [(q_sums[q] / q_counts[q]) if q_counts[q] else None
               for q in range(n_quantiles)]

    ic = spearman_ic([p[0] for p in pairs], [p[1] for p in pairs])
    spread = (q_means[-1] - q_means[0]
              if q_means[-1] is not None and q_means[0] is not None else None)
    return {"ic": ic, "spread": spread, "q_means": q_means, "n": n}


# ── Agregación del run ────────────────────────────────────────────────────────

def aggregate_cross_sections(sections):
    """Agrega las cross-sections de UN horizonte (lista de dicts de
    date_cross_section, sin los None) en el resumen del run.

    Equal-weight por fecha: media/mediana/% positivo sobre los retornos
    DIARIOS de cada cuantil. IC: media, desvío, % positivo y t-stat
    (media / desvío × √n — significancia aproximada de que el IC medio
    no es ruido).
    """
    if not sections:
        return None
    n_q = len(sections[0]["q_means"])

    quantiles = []
    for q in range(n_q):
        daily = [s["q_means"][q] for s in sections if s["q_means"][q] is not None]
        quantiles.append({
            "quantile":  q + 1,
            "n_dates":   len(daily),
            "mean_ret":  (sum(daily) / len(daily)) if daily else None,
            "median_ret": median(daily) if daily else None,
            "pct_pos":   (sum(1 for r in daily if r > 0) / len(daily)) if daily else None,
        })

    ics = [s["ic"] for s in sections if s["ic"] is not None]
    ic_mean = ic_std = ic_t = None
    if ics:
        ic_mean = sum(ics) / len(ics)
        if len(ics) > 1:
            var = sum((x - ic_mean) ** 2 for x in ics) / (len(ics) - 1)
            ic_std = sqrt(var)
            if ic_std > 0:
                ic_t = ic_mean / ic_std * sqrt(len(ics))

    spreads = [s["spread"] for s in sections if s["spread"] is not None]
    avg_assets = sum(s["n"] for s in sections) / len(sections)

    return {
        "n_dates":     len(sections),
        "avg_assets":  avg_assets,
        "quantiles":   quantiles,
        "ic_mean":     ic_mean,
        "ic_std":      ic_std,
        "ic_t":        ic_t,
        "ic_pct_pos":  (sum(1 for x in ics if x > 0) / len(ics)) if ics else None,
        "spread_mean": (sum(spreads) / len(spreads)) if spreads else None,
    }
