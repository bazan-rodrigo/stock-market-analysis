"""
Simulador de trades sobre la serie de scores de una estrategia para UN activo.

Lógica pura (sin BD): recibe arrays alineados por barra de precio propia del
activo y devuelve la lista de trades que produce la spec de entrada/salida.
Lo consumen el overlay de estrategia del gráfico y (a futuro) el módulo de
backtesting.

╔══════════════════════════════════════════════════════════════════════════╗
║ REGLA DE HOMOLOGACIÓN (ver CLAUDE.md): este archivo es el CONTRATO de la  ║
║ semántica. La misma máquina de estados está replicada en JavaScript en    ║
║ app/callbacks/chart_callbacks.py (función window._lwc.simulateTrades)    ║
║ para la interactividad del gráfico (sliders sin round-trip). Cualquier   ║
║ cambio de semántica acá debe replicarse allá EN EL MISMO COMMIT, y los   ║
║ casos de tests/fixtures/trade_simulator_cases.json deben acompañarlo.    ║
╚══════════════════════════════════════════════════════════════════════════╝

Taxonomía: el MODO sale por SEÑAL (score/percentil), los TOPES salen por
PRECIO o TIEMPO, y el filtro de elegibilidad cierra siempre. El modo es
opcional (None) y los topes combinables (lista, cada tipo a lo sumo una
vez); sin modo ni topes, el trade se mantiene mientras el activo siga
siendo elegible (buy & hold del filtro).

Semántica (fijada por los fixtures — cambiarla es cambiar el contrato):

- `closes[i]` / `scores[i]` / `percentiles[i]`: barra i del PROPIO activo.
  `scores[i] is None` = el activo no fue elegible (no pasó el filtro) en esa
  barra. `percentiles` (0..100, 100 = mejor rankeado) solo se usa en el modo
  "percentile".
- Entrada: sin posición, la barra tiene señal de entrada y señal >=
  spec["entry"] → entra al close de esa barra. La señal de entrada es el
  score, o el PERCENTIL si spec["entry_pct"] es True (default False) —
  independiente del modo de salida (se puede entrar por percentil y salir
  por trailing de score, o entrar por score y salir por percentil).
  Los percentiles solo existen en barras con score (derivan de él).
  En la barra de entrada NO se evalúa ninguna salida.
- Re-entrada (control del whipsaw tras una salida), dos frenos opcionales
  e independientes que se exigen ADEMÁS de señal >= entry:
  - spec["rearm"] (bool, default False) — re-entrada por CRUCE: tras una
    salida el sistema queda desarmado; se re-arma recién cuando una barra
    sin posición muestra señal < entry (la señal "se reseteó"). El estado
    inicial es armado (una serie que arranca sobre el umbral entra).
    El armado usa la MISMA señal que la entrada (percentil si entry_pct,
    score si no) y solo se evalúa en barras con señal.
  - spec["cooldown"] (int >= 0, default 0) — enfriamiento: tras una salida
    en la barra j, la entrada se permite recién cuando i − j > cooldown
    (0 = barra siguiente, comportamiento sin freno). Cuenta barras propias,
    tengan o no score.
- En posición, por barra, gana el primero que se cumpla (en este orden):
    1. filtro   — barra sin score → cierre forzado (reason "filter").
    2. topes    — spec["caps"], None o LISTA de topes (max_bars / stop_loss /
                  trailing_stop / take_profit), evaluados EN EL ORDEN DE LA
                  LISTA: si varios se cumplen en la misma barra, el reason es
                  el primero de la lista (la UI los arma en orden canónico:
                  max_bars, stop_loss, trailing_stop, take_profit).
    3. modo     — spec["mode"], None ("sin salida por score") o UNO:
                  absolute / delta_entry / trailing_score / score_ma /
                  percentile.
- Cola sin score: las barras DESPUÉS de la última barra con score no cierran
  por filtro (típico: el precio de hoy ya bajó pero las señales aún no
  corrieron — "no sabemos si es elegible" no es "dejó de ser elegible").
  El trade queda abierto y su retorno se mide contra el último close real.
- Trade abierto al final: exit_idx/exit_close None, reason None, ret contra
  closes[-1].

Modos (spec["mode"] = None | {"type": ..., parámetros}):
- absolute       {"x"}: score < x (nivel absoluto; útil si las señales son
                  simétricas y 0 significa "se dio vuelta").
- delta_entry    {"x"}: score < score_de_entrada − x.
- trailing_score {"x"}: score < máximo score desde la entrada (incluida la
                  barra actual) − x.
- score_ma       {"k"}: score < media simple de los últimos k scores
                  observados (sobre toda la serie, no desde la entrada;
                  incluye el actual; con menos de k observados no dispara).
- percentile     {"x"}: percentil < x (100 = mejor rankeado del día). La
                  entrada NO cambia con este modo — eso lo decide
                  spec["entry_pct"].

El horizonte fijo ("salir a las N ruedas") NO es un modo: es tiempo, no
señal — se expresa como tope max_bars (antes existía duplicado como modo
"horizon"; se eliminó al volverse opcional el modo).

Topes (spec["caps"] = None | [{"type": ..., parámetros}, ...]):
- max_bars      {"n"}:   i − entry_idx >= n.
- stop_loss     {"pct"}: close <= entry_close × (1 − pct/100).
- trailing_stop {"pct"}: close <= máximo close desde la entrada (incluida la
                 barra actual) × (1 − pct/100).
- take_profit   {"pct"}: close >= entry_close × (1 + pct/100).
"""

from statistics import median

EXIT_MODES = ("absolute", "delta_entry", "trailing_score",
              "score_ma", "percentile")
CAP_TYPES = ("max_bars", "stop_loss", "trailing_stop", "take_profit")


def simulate_trades(closes, scores, spec, percentiles=None) -> list[dict]:
    """Corre la máquina de estados y devuelve los trades.

    Cada trade: {"entry_idx", "exit_idx" (None=abierto), "entry_close",
    "exit_close" (None=abierto), "ret" (None si entry_close<=0), "reason"
    (tipo de modo/tope, "filter", o None=abierto)}.
    """
    mode  = spec.get("mode") or None
    mtype = mode["type"] if mode else None
    caps  = spec.get("caps") or []
    entry_th  = spec["entry"]
    entry_pct = bool(spec.get("entry_pct"))
    rearm     = bool(spec.get("rearm"))
    cooldown  = int(spec.get("cooldown") or 0)

    if mtype is not None and mtype not in EXIT_MODES:
        raise ValueError(f"Modo de salida desconocido: {mtype!r}")
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

    trades = []
    in_pos = False
    entry_idx = entry_close = entry_score = None
    max_score = max_close = None
    ma_window = []          # últimos k scores observados (modo score_ma)
    k = mode.get("k") if mode else None
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
        if mtype == "score_ma" and sc is not None:
            ma_window.append(sc)
            if len(ma_window) > k:
                ma_window.pop(0)
            if len(ma_window) == k:
                ma = sum(ma_window) / k

        if not in_pos:
            sig = pc if entry_pct else sc
            if sig is not None:
                if sig < entry_th:
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

        # 2) Topes (en el orden de la lista; gana el primero que se cumpla).
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

        # 3) Modo principal (None = sin salida por score).
        if reason is None and mtype is not None:
            if mtype == "absolute" and sc < mode["x"]:
                reason = "absolute"
            elif mtype == "delta_entry" and sc < entry_score - mode["x"]:
                reason = "delta_entry"
            elif mtype == "trailing_score" and sc < max_score - mode["x"]:
                reason = "trailing_score"
            elif mtype == "score_ma" and ma is not None and sc < ma:
                reason = "score_ma"
            elif mtype == "percentile" and pc is not None and pc < mode["x"]:
                reason = "percentile"

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
