"""
Métricas de performance de cartera (nivel C del backtest y módulo de Carteras).

Lógica pura (sin BD, sin Dash): recibe series en memoria y devuelve métricas.
Sirve por igual al Backtest (simulación de cartera) y a las carteras reales y
teóricas — cambia sólo la fuente de la serie (histórica simulada / forward /
real). La orquestación (carga de datos, costos, persistencia) vive en los
servicios que la consumen.

Entradas típicas:
  - `equity`: lista de floats con el valor de la cartera en el tiempo (base
    arbitraria: 100, capital real, etc. — las métricas son escala-invariante).
  - `returns`: lista de retornos período-a-período.
  - `trades`: lista de dicts con al menos 'ret' y 'reason', en el formato que
    devuelve trade_simulator.simulate_trades (ret=None y reason=None = abierto).

Convención del proyecto (igual que backtest_engine.spearman_ic): una métrica
NO computable devuelve None — nunca inf ni NaN. Los costos (comisiones/bps) se
aplican aguas arriba (en el servicio que arma la serie o los trades), no acá.
"""

from math import sqrt
from statistics import mean, median, stdev

TRADING_DAYS = 252  # ruedas por año (anualización por defecto)


# ── Retornos y equity ─────────────────────────────────────────────────────────

def returns_from_equity(equity):
    """Retornos período-a-período: r[i] = equity[i]/equity[i-1] − 1.

    Devuelve una lista de longitud len(equity)−1. Un denominador 0/None da None
    en esa posición (no rompe el resto de la serie).
    """
    out = []
    for i in range(1, len(equity)):
        prev = equity[i - 1]
        cur = equity[i]
        if prev is None or cur is None or prev == 0:
            out.append(None)
        else:
            out.append(cur / prev - 1)
    return out


def equity_from_returns(returns, base=100.0):
    """Curva de equity compuesta a partir de retornos por período (base inicial)."""
    eq = [float(base)]
    for r in returns:
        eq.append(eq[-1] * (1 + (r or 0.0)))
    return eq


def _clean(xs):
    """Descarta None de una lista (para métricas que los ignoran)."""
    return [x for x in xs if x is not None]


# ── Riesgo / retorno ──────────────────────────────────────────────────────────

def total_return(equity):
    """Retorno total de la serie: equity[-1]/equity[0] − 1. None si no computa."""
    if len(equity) < 2 or not equity[0] or equity[-1] is None:
        return None
    return equity[-1] / equity[0] - 1


def cagr(equity, years):
    """Retorno anualizado compuesto dado el # de años (calendario).

    None si la serie no computa, years es None o years <= 0.
    """
    tr = total_return(equity)
    if tr is None or years is None or years <= 0 or (1 + tr) <= 0:
        return None
    return (1 + tr) ** (1.0 / years) - 1


def annualized_volatility(returns, periods_per_year=TRADING_DAYS):
    """Desvío de los retornos, anualizado (√periods_per_year). None si <2 datos."""
    rs = _clean(returns)
    if len(rs) < 2:
        return None
    return stdev(rs) * sqrt(periods_per_year)


def sharpe(returns, risk_free=0.0, periods_per_year=TRADING_DAYS):
    """Sharpe anualizado. risk_free es tasa ANUAL. None si <2 datos o desvío 0."""
    rs = _clean(returns)
    if len(rs) < 2:
        return None
    rf_p = risk_free / periods_per_year
    excess = [r - rf_p for r in rs]
    sd = stdev(excess)
    if sd == 0:
        return None
    return (mean(excess) / sd) * sqrt(periods_per_year)


def sortino(returns, risk_free=0.0, periods_per_year=TRADING_DAYS):
    """Sortino anualizado: usa el desvío a la baja (downside deviation).

    La downside deviation es √(Σ min(excess,0)² / N) sobre TODOS los períodos
    (no sólo los negativos). None si <2 datos, sin períodos negativos, o dd 0.
    """
    rs = _clean(returns)
    if len(rs) < 2:
        return None
    rf_p = risk_free / periods_per_year
    excess = [r - rf_p for r in rs]
    downside = [e for e in excess if e < 0]
    if not downside:
        return None
    dd = sqrt(sum(e * e for e in downside) / len(excess))
    if dd == 0:
        return None
    return (mean(excess) / dd) * sqrt(periods_per_year)


# ── Drawdown ──────────────────────────────────────────────────────────────────

def drawdown_series(equity):
    """Serie underwater: en cada punto, valor/pico_hasta_ahora − 1 (<= 0)."""
    out = []
    peak = None
    for v in equity:
        if peak is None or v > peak:
            peak = v
        out.append(v / peak - 1 if peak and peak > 0 else 0.0)
    return out


def max_drawdown(equity):
    """Máximo drawdown y sus índices.

    Devuelve dict {mdd, peak_idx, trough_idx, recovery_idx} o None si <2 puntos.
    - mdd: el drawdown más negativo (<= 0).
    - peak_idx: índice del pico previo al valle.
    - trough_idx: índice del valle (mdd).
    - recovery_idx: primer índice tras el valle que recupera el pico (o None si
      no se recuperó dentro de la serie).
    """
    if len(equity) < 2:
        return None
    dd = drawdown_series(equity)
    trough_idx = min(range(len(dd)), key=lambda i: dd[i])
    peak_idx = max(range(trough_idx + 1), key=lambda i: equity[i])
    peak_val = equity[peak_idx]
    recovery_idx = None
    for i in range(trough_idx + 1, len(equity)):
        if equity[i] >= peak_val:
            recovery_idx = i
            break
    return {
        "mdd": dd[trough_idx],
        "peak_idx": peak_idx,
        "trough_idx": trough_idx,
        "recovery_idx": recovery_idx,
    }


# ── Métricas de trades ────────────────────────────────────────────────────────
# `rets` = lista de retornos de trades CERRADOS (floats). Ver exit_reason_breakdown
# para trabajar sobre la lista de dicts cruda de simulate_trades.

def win_rate(rets):
    """Fracción de trades con retorno > 0. None si no hay trades."""
    r = _clean(rets)
    if not r:
        return None
    return sum(1 for x in r if x > 0) / len(r)


def profit_factor(rets):
    """Ganancia bruta / pérdida bruta. None si no hay pérdidas (indefinido)."""
    r = _clean(rets)
    gains = sum(x for x in r if x > 0)
    losses = -sum(x for x in r if x < 0)
    if losses == 0:
        return None
    return gains / losses


def expectancy(rets):
    """Retorno medio por trade. None si no hay trades."""
    r = _clean(rets)
    if not r:
        return None
    return mean(r)


def payoff_ratio(rets):
    """Ganancia media / pérdida media (en magnitud). None si falta alguna cola."""
    r = _clean(rets)
    wins = [x for x in r if x > 0]
    losses = [-x for x in r if x < 0]
    if not wins or not losses:
        return None
    return mean(wins) / mean(losses)


def exit_reason_breakdown(trades):
    """Desglose de trades CERRADOS por motivo de salida.

    Devuelve dict {reason: {'count': n, 'mean_ret': r, 'total_ret': suma}}
    preservando el orden de aparición. Ignora trades abiertos (ret/reason None).
    """
    agg = {}
    order = []
    for t in trades:
        ret = t.get("ret")
        reason = t.get("reason")
        if ret is None or reason is None:
            continue
        if reason not in agg:
            agg[reason] = {"count": 0, "total_ret": 0.0}
            order.append(reason)
        agg[reason]["count"] += 1
        agg[reason]["total_ret"] += ret
    out = {}
    for reason in order:
        a = agg[reason]
        out[reason] = {
            "count": a["count"],
            "mean_ret": a["total_ret"] / a["count"],
            "total_ret": a["total_ret"],
        }
    return out


# ── Series y exposición ───────────────────────────────────────────────────────

def exposure(trades, total_bars, last_idx=None):
    """Tiempo en mercado: barras en posición / barras totales.

    Usa entry_idx/exit_idx de cada trade. Para trades abiertos (exit_idx None)
    cuenta hasta last_idx si se provee. None si total_bars <= 0.
    """
    if not total_bars or total_bars <= 0:
        return None
    bars = 0
    for t in trades:
        ei = t.get("entry_idx")
        if ei is None:
            continue
        xi = t.get("exit_idx")
        end = xi if xi is not None else (last_idx if last_idx is not None else ei)
        bars += max(0, end - ei)
    return bars / total_bars


def turnover(weight_snapshots):
    """Turnover promedio por rebalanceo (one-way: 0.5·Σ|Δw|).

    `weight_snapshots`: lista de dicts {asset: peso} en cada rebalanceo. None si
    hay menos de 2 snapshots.
    """
    if len(weight_snapshots) < 2:
        return None
    tos = []
    for i in range(1, len(weight_snapshots)):
        prev, cur = weight_snapshots[i - 1], weight_snapshots[i]
        keys = set(prev) | set(cur)
        tos.append(0.5 * sum(abs(cur.get(k, 0.0) - prev.get(k, 0.0)) for k in keys))
    return mean(tos)


def monthly_return_matrix(dates, equity):
    """Matriz de retornos mensuales compuestos.

    `dates`: lista de date/datetime paralela a `equity`. Devuelve un dict
    {año: {mes: retorno}} (retornos compuestos dentro del mes), ordenado. None
    si las longitudes no coinciden o hay <2 puntos.
    """
    if len(dates) != len(equity) or len(equity) < 2:
        return None
    rets = returns_from_equity(equity)  # alineado a dates[1:]
    factors = {}
    for i, r in enumerate(rets):
        if r is None:
            continue
        d = dates[i + 1]
        key = (d.year, d.month)
        factors[key] = factors.get(key, 1.0) * (1 + r)
    matrix = {}
    for (y, m), f in sorted(factors.items()):
        matrix.setdefault(y, {})[m] = f - 1
    return matrix


# ── Resumen ───────────────────────────────────────────────────────────────────

def summary(equity, dates=None, trades=None, periods_per_year=TRADING_DAYS,
            risk_free=0.0):
    """Diccionario con las métricas principales de una cartera.

    Pensado para alimentar los tiles/tablas de la UI y la persistencia. Cada
    métrica es None si no computa. Si se pasan `dates` (paralelas a equity) se
    calculan CAGR (por años calendario) y la matriz mensual; si se pasan
    `trades` se agregan las métricas de operaciones.
    """
    rets = returns_from_equity(equity)
    years = None
    if dates and len(dates) == len(equity) and len(dates) >= 2:
        days = (dates[-1] - dates[0]).days
        years = days / 365.25 if days > 0 else None
    mdd = max_drawdown(equity)
    out = {
        "total_return": total_return(equity),
        "cagr": cagr(equity, years),
        "volatility": annualized_volatility(rets, periods_per_year),
        "sharpe": sharpe(rets, risk_free, periods_per_year),
        "sortino": sortino(rets, risk_free, periods_per_year),
        "max_drawdown": mdd["mdd"] if mdd else None,
    }
    if dates and len(dates) == len(equity):
        out["monthly_returns"] = monthly_return_matrix(dates, equity)
    if trades is not None:
        closed = [t["ret"] for t in trades if t.get("ret") is not None]
        out.update({
            "n_trades": len(trades),
            "n_closed": len(closed),
            "win_rate": win_rate(closed),
            "profit_factor": profit_factor(closed),
            "expectancy": expectancy(closed),
            "payoff_ratio": payoff_ratio(closed),
            "exit_reasons": exit_reason_breakdown(trades),
        })
    return out
