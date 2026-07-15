"""
Simulador de trades sobre la serie de scores de una estrategia para UN activo.

Lógica pura (sin BD): recibe arrays alineados por barra de precio propia del
activo y devuelve la lista de trades que produce la spec. Lo consumen el
overlay de estrategia del gráfico y (a futuro) el módulo de backtesting.

╔══════════════════════════════════════════════════════════════════════════╗
║ REGLA DE HOMOLOGACIÓN (ver CLAUDE.md): este archivo es el CONTRATO de la  ║
║ semántica. La misma máquina de estados está replicada en JavaScript en    ║
║ app/callbacks/chart_callbacks.py (función window._lwc.simulateTrades)    ║
║ para la interactividad del gráfico (sin round-trip). Cualquier cambio de ║
║ semántica acá debe replicarse allá EN EL MISMO COMMIT, y los casos de    ║
║ tests/fixtures/trade_simulator_cases.json deben acompañarlo.             ║
╚══════════════════════════════════════════════════════════════════════════╝

Estructura de la spec (todas las secciones combinables e independientes):

    {
      "entries":     [ {"type": "score"|"pct", "th": N}, ... ],   # AND
      "score_exits": [ {"type": ..., parámetros}, ... ],          # OR
      "caps":        [ {"type": ..., parámetros}, ... ],          # OR
      "rearm":       bool,   # default False
      "cooldown":    int,    # default 0
    }

Asimetría deliberada AND/OR: las condiciones de ENTRADA son filtros — deben
cumplirse TODAS las activas para entrar; las de SALIDA son gatillos — cierra
la PRIMERA que dispare. Sin condiciones de entrada no hay trades; sin
salidas (score ni caps), el trade se mantiene mientras el activo siga siendo
elegible (buy & hold del filtro).

Semántica (fijada por los fixtures — cambiarla es cambiar el contrato):

- `closes[i]` / `scores[i]` / `percentiles[i]`: barra i del PROPIO activo.
  `scores[i] is None` = el activo no fue elegible (no pasó el filtro) en esa
  barra. `percentiles` (0..100, 100 = mejor rankeado del día) solo existen
  en barras con score (derivan de él).
- Entradas ("entries", AND — cada tipo a lo sumo una vez):
  - score {"th"}: score >= th.
  - pct   {"th"}: percentil >= th.
  Solo se evalúan en barras con score; una condición cuyo dato falta cuenta
  como NO cumplida. En la barra de entrada no se evalúa ninguna salida.
- Re-entrada (frenos del whipsaw, opcionales, se exigen ADEMÁS de entries):
  - "rearm": tras una salida queda desarmado; se re-arma en la primera barra
    con score donde la condición de entrada combinada NO se cumple ("la
    señal se reseteó"). Estado inicial: armado.
  - "cooldown": tras la salida en la barra j, la entrada se habilita cuando
    i − j > cooldown (0 = barra siguiente). Cuenta barras propias.
- En posición, por barra, gana el primero que se cumpla (en este orden):
    1. filtro       — barra sin score → cierre forzado (reason "filter").
    2. caps         — salidas por PRECIO/TIEMPO, en el orden de la lista.
    3. score_exits  — salidas por SEÑAL, en el orden de la lista.
  (la UI arma ambas listas en orden canónico; ver abajo)

Salidas por score ("score_exits", cada tipo a lo sumo una vez):
- absolute       {"x"}: score < x (nivel absoluto; útil si las señales son
                  simétricas y 0 significa "se dio vuelta").
- delta_entry    {"x"}: score < score_de_entrada − x.
- trailing_score {"x"}: score < máximo score desde la entrada (incluida la
                  barra actual) − x.
- score_ma       {"k"}: score < media simple de los últimos k scores
                  observados (sobre toda la serie, no desde la entrada;
                  incluye el actual; con menos de k observados no dispara).
- percentile     {"x"}: percentil < x.

Salidas por precio/tiempo ("caps", cada tipo a lo sumo una vez):
- max_bars      {"n"}:   i − entry_idx >= n.
- stop_loss     {"pct"}: close <= entry_close × (1 − pct/100).
- trailing_stop {"pct"}: close <= máximo close desde la entrada (incluida la
                 barra actual) × (1 − pct/100).
- take_profit   {"pct"}: close >= entry_close × (1 + pct/100).
"""

from statistics import median

ENTRY_TYPES = ("score", "pct")
SCORE_EXIT_TYPES = ("absolute", "delta_entry", "trailing_score",
                    "score_ma", "percentile")
CAP_TYPES = ("max_bars", "stop_loss", "trailing_stop", "take_profit")


def simulate_trades(closes, scores, spec, percentiles=None) -> list[dict]:
    """Corre la máquina de estados y devuelve los trades.

    Cada trade: {"entry_idx", "exit_idx" (None=abierto), "entry_close",
    "exit_close" (None=abierto), "ret" (None si entry_close<=0), "reason"
    (tipo de salida, "filter", o None=abierto)}.
    """
    entries     = spec.get("entries") or []
    score_exits = spec.get("score_exits") or []
    caps        = spec.get("caps") or []
    rearm       = bool(spec.get("rearm"))
    cooldown    = int(spec.get("cooldown") or 0)

    for e in entries:
        if e["type"] not in ENTRY_TYPES:
            raise ValueError(f"Condición de entrada desconocida: {e['type']!r}")
    for x in score_exits:
        if x["type"] not in SCORE_EXIT_TYPES:
            raise ValueError(f"Salida por score desconocida: {x['type']!r}")
    for cap in caps:
        if cap["type"] not in CAP_TYPES:
            raise ValueError(f"Tope desconocido: {cap['type']!r}")

    # Última barra con score: más allá no hay veredicto de elegibilidad.
    last_scored = None
    for i in range(len(scores) - 1, -1, -1):
        if scores[i] is not None:
            last_scored = i
            break
    if last_scored is None:
        return []

    def _entry_ok(sc, pc):
        """AND de todas las condiciones activas; dato faltante = no cumple."""
        if not entries:
            return False
        for e in entries:
            v = sc if e["type"] == "score" else pc
            if v is None or v < e["th"]:
                return False
        return True

    trades = []
    in_pos = False
    entry_idx = entry_close = entry_score = None
    max_score = max_close = None
    ma_window = []          # últimos k scores observados (salida score_ma)
    k = next((x["k"] for x in score_exits if x["type"] == "score_ma"), None)
    armed = True            # re-armado por cruce: armado al inicio
    last_exit = None        # barra de la última salida (para el cooldown)

    def _close_trade(i, reason):
        nonlocal in_pos, armed, last_exit
        ret = (closes[i] / entry_close - 1) if entry_close and entry_close > 0 else None
        trades.append({"entry_idx": entry_idx, "exit_idx": i,
                       "entry_close": entry_close, "exit_close": closes[i],
                       "ret": ret, "reason": reason})
        in_pos = False
        armed = False
        last_exit = i

    for i in range(last_scored + 1):
        c  = closes[i]
        sc = scores[i]
        pc = percentiles[i] if percentiles is not None else None

        # Media móvil del score: se acumula sobre toda la serie observada,
        # haya o no posición (es una propiedad de la serie, no del trade).
        ma = None
        if k is not None and sc is not None:
            ma_window.append(sc)
            if len(ma_window) > k:
                ma_window.pop(0)
            if len(ma_window) == k:
                ma = sum(ma_window) / k

        if not in_pos:
            if sc is None:
                continue  # sin score no hay evaluación de entrada ni armado
            if not _entry_ok(sc, pc):
                armed = True  # la señal se reseteó: re-arma el cruce
            elif ((not rearm or armed)
                    and (last_exit is None or i - last_exit > cooldown)):
                in_pos = True
                entry_idx, entry_close = i, c
                entry_score, max_score, max_close = sc, sc, c
            continue  # en la barra de entrada no se evalúan salidas

        # 1) Elegibilidad: barra propia sin score → cierre forzado.
        if sc is None:
            _close_trade(i, "filter")
            continue

        # Máximos INCLUYENDO la barra actual (contrato de trailing_*).
        if max_score is None or sc > max_score:
            max_score = sc
        if c > max_close:
            max_close = c

        # 2) Salidas por precio/tiempo (orden de la lista; gana la primera).
        reason = None
        for cap in caps:
            ct = cap["type"]
            if ct == "max_bars" and i - entry_idx >= cap["n"]:
                reason = "max_bars"
            elif (ct == "stop_loss" and entry_close > 0
                    and c <= entry_close * (1 - cap["pct"] / 100)):
                reason = "stop_loss"
            elif (ct == "trailing_stop" and max_close > 0
                    and c <= max_close * (1 - cap["pct"] / 100)):
                reason = "trailing_stop"
            elif (ct == "take_profit" and entry_close > 0
                    and c >= entry_close * (1 + cap["pct"] / 100)):
                reason = "take_profit"
            if reason:
                break

        # 3) Salidas por score (orden de la lista; gana la primera).
        if reason is None:
            for x in score_exits:
                t = x["type"]
                if t == "absolute" and sc < x["x"]:
                    reason = t
                elif t == "delta_entry" and sc < entry_score - x["x"]:
                    reason = t
                elif t == "trailing_score" and sc < max_score - x["x"]:
                    reason = t
                elif t == "score_ma" and ma is not None and sc < ma:
                    reason = t
                elif t == "percentile" and pc is not None and pc < x["x"]:
                    reason = t
                if reason:
                    break

        if reason:
            _close_trade(i, reason)

    if in_pos:
        ret = (closes[-1] / entry_close - 1) if entry_close and entry_close > 0 else None
        trades.append({"entry_idx": entry_idx, "exit_idx": None,
                       "entry_close": entry_close, "exit_close": None,
                       "ret": ret, "reason": None})
    return trades


def summarize_trades(trades) -> dict:
    """Métricas agregadas para el label del gráfico / reporte de backtest."""
    closed = [t for t in trades if t["exit_idx"] is not None]
    rets   = [t["ret"] for t in closed if t["ret"] is not None]
    open_t = next((t for t in trades if t["exit_idx"] is None), None)
    return {
        "n_trades": len(trades),
        "n_closed": len(closed),
        "win_rate": (sum(1 for r in rets if r > 0) / len(rets)) if rets else None,
        "avg_ret":    (sum(rets) / len(rets)) if rets else None,
        "median_ret": median(rets) if rets else None,
        "min_ret":    min(rets) if rets else None,
        "max_ret":    max(rets) if rets else None,
        "avg_bars": (sum(t["exit_idx"] - t["entry_idx"] for t in closed)
                     / len(closed)) if closed else None,
        "n_filter": sum(1 for t in closed if t["reason"] == "filter"),
        "open_ret": open_t["ret"] if open_t else None,
    }
