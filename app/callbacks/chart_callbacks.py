"""
Callbacks del grafico tecnico.

Arquitectura:
  - Python: solo obtiene raw_daily al cambiar el activo (sin indicadores).
  - JS: calcula TODOS los indicadores en el browser (sin round-trip al server).

Flujo:
  1. Cambiar activo → Python → chart-data (raw_daily + asset_id)
  2. chart-data change → clientside _JS_RENDER → render completo
  3. Cambiar params/toggles → clientside _JS_IND_UPDATE → recalcula y renderiza
  4. Cambiar tipo/freq/escala/volumen → clientside individuales
"""
from dash import Input, Output, State, callback, clientside_callback, no_update, html


from app.services.asset_service import get_assets
from app.services.price_service import get_prices_df
import app.services.event_service as event_svc
import app.services.sr_service as sr_svc


# ─── Configuración de slots ───────────────────────────────────────────────────
# {nombre: (n_slots, [(param_name, defaults_por_slot)])}
_SLOTS = {
    "sma":        (3, [("period",   [20, 50, 200])]),
    "ema":        (3, [("period",   [9,  21,  50])]),
    "bollinger":  (1, [("period",   [20]), ("std_dev", [2.0])]),
    "rsi":        (1, [("period",   [14])]),
    "macd":       (1, [("fast",     [12]), ("slow",    [26]), ("signal", [9])]),
    "stochastic": (1, [("k_period", [14]), ("d_period", [3])]),
    "atr":        (1, [("period",   [14])]),
    "drawdown":   (1, []),
}
_COLLAPSIBLE = {"sma", "ema", "bollinger", "rsi", "macd", "stochastic", "atr"}  # tienen params div

# Genera listas de IDs y args JS en orden canónico
# Orden: para cada ind, para cada slot: enabled, luego params
def _canonical():
    for name, (n_slots, params) in _SLOTS.items():
        for slot in range(1, n_slots + 1):
            yield ("enabled", name, slot, None, None)
            for pname, defaults in params:
                d = defaults[slot - 1] if slot <= len(defaults) else defaults[-1]
                yield ("param",  name, slot, pname, d)

_CANONICAL = list(_canonical())

def _js_arg(entry):
    kind, name, slot, pname, _ = entry
    if kind == "enabled":
        return f"ind_{name}_{slot}_en"
    return f"ind_{name}_{slot}_{pname}"

_JS_ARGS = [_js_arg(e) for e in _CANONICAL]
_JS_ARGS_STR = ", ".join(_JS_ARGS)

def _state_list(cls=State):
    result = []
    for kind, name, slot, pname, _ in _CANONICAL:
        if kind == "enabled":
            result.append(cls(f"chart-ind-{name}-{slot}-enabled", "value"))
        else:
            result.append(cls(f"chart-ind-{name}-{slot}-{pname}", "value"))
    return result


def _js_ind_params():
    """Genera el literal JS del objeto indParams a partir de los args."""
    lines = []
    for name, (n_slots, params) in _SLOTS.items():
        slots_js = []
        for slot in range(1, n_slots + 1):
            en = f"ind_{name}_{slot}_en"
            fields = f"enabled: !!({en}&&{en}.length)"
            for pname, _ in params:
                fields += f", {pname}: ind_{name}_{slot}_{pname}"
            slots_js.append("{" + fields + "}")
        lines.append(f"    {name}: [{', '.join(slots_js)}]")
    return "{\n" + ",\n".join(lines) + "\n  }"


def _t(d):
    return str(d)[:10]


# ─── Carga de activos ─────────────────────────────────────────────────────────
@callback(
    Output("analysis-asset-select", "options"),
    Input("analysis-asset-select", "id"),
)
def load_chart_assets(_):
    from app.services.verification_service import get_flagged_asset_ids
    assets = get_assets()
    flags  = get_flagged_asset_ids()
    return [{"label": f"{'⚠️ ' if a.id in flags else ''}{a.ticker} - {a.name or a.ticker}",
             "value": a.id} for a in assets]


@callback(
    Output("analysis-asset-select", "value"),
    Input("url", "search"),
)
def preselect_asset_from_url(search):
    if not search:
        return no_update
    from urllib.parse import parse_qs
    params = parse_qs(search.lstrip("?"))
    asset_ids = params.get("asset_id", [])
    if not asset_ids:
        return no_update
    try:
        return int(asset_ids[0])
    except (ValueError, TypeError):
        return no_update


# ─── Mostrar/ocultar params colapsables ───────────────────────────────────────
for _name, _slot in [(e[1], e[2]) for e in _CANONICAL if e[0] == "enabled" and e[1] in _COLLAPSIBLE]:
    @callback(
        Output(f"chart-ind-{_name}-{_slot}-params", "style"),
        Input(f"chart-ind-{_name}-{_slot}-enabled", "value"),
    )
    def _toggle_params(enabled):
        return {"display": "flex"} if enabled else {"display": "none"}


# ─── Python: solo carga raw_daily al cambiar el activo ────────────────────────
@callback(
    Output("chart-data", "data"),
    Output("chart-load-output", "children"),
    Input("analysis-asset-select", "value"),
    State("chart-data", "data"),
    prevent_initial_call=True,
)
def load_chart_data(asset_id, current_data):
    if not asset_id:
        return no_update, no_update
    if current_data and current_data.get("asset_id") == int(asset_id):
        return no_update, no_update

    df = get_prices_df(int(asset_id))
    if df.empty:
        return no_update, no_update

    raw_daily = [
        {"time": _t(row.date), "open": row.open, "high": row.high,
         "low": row.low,  "close": row.close, "volume": float(row.volume or 0)}
        for row in df.itertuples(index=False)
    ]

    import sqlalchemy as sa
    from app.database import get_session
    from app.models import Asset, RegimeConfig
    from app.models.indicator_store import get_ind_table, CurrentIndicatorValue

    db = get_session()
    asset = db.query(Asset).filter(Asset.id == int(asset_id)).first()
    country_id = asset.country_id if asset else None
    events = event_svc.get_events_for_asset(int(asset_id), country_id)

    regime_cfg = db.query(RegimeConfig).filter(RegimeConfig.id == 1).first()
    regime_ema_periods = {
        "D": regime_cfg.ema_period_d if regime_cfg else 200,
        "W": regime_cfg.ema_period_w if regime_cfg else 50,
        "M": regime_cfg.ema_period_m if regime_cfg else 20,
    }

    # Leer estado actual de régimen/volatilidad desde tablas ind_*
    _str_codes = {
        "trend_daily":       ("regime_current", "D"),
        "trend_weekly":      ("regime_current", "W"),
        "trend_monthly":     ("regime_current", "M"),
        "volatility_daily":  ("vol_current",    "D"),
        "volatility_weekly": ("vol_current",     "W"),
        "volatility_monthly":("vol_current",     "M"),
    }

    regime_current: dict = {}
    vol_current: dict = {}
    best_ma: dict = {"D": {}, "W": {}, "M": {}}

    aid = int(asset_id)
    for code, (group, key) in _str_codes.items():
        try:
            t   = get_ind_table(code)
            row = db.execute(
                sa.select(t.c.value)
                .where(t.c.asset_id == aid)
                .order_by(t.c.date.desc())
                .limit(1)
            ).fetchone()
            if row is not None:
                if group == "regime_current":
                    regime_current[key] = row[0]
                else:
                    vol_current[key] = row[0]
        except Exception:
            pass

    # best_ma desde current_indicator_values
    _bm_map = {
        "best_sma_d": ("D", "sma"), "best_ema_d": ("D", "ema"),
        "best_sma_w": ("W", "sma"), "best_ema_w": ("W", "ema"),
        "best_sma_m": ("M", "sma"), "best_ema_m": ("M", "ema"),
    }
    bm_rows = db.query(CurrentIndicatorValue.code, CurrentIndicatorValue.value_num).filter(
        CurrentIndicatorValue.asset_id == aid,
        CurrentIndicatorValue.code.in_(list(_bm_map.keys())),
    ).all()
    for code, val_num in bm_rows:
        if val_num is not None:
            tf, ma_type = _bm_map[code]
            best_ma[tf][ma_type] = int(val_num)

    sr_data = sr_svc.compute_sr_for_asset(int(asset_id)) or {}

    # Config P&F: la caja se resuelve server-side (puede depender del ATR del activo)
    from app.services import pnf_service
    try:
        _pnf_cfg = pnf_service.get_pnf_config()
        pnf = {"box": pnf_service.compute_box_size(df, _pnf_cfg),
               "reversal": int(_pnf_cfg.reversal), "source": _pnf_cfg.source}
    except Exception:
        pnf = None

    return {"raw_daily": raw_daily, "asset_id": int(asset_id), "events": events,
            "best_ma": best_ma,
            "regime_current": regime_current,
            "regime_ema_periods": regime_ema_periods,
            "vol_current": vol_current,
            "pnf": pnf,
            "sr_pivots": sr_data.get("sr_pivots")}, ""


# ─── Callbacks lazy: calculan overlays solo cuando el toggle se activa ────────

@callback(
    Output("chart-regime-data", "data"),
    Input("chart-regime-enabled", "value"),
    Input("analysis-asset-select", "value"),
    prevent_initial_call=True,
)
def load_regime_overlay(enabled, asset_id):
    if not enabled or not asset_id:
        return no_update
    from app.services.price_service import get_prices_df as _gpdf
    from app.services.technical_service import get_regime_zones_for_chart
    df = _gpdf(int(asset_id))
    if df.empty:
        return no_update
    return get_regime_zones_for_chart(df)


@callback(
    Output("chart-vol-data", "data"),
    Input("chart-vol-enabled", "value"),
    Input("analysis-asset-select", "value"),
    prevent_initial_call=True,
)
def load_vol_overlay(enabled, asset_id):
    if not enabled or not asset_id:
        return no_update
    from app.services.price_service import get_prices_df as _gpdf
    from app.services.technical_service import get_vol_zones_for_chart
    df = _gpdf(int(asset_id))
    if df.empty:
        return no_update
    return get_vol_zones_for_chart(df)


@callback(
    Output("chart-dd-data", "data"),
    Input("chart-dd-enabled", "value"),
    Input("analysis-asset-select", "value"),
    prevent_initial_call=True,
)
def load_dd_overlay(enabled, asset_id):
    if not enabled or not asset_id:
        return no_update
    from app.services.price_service import get_prices_df as _gpdf
    from app.services.technical_service import get_dd_events_for_chart
    df = _gpdf(int(asset_id))
    if df.empty:
        return no_update
    return get_dd_events_for_chart(df)


# ─── Overlay de estrategia: entradas/salidas por umbral de score ──────────────

@callback(
    Output("chart-strategy-sel", "options"),
    Input("chart-strategy-sel", "id"),
)
def load_strategy_opts(_):
    from app.services.strategy_service import get_visible_strategies
    from app.services.visibility import current_viewer
    strategies = get_visible_strategies(*current_viewer())
    return [{"label": s.name, "value": s.id} for s in strategies]


@callback(
    Output("chart-strategy-params", "style"),
    Output("chart-strategy-result", "style"),
    Input("chart-strategy-enabled", "value"),
)
def toggle_strategy_params(enabled):
    if enabled:
        return {"display": "flex"}, {"display": "block"}
    return {"display": "none"}, {"display": "none"}


@callback(
    Output("chart-strategy-data", "data"),
    Input("chart-strategy-enabled", "value"),
    Input("chart-strategy-sel", "value"),
    Input("analysis-asset-select", "value"),
    prevent_initial_call=True,
)
def load_strategy_overlay(enabled, strategy_id, asset_id):
    """Historial de score de la estrategia para este activo. Los umbrales
    de entrada/salida se aplican en el browser (los sliders no vuelven a
    consultar la base)."""
    if not enabled or not strategy_id or not asset_id:
        return no_update
    from app.models import StrategyResult
    from app.services.strategy_service import get_strategy_by_id
    from app.services.visibility import can_view, current_viewer

    strat = get_strategy_by_id(int(strategy_id))
    user_id, is_admin = current_viewer()
    if strat is None or not can_view(strat.owner_id, strat.is_public,
                                     user_id, is_admin):
        return no_update

    from app.database import get_session
    db = get_session()
    # score y pct (percentil 0..100 en la cross-section, precalculado por el
    # pipeline — migración 0071) salen de la misma query indexada. pct puede
    # ser NULL en historia previa a la migración: el modo percentil del
    # simulador simplemente no ve esas fechas hasta un "Recalcular completo".
    rows = (db.query(StrategyResult.date, StrategyResult.score,
                     StrategyResult.pct)
            .filter(StrategyResult.strategy_id == int(strategy_id),
                    StrategyResult.asset_id == int(asset_id))
            .order_by(StrategyResult.date).all())

    return {
        "asset_id":    int(asset_id),
        "strategy_id": int(strategy_id),
        "name":        strat.name,
        "scores":      [[_t(d), float(sc)] for d, sc, _ in rows if sc is not None],
        "percentiles": [[_t(d), float(p)] for d, _, p in rows if p is not None],
    }


# Controles del simulador, en el ORDEN POSICIONAL de window._lwc.buildSpec
# (los tres lugares — esta lista, la firma de buildSpec y los dos callbacks
# clientside que lo llaman — deben mantenerse sincronizados).
_SIM_CONTROL_IDS = [
    "chart-strategy-entry-sc-on", "chart-strategy-entry-sc",
    "chart-strategy-entry-pct-on", "chart-strategy-entry-pct",
    "chart-strategy-xs-abs-on", "chart-strategy-xs-abs",
    "chart-strategy-xs-absup-on", "chart-strategy-xs-absup",
    "chart-strategy-xs-dent-on", "chart-strategy-xs-dent",
    "chart-strategy-xs-dmax-on", "chart-strategy-xs-dmax",
    "chart-strategy-xs-mak-on", "chart-strategy-xs-mak",
    "chart-strategy-xs-pct-on", "chart-strategy-xs-pct",
    "chart-strategy-cap-bars-on", "chart-strategy-cap-bars",
    "chart-strategy-cap-sl-on", "chart-strategy-cap-sl",
    "chart-strategy-cap-ts-on", "chart-strategy-cap-ts",
    "chart-strategy-cap-tp-on", "chart-strategy-cap-tp",
    "chart-strategy-rearm",
    "chart-strategy-cooldown-on", "chart-strategy-cooldown",
]


def _sim_control_deps(cls):
    """Inputs/States de los controles del simulador, en orden posicional."""
    return [cls(i, "value") for i in _SIM_CONTROL_IDS]


@callback(
    Output("chart-strategy-xs-abs",   "max"),
    Output("chart-strategy-xs-abs",   "value"),
    Output("chart-strategy-xs-absup", "min"),
    Output("chart-strategy-xs-absup", "value"),
    Output("chart-strategy-xs-pct",   "max"),
    Output("chart-strategy-xs-pct",   "value"),
    Input("chart-strategy-entry-sc-on",  "value"),
    Input("chart-strategy-entry-sc",     "value"),
    Input("chart-strategy-entry-pct-on", "value"),
    Input("chart-strategy-entry-pct",    "value"),
    State("chart-strategy-xs-abs",   "value"),
    State("chart-strategy-xs-absup", "value"),
    State("chart-strategy-xs-pct",   "value"),
    prevent_initial_call=True,
)
def couple_score_exits_to_entries(sc_on, sc_val, pct_on, pct_val,
                                  abs_val, absup_val, xpct_val):
    """Acople con la entrada cuando comparten unidad (evita configs que
    entran y salen en la barra siguiente): Abs< y Pct< topeados por su
    entrada (salida por debilidad DEBAJO de la entrada); Abs> con PISO en
    la entrada (salida por fortaleza ENCIMA de la entrada). Entrada
    inactiva → rango default."""
    def clamp_upper(on, entry_v, exit_v):
        if on and len(on) and entry_v is not None:
            new_v = exit_v if (exit_v is None or exit_v <= entry_v) else entry_v
            return entry_v, (no_update if new_v == exit_v else new_v)
        return 100, no_update

    def clamp_lower(on, entry_v, exit_v):
        if on and len(on) and entry_v is not None:
            new_v = exit_v if (exit_v is None or exit_v >= entry_v) else entry_v
            return entry_v, (no_update if new_v == exit_v else new_v)
        return -100, no_update

    mx1, v1 = clamp_upper(sc_on, sc_val, abs_val)
    mn2, v2 = clamp_lower(sc_on, sc_val, absup_val)
    mx3, v3 = clamp_upper(pct_on, pct_val, xpct_val)
    return mx1, v1, mn2, v2, mx3, v3


_CAP_INPUT_STYLE = {"width": "58px", "fontSize": "0.72rem",
                    "padding": "1px 4px", "height": "22px"}


# Controles con input de valor (todos los checkbox+valor del simulador):
# el input solo se ve con el control activo.
_SIM_TOGGLE_KEYS = [
    "entry-sc", "entry-pct",
    "xs-abs", "xs-absup", "xs-dent", "xs-dmax", "xs-mak", "xs-pct",
    "cap-bars", "cap-sl", "cap-ts", "cap-tp", "cooldown",
]


@callback(
    *[Output(f"chart-strategy-{k}", "style") for k in _SIM_TOGGLE_KEYS],
    *[Input(f"chart-strategy-{k}-on", "value") for k in _SIM_TOGGLE_KEYS],
    prevent_initial_call=True,
)
def toggle_sim_inputs(*ons):
    def style(on):
        return _CAP_INPUT_STYLE if (on and len(on)) else \
            {**_CAP_INPUT_STYLE, "display": "none"}
    return tuple(style(on) for on in ons)


# ─── JS compartido ───────────────────────────────────────────────────────────
_JS_RENDER = f"""
function(chartData, chartType, freq, logScale, volumeEnabled, eventsEnabled, regimeEnabled, ddEnabled, volEnabled, srPivotEnabled, strategyEnabled, entScOn, entSc, entPctOn, entPct, xsAbsOn, xsAbs, xsAbsUpOn, xsAbsUp, xsDentOn, xsDent, xsDmaxOn, xsDmax, xsMakOn, xsMak, xsPctOn, xsPct, capBarsOn, capBars, capSlOn, capSl, capTsOn, capTs, capTpOn, capTp, rearmOn, coolOn, cool, strategyData, {_JS_ARGS_STR}) {{

  if (!window._lwc) {{ window._lwc = {{}}; }}

  /* ── Indicadores: cálculo en el browser ── */

  window._lwc.sma = function(arr, n) {{
    var r = [], sum = 0;
    for (var i = 0; i < arr.length; i++) {{
      sum += arr[i]; if (i >= n) sum -= arr[i - n];
      r.push(i >= n - 1 ? sum / n : NaN);
    }}
    return r;
  }};

  window._lwc.ema = function(arr, n) {{
    var r = [], a = 2 / (n + 1), prev = NaN;
    for (var i = 0; i < arr.length; i++) {{
      prev = isNaN(prev) ? arr[i] : a * arr[i] + (1 - a) * prev;
      r.push(prev);
    }}
    return r;
  }};

  window._lwc.emaW = function(arr, n) {{
    /* Wilder: warmup SMA luego alpha=1/n */
    var r = new Array(arr.length).fill(NaN);
    var sum = 0;
    for (var i = 0; i < n; i++) sum += arr[i];
    r[n - 1] = sum / n;
    var a = 1 / n;
    for (var i = n; i < arr.length; i++)
      r[i] = a * arr[i] + (1 - a) * r[i - 1];
    return r;
  }};

  window._lwc.bollinger = function(close, n, std) {{
    var sma = window._lwc.sma(close, n);
    var upper = [], mid = [], lower = [];
    for (var i = 0; i < close.length; i++) {{
      if (i < n - 1) {{ upper.push(NaN); mid.push(NaN); lower.push(NaN); continue; }}
      var s2 = 0;
      for (var j = i - n + 1; j <= i; j++) s2 += (close[j] - sma[i]) * (close[j] - sma[i]);
      var sd = Math.sqrt(s2 / n);
      upper.push(sma[i] + std * sd); mid.push(sma[i]); lower.push(sma[i] - std * sd);
    }}
    return {{upper: upper, mid: mid, lower: lower}};
  }};

  window._lwc.rsi = function(close, n) {{
    var g = [0], l = [0];
    for (var i = 1; i < close.length; i++) {{
      var d = close[i] - close[i-1];
      g.push(d > 0 ? d : 0); l.push(d < 0 ? -d : 0);
    }}
    var ag = window._lwc.emaW(g, n), al = window._lwc.emaW(l, n);
    return ag.map(function(gv, i) {{
      if (isNaN(gv)) return NaN;
      return al[i] === 0 ? 100 : 100 - 100 / (1 + gv / al[i]);
    }});
  }};

  window._lwc.macd = function(close, fast, slow, sig) {{
    var ef = window._lwc.ema(close, fast), es = window._lwc.ema(close, slow);
    var ml = ef.map(function(v, i) {{ return v - es[i]; }});
    var sl = window._lwc.ema(ml, sig);
    return {{line: ml, signal: sl, hist: ml.map(function(v, i) {{ return v - sl[i]; }})}};
  }};

  window._lwc.stochastic = function(high, low, close, k, d) {{
    var kArr = [];
    for (var i = 0; i < close.length; i++) {{
      if (i < k - 1) {{ kArr.push(NaN); continue; }}
      var lo = Infinity, hi = -Infinity;
      for (var j = i - k + 1; j <= i; j++) {{
        if (low[j] < lo) lo = low[j]; if (high[j] > hi) hi = high[j];
      }}
      var rng = hi - lo; kArr.push(rng === 0 ? NaN : 100 * (close[i] - lo) / rng);
    }}
    var dArr = new Array(close.length).fill(NaN);
    for (var i = k - 1 + d - 1; i < close.length; i++) {{
      var sum = 0, ok = true;
      for (var j = i - d + 1; j <= i; j++) {{ if (isNaN(kArr[j])) {{ ok = false; break; }} sum += kArr[j]; }}
      if (ok) dArr[i] = sum / d;
    }}
    return {{k: kArr, d: dArr}};
  }};

  window._lwc.drawdown = function(close) {{
    var r = [], mx = -Infinity;
    for (var i = 0; i < close.length; i++) {{
      if (close[i] > mx) mx = close[i];
      r.push(mx > 0 ? (close[i] - mx) / mx * 100 : 0);
    }}
    return r;
  }};

  window._lwc.atr = function(high, low, close, n) {{
    var tr = [high[0] - low[0]];   /* primer TR = rango del día (estándar Wilder) */
    for (var i = 1; i < close.length; i++) {{
      var a = high[i] - low[i], b = Math.abs(high[i] - close[i-1]), c = Math.abs(low[i] - close[i-1]);
      tr.push(Math.max(a, b, c));
    }}
    return window._lwc.emaW(tr, n);
  }};

  /* ── Overlays de eventos de mercado ── */

  window._lwc.drawEventOverlays = function(charts, panelDivs, events, times) {{
    /* Limpiar overlays previos en todos los paneles */
    panelDivs.forEach(function(div) {{
      div.querySelectorAll('.lwc-ev').forEach(function(el) {{ el.remove(); }});
    }});
    if (!events || !events.length || !charts.length || !times || !times.length) return;

    var refChart = charts[0];

    /* Índice del primer bar >= dateStr (búsqueda binaria en times[]) */
    function barIndex(dateStr) {{
      var lo = 0, hi = times.length - 1;
      while (lo <= hi) {{
        var mid = (lo + hi) >> 1;
        if (times[mid] < dateStr) lo = mid + 1;
        else if (times[mid] > dateStr) hi = mid - 1;
        else return mid;
      }}
      return lo; /* primer bar DESPUÉS de dateStr si no existe exacto */
    }}

    function reposition() {{
      if (window._lwcState && window._lwcState.eventsEnabled === false) return;
      var vr = refChart.timeScale().getVisibleLogicalRange();
      if (!vr) return;
      var fromIdx = vr.from, toIdx = vr.to, span = toIdx - fromIdx;
      if (span <= 0) return;

      events.forEach(function(ev) {{
        var i1 = barIndex(ev.start);
        var i2 = barIndex(ev.end);
        panelDivs.forEach(function(div) {{
          var el = div.querySelector('[data-ev="' + ev.id + '"]');
          if (!el) return;
          var W  = div.clientWidth;
          var x1 = (i1 - fromIdx) / span * W;
          var x2 = (i2 - fromIdx) / span * W;
          if (x1 >= W || x2 <= 0) {{ el.style.display = 'none'; return; }}
          var left  = Math.max(0, x1);
          var right = Math.min(W, x2);
          if (right <= left) {{ el.style.display = 'none'; return; }}
          el.style.display = '';
          el.style.left  = left + 'px';
          el.style.width = (right - left) + 'px';
        }});
      }});
    }}

    /* Convierte hex color a rgba con alpha dado */
    function hexRgba(hex, a) {{
      var h = (hex || '#ff9800').replace('#','');
      if (h.length === 3) h = h[0]+h[0]+h[1]+h[1]+h[2]+h[2];
      var r = parseInt(h.slice(0,2),16), g = parseInt(h.slice(2,4),16), b = parseInt(h.slice(4,6),16);
      return 'rgba('+r+','+g+','+b+','+a+')';
    }}

    /* Crear overlay div en cada panel (etiqueta solo en panel de precio) */
    events.forEach(function(ev) {{
      panelDivs.forEach(function(div, di) {{
        var el = document.createElement('div');
        el.className = 'lwc-ev';
        el.setAttribute('data-ev', String(ev.id));
        el.title = ev.name + '  (' + ev.start + ' – ' + ev.end + ')';
        el.style.cssText = 'position:absolute;top:0;height:100%;pointer-events:none;z-index:2;overflow:hidden;';
        el.style.backgroundColor = hexRgba(ev.color, 0.13);
        /* Etiqueta de nombre solo en el primer panel (precio) */
        if (di === 0) {{
          var lbl = document.createElement('span');
          lbl.textContent = ev.name;
          lbl.style.cssText = 'position:absolute;top:4px;left:4px;font-size:10px;color:#fff;'
            + 'text-shadow:0 1px 2px rgba(0,0,0,0.8);white-space:nowrap;pointer-events:none;opacity:0.85;';
          el.appendChild(lbl);
        }}
        div.appendChild(el);
      }});
    }});

    setTimeout(reposition, 0);
    refChart.timeScale().subscribeVisibleLogicalRangeChange(reposition);
  }};

  window._lwc.drawRegimeZones = function(chart, div, zones, times) {{
    div.querySelectorAll('.lwc-regime').forEach(function(el) {{ el.remove(); }});
    if (!zones || !zones.length || !chart || !times || !times.length) return;

    var COLORS = {{
      bullish: 'rgba(76,175,80,0.10)',
      bearish: 'rgba(239,83,80,0.10)',
      lateral: 'rgba(100,149,237,0.13)',
    }};

    function barIndex(dateStr) {{
      var lo = 0, hi = times.length - 1;
      while (lo <= hi) {{
        var mid = (lo + hi) >> 1;
        if (times[mid] < dateStr) lo = mid + 1;
        else if (times[mid] > dateStr) hi = mid - 1;
        else return mid;
      }}
      return lo;
    }}

    function reposition() {{
      var vr = chart.timeScale().getVisibleLogicalRange();
      if (!vr) return;
      var fromIdx = vr.from, toIdx = vr.to, span = toIdx - fromIdx;
      if (span <= 0) return;
      var W = div.clientWidth;
      zones.forEach(function(z) {{
        var el = div.querySelector('[data-rz="' + z.start + '"]');
        if (!el) return;
        var x1 = (barIndex(z.start) - fromIdx) / span * W;
        var x2 = (barIndex(z.end)   - fromIdx) / span * W;
        if (x1 >= W || x2 <= 0) {{ el.style.display = 'none'; return; }}
        var left = Math.max(0, x1), right = Math.min(W, x2);
        if (right <= left) {{ el.style.display = 'none'; return; }}
        el.style.display = '';
        el.style.left  = left + 'px';
        el.style.width = (right - left) + 'px';
      }});
    }}

    zones.forEach(function(z) {{
      var el = document.createElement('div');
      el.className = 'lwc-regime';
      el.setAttribute('data-rz', z.start);
      el.style.cssText = 'position:absolute;top:0;height:100%;pointer-events:none;z-index:1;';
      el.style.backgroundColor = COLORS[z.regime] || 'rgba(128,128,128,0.07)';
      div.appendChild(el);
    }});

    setTimeout(reposition, 0);
    chart.timeScale().subscribeVisibleLogicalRangeChange(reposition);
  }};

  window._lwc.drawVolZones = function(chart, div, zones, times) {{
    div.querySelectorAll('.lwc-vol').forEach(function(el) {{ el.remove(); }});
    if (!zones || !zones.length || !chart || !times || !times.length) return;

    var COLORS = {{
      baja:    'rgba(2,136,209,0.10)',
      normal:  'rgba(84,110,122,0.10)',
      alta:    'rgba(239,108,0,0.13)',
      extrema: 'rgba(183,28,28,0.16)',
    }};

    function barIndex(dateStr) {{
      var lo = 0, hi = times.length - 1;
      while (lo <= hi) {{
        var mid = (lo + hi) >> 1;
        if (times[mid] < dateStr) lo = mid + 1;
        else if (times[mid] > dateStr) hi = mid - 1;
        else return mid;
      }}
      return lo;
    }}

    function reposition() {{
      var vr = chart.timeScale().getVisibleLogicalRange();
      if (!vr) return;
      var fromIdx = vr.from, toIdx = vr.to, span = toIdx - fromIdx;
      if (span <= 0) return;
      var W = div.clientWidth;
      zones.forEach(function(z) {{
        var el = div.querySelector('[data-vz="' + z.start + '"]');
        if (!el) return;
        var x1 = (barIndex(z.start) - fromIdx) / span * W;
        var x2 = (barIndex(z.end)   - fromIdx) / span * W;
        if (x1 >= W || x2 <= 0) {{ el.style.display = 'none'; return; }}
        var left = Math.max(0, x1), right = Math.min(W, x2);
        if (right <= left) {{ el.style.display = 'none'; return; }}
        el.style.display = '';
        el.style.left  = left + 'px';
        el.style.width = (right - left) + 'px';
      }});
    }}

    zones.forEach(function(z) {{
      var el = document.createElement('div');
      el.className = 'lwc-vol';
      el.setAttribute('data-vz', z.start);
      var label = z.vol_regime + ' | ' + z.dur_regime + (z.atr_pct != null ? ' (' + z.atr_pct.toFixed(0) + 'p)' : '');
      el.title = label;
      el.style.cssText = 'position:absolute;top:0;height:100%;pointer-events:none;z-index:1;';
      el.style.backgroundColor = COLORS[z.vol_regime] || 'rgba(128,128,128,0.07)';
      div.appendChild(el);
    }});

    setTimeout(reposition, 0);
    chart.timeScale().subscribeVisibleLogicalRangeChange(reposition);
  }};

  /* ── Funciones de render ── */

  window._lwc.resample = function(daily, freq) {{
    if (freq === 'D') return daily;
    var groups = {{}}, keys = [];
    daily.forEach(function(b) {{
      var key;
      if (freq === 'W') {{
        var d = new Date(b.time + 'T00:00:00Z'), dow = d.getUTCDay() || 7;
        d.setUTCDate(d.getUTCDate() - (dow - 1)); key = d.toISOString().slice(0, 10);
      }} else {{ key = b.time.slice(0, 7) + '-01'; }}
      if (!groups[key]) {{
        groups[key] = {{time: key, open: b.open, high: b.high, low: b.low, close: b.close, volume: b.volume || 0}};
        keys.push(key);
      }} else {{
        var g = groups[key];
        if (b.high > g.high) g.high = b.high; if (b.low < g.low) g.low = b.low;
        g.close = b.close; g.volume = (g.volume || 0) + (b.volume || 0);
      }}
    }});
    return keys.sort().map(function(k) {{ return groups[k]; }});
  }};

  /* Columnas Punto y Figura sobre OHLC: cada columna se dibuja como una vela
     (X = verde sube, O = roja baja), fechada al fin de la columna. */
  window._lwc.pnfColumns = function(ohlcv, box, reversal, source) {{
    if (!box || box <= 0 || !ohlcv.length) return [];
    var useHl = source === 'hl';
    var cols = [], cur = null, refHi = null, refLo = null;
    function fl(p) {{ return Math.floor(p / box); }}
    ohlcv.forEach(function(b) {{
      if (b.close == null) return;
      var hi = useHl && b.high != null ? b.high : b.close;
      var lo = useHl && b.low  != null ? b.low  : b.close;
      var hb = fl(hi), lb = fl(lo);
      if (cur === null) {{
        if (refHi === null) {{ refHi = hb; refLo = lb; return; }}
        if (hb > refHi)      cur = {{type:'X', top: hb, bot: refLo, end: b.time}};
        else if (lb < refLo) cur = {{type:'O', top: refHi, bot: lb, end: b.time}};
        else {{ refHi = Math.max(refHi, hb); refLo = Math.min(refLo, lb); }}
        return;
      }}
      if (cur.type === 'X') {{
        if (hb > cur.top) {{ cur.top = hb; cur.end = b.time; }}
        else if (cur.top - lb >= reversal) {{
          cols.push(cur);
          cur = {{type:'O', top: cur.top - 1, bot: lb, end: b.time}};
        }}
      }} else {{
        if (lb < cur.bot) {{ cur.bot = lb; cur.end = b.time; }}
        else if (hb - cur.bot >= reversal) {{
          cols.push(cur);
          cur = {{type:'X', top: hb, bot: cur.bot + 1, end: b.time}};
        }}
      }}
    }});
    if (cur !== null) cols.push(cur);
    return cols.map(function(c) {{
      var loP = c.bot * box, hiP = (c.top + 1) * box;
      return {{time: c.end, high: hiP, low: loP,
               open: c.type === 'X' ? loP : hiP,
               close: c.type === 'X' ? hiP : loP, volume: 0}};
    }});
  }};

  window._lwc.addSeries = function(chart, spec) {{
    var s;
    if (spec.type === 'candlestick') {{
      s = chart.addCandlestickSeries({{
        upColor: '#00b050', downColor: '#ef5350',
        borderUpColor: '#00b050', borderDownColor: '#ef5350',
        wickUpColor: '#00b050', wickDownColor: '#ef5350'
      }});
    }} else if (spec.type === 'line') {{
      s = chart.addLineSeries({{
        color: spec.color || '#2196f3', lineWidth: spec.lineWidth || 1.5,
        title: spec.name || '', priceLineVisible: false, lastValueVisible: true,
        lineStyle: spec.dashed ? LightweightCharts.LineStyle.Dashed : LightweightCharts.LineStyle.Solid,
        pointMarkersVisible: !!spec.pointMarkers,
      }});
    }} else if (spec.type === 'histogram') {{
      s = chart.addHistogramSeries({{
        title: spec.name || '', color: spec.color || '#26a69a',
        priceFormat: spec.isVolume ? {{type: 'volume'}} : {{type: 'price', precision: 4}},
        priceLineVisible: false, lastValueVisible: !spec.isVolume,
      }});
    }}
    if (!s) return null;
    if (spec.data && spec.data.length) s.setData(spec.data);
    return s;
  }};

  window._lwc.drawRegimeEma = function(pc, zones, times, close, emaPeriod) {{
    window._lwcRegimeEmaSeries = window._lwcRegimeEmaSeries || [];
    if (!zones || !zones.length || !pc) return;
    var emaVals = window._lwc.ema(close, emaPeriod);
    var COLORS = {{bullish: '#4caf50', lateral: '#6495ed', bearish: '#ef5350'}};
    zones.forEach(function(zone) {{
      var color = COLORS[zone.regime] || '#888888';
      var data = [];
      for (var i = 0; i < times.length; i++) {{
        if (times[i] >= zone.start && times[i] <= zone.end && !isNaN(emaVals[i]))
          data.push({{time: times[i], value: emaVals[i]}});
      }}
      if (data.length < 2) return;
      var s = pc.addLineSeries({{
        color: color, lineWidth: 2,
        priceLineVisible: false, lastValueVisible: false,
        crosshairMarkerVisible: false,
      }});
      s.setData(data);
      window._lwcRegimeEmaSeries.push(s);
    }});
  }};

  window._lwc.fullRender = function() {{
    var st = window._lwcState;
    if (!st || !st.rawDaily) return;
    var container = document.getElementById('lwc-container');
    if (!container) return;

    /* Guardar rango si mismo activo */
    var savedRange = null;
    if (window._lwcLastAssetId === st.assetId && window._lwcCharts && window._lwcCharts.length > 0) {{
      try {{ savedRange = window._lwcCharts[0].timeScale().getVisibleLogicalRange(); }} catch(e) {{}}
    }}
    window._lwcLastAssetId = st.assetId;

    if (window._lwcCharts) window._lwcCharts.forEach(function(c) {{ try {{ c.remove(); }} catch(e) {{}} }});
    if (window._lwcResizeObs) window._lwcResizeObs.disconnect();
    window._lwcCharts = []; window._lwcPanelCharts = {{}}; window._lwcPanelDivs = {{}};
    container.innerHTML = '';

    var ohlcv  = window._lwc.resample(st.rawDaily, st.freq);
    /* Modo P&F: reemplaza las barras por columnas X/O (1 vela por columna) */
    if (st.chartType === 'pnf' && st.pnf) {{
      ohlcv = window._lwc.pnfColumns(ohlcv, st.pnf.box, st.pnf.reversal, st.pnf.source);
    }}
    var rect   = container.getBoundingClientRect();
    var totalH = Math.max(window.innerHeight - rect.top - 6, 200);
    container.style.height = totalH + 'px';
    var totalW = container.clientWidth || 800;

    var close = ohlcv.map(function(b) {{ return b.close; }});
    var high  = ohlcv.map(function(b) {{ return b.high;  }});
    var low   = ohlcv.map(function(b) {{ return b.low;   }});
    var times = ohlcv.map(function(b) {{ return b.time;  }});

    /* Calcular indicadores separados activos */
    var activeSeps = [];
    var ip = st.indParams;

    function toData(vals) {{
      return vals.map(function(v, i) {{ return isNaN(v) ? null : {{time: times[i], value: v}}; }})
                 .filter(function(x) {{ return x !== null; }});
    }}

    /* Mapea fecha exacta al índice de barra más cercano (necesario para S/M) */
    function nearestBarIdx(dateStr) {{
      for (var i = 0; i < times.length; i++) {{
        if (times[i] >= dateStr) return i;
      }}
      return times.length - 1;
    }}

    /* Paneles activos */
    var showVolume = !!st.volumeEnabled;
    ['rsi', 'macd', 'stochastic', 'atr', 'drawdown'].forEach(function(n) {{
      if (ip[n] && ip[n][0].enabled) activeSeps.push(n);
    }});
    var showStrategy = !!(st.strategyEnabled && st.strategyData
        && st.strategyData.asset_id === st.assetId
        && st.strategyData.scores && st.strategyData.scores.length);
    if (showStrategy) activeSeps.push('strategy');

    var panels = ['price'];
    if (showVolume) panels.push('volume');
    panels = panels.concat(activeSeps);

    /* Alturas: volumen fijo 60px, resto proporcional, suma = totalH */
    var heights = {{}};
    var VOLUME_H = showVolume ? 60 : 0;
    var ns = activeSeps.length;
    if (ns === 0) {{
      heights.price = totalH - VOLUME_H;
      if (showVolume) heights.volume = VOLUME_H;
    }} else {{
      var sepTotal = Math.round((totalH - VOLUME_H) * 0.42);
      heights.price = totalH - VOLUME_H - sepTotal;
      if (showVolume) heights.volume = VOLUME_H;
      var sh = Math.floor(sepTotal / ns), rem = sepTotal - sh * ns;
      activeSeps.forEach(function(p, i) {{ heights[p] = sh + (i === ns - 1 ? rem : 0); }});
    }}

    /* Crear charts con drag handles entre paneles */
    var handleInfo = [];
    panels.forEach(function(panel, idx) {{
      var div = document.createElement('div');
      div.style.cssText = 'width:100%;overflow:hidden;flex-shrink:0;';
      container.appendChild(div);
      var isLast = idx === panels.length - 1;
      var chart = LightweightCharts.createChart(div, {{
        width: totalW, height: heights[panel] || 60,
        layout: {{ background: {{type:'solid',color:'#1e1e1e'}}, textColor:'#dee2e6', fontSize: 11 }},
        grid:   {{ vertLines: {{color:'#2a2a2a'}}, horzLines: {{color:'#2a2a2a'}} }},
        crosshair: {{ mode: LightweightCharts.CrosshairMode.Normal }},
        rightPriceScale: {{ borderColor:'#444', scaleMargins: {{top:0.05,bottom:0.05}} }},
        timeScale: {{ borderColor:'#444', visible: isLast, timeVisible: false }},
        handleScroll: true, handleScale: true,
      }});
      window._lwcPanelCharts[panel] = chart;
      window._lwcPanelDivs[panel]   = div;
      window._lwcCharts.push(chart);
      /* Handle de resize (excepto después del último) */
      if (!isLast) {{
        var handle = document.createElement('div');
        handle.style.cssText = 'width:100%;height:5px;cursor:row-resize;background:#2a2a2a;flex-shrink:0;';
        handle.onmouseover = function() {{ this.style.background='#555'; }};
        handle.onmouseout  = function() {{ this.style.background='#2a2a2a'; }};
        container.appendChild(handle);
        handleInfo.push({{handle: handle, idx: idx}});
      }}
    }});

    /* Eventos de drag en los handles */
    handleInfo.forEach(function(h) {{
      (function(handle, i) {{
        handle.addEventListener('mousedown', function(e) {{
          e.preventDefault();
          var startY = e.clientY;
          var c1 = window._lwcCharts[i], c2 = window._lwcCharts[i + 1];
          var h1 = c1.options().height, h2 = c2.options().height;
          function onMove(ev) {{
            var dy = ev.clientY - startY;
            c1.applyOptions({{height: Math.max(60, h1 + dy)}});
            c2.applyOptions({{height: Math.max(40, h2 - dy)}});
          }}
          function onUp() {{
            document.removeEventListener('mousemove', onMove);
            document.removeEventListener('mouseup', onUp);
          }}
          document.addEventListener('mousemove', onMove);
          document.addEventListener('mouseup', onUp);
        }});
      }})(h.handle, h.idx);
    }});

    /* Escala logarítmica */
    if (st.logScale && window._lwcPanelCharts.price) {{
      window._lwcPanelCharts.price.priceScale('right').applyOptions({{
        mode: LightweightCharts.PriceScaleMode.Logarithmic
      }});
    }}

    /* Serie de precio */
    var pc = window._lwcPanelCharts.price;
    window._lwcRegimeEmaSeries = [];
    if (st.chartType === 'candlestick' || st.chartType === 'pnf') {{
      window._lwcPriceSeries = window._lwc.addSeries(pc, {{type: 'candlestick', data: ohlcv}});
    }} else {{
      window._lwcPriceSeries = window._lwc.addSeries(pc, {{type: 'line', color: '#2196f3', lineWidth: 1.5,
        data: ohlcv.map(function(b) {{ return {{time: b.time, value: b.close}}; }})}});
    }}

    /* Volumen */
    if (showVolume && window._lwcPanelCharts.volume) {{
      window._lwc.addSeries(window._lwcPanelCharts.volume, {{
        type: 'histogram', isVolume: true,
        data: ohlcv.map(function(b) {{
          return {{time: b.time, value: b.volume || 0, color: b.close >= b.open ? '#00b050' : '#ef5350'}};
        }})
      }});
    }}

    /* SMA */
    var smaColors = ['#ff9800','#e91e63','#4caf50'];
    var bestMaFreq = (st.bestMa || {{}})[st.freq] || {{}};
    var lastClose = close[close.length - 1];
    ip.sma.forEach(function(s, i) {{
      if (!s.enabled) return;
      var vals = window._lwc.sma(close, s.period);
      var name = 'SMA ' + s.period;
      if (s.period === bestMaFreq.sma) {{
        var lastMa = vals[vals.length - 1];
        if (!isNaN(lastMa) && lastMa > 0) {{
          var pct = (lastClose - lastMa) / lastMa * 100;
          name += ' (' + (pct >= 0 ? '+' : '') + pct.toFixed(1) + '%)';
        }}
      }}
      window._lwc.addSeries(pc, {{type:'line', name: name,
        color: smaColors[i], lineWidth: 1.5,
        data: toData(vals)}});
    }});

    /* EMA */
    var emaColors = ['#00bcd4','#9c27b0','#ffeb3b'];
    ip.ema.forEach(function(s, i) {{
      if (!s.enabled) return;
      var vals = window._lwc.ema(close, s.period);
      var name = 'EMA ' + s.period;
      if (s.period === bestMaFreq.ema) {{
        var lastMa = vals[vals.length - 1];
        if (!isNaN(lastMa) && lastMa > 0) {{
          var pct = (lastClose - lastMa) / lastMa * 100;
          name += ' (' + (pct >= 0 ? '+' : '') + pct.toFixed(1) + '%)';
        }}
      }}
      window._lwc.addSeries(pc, {{type:'line', name: name,
        color: emaColors[i], lineWidth: 1.5, dashed: true,
        data: toData(vals)}});
    }});

    /* Bollinger */
    if (ip.bollinger[0].enabled) {{
      var bb = window._lwc.bollinger(close, ip.bollinger[0].period, ip.bollinger[0].std_dev);
      window._lwc.addSeries(pc, {{type:'line', name:'BB Sup', color:'#7e57c2', lineWidth:1, dashed:true, data: toData(bb.upper)}});
      window._lwc.addSeries(pc, {{type:'line', name:'BB Med', color:'#e91e63', lineWidth:1, data: toData(bb.mid)}});
      window._lwc.addSeries(pc, {{type:'line', name:'BB Inf', color:'#7e57c2', lineWidth:1, dashed:true, data: toData(bb.lower)}});
    }}

    /* RSI */
    if (ip.rsi[0].enabled && window._lwcPanelCharts.rsi) {{
      var rsiVals = window._lwc.rsi(close, ip.rsi[0].period);
      var rsiS = window._lwc.addSeries(window._lwcPanelCharts.rsi, {{
        type:'line', name:'RSI', color:'#9c27b0', lineWidth:1.5, data: toData(rsiVals)}});
      window._lwcPanelCharts.rsi.addLineSeries({{color:'#ef5350',lineWidth:1,priceLineVisible:false,lastValueVisible:false}}).setData([{{time:times[0],value:70}},{{time:times[times.length-1],value:70}}]);
      window._lwcPanelCharts.rsi.addLineSeries({{color:'#4caf50',lineWidth:1,priceLineVisible:false,lastValueVisible:false}}).setData([{{time:times[0],value:30}},{{time:times[times.length-1],value:30}}]);
    }}

    /* MACD */
    if (ip.macd[0].enabled && window._lwcPanelCharts.macd) {{
      var mc = window._lwc.macd(close, ip.macd[0].fast, ip.macd[0].slow, ip.macd[0].signal);
      window._lwc.addSeries(window._lwcPanelCharts.macd, {{type:'line',  name:'MACD',  color:'#2196f3', lineWidth:1.5, data: toData(mc.line)}});
      window._lwc.addSeries(window._lwcPanelCharts.macd, {{type:'line',  name:'Señal', color:'#ff5722', lineWidth:1,   data: toData(mc.signal)}});
      window._lwc.addSeries(window._lwcPanelCharts.macd, {{
        type:'histogram', name:'Hist',
        data: mc.hist.map(function(v, i) {{
          return isNaN(v) ? null : {{time: times[i], value: v, color: v >= 0 ? '#00b050' : '#ef5350'}};
        }}).filter(function(x) {{ return x !== null; }})
      }});
    }}

    /* Estocástico */
    if (ip.stochastic[0].enabled && window._lwcPanelCharts.stochastic) {{
      var st2 = window._lwc.stochastic(high, low, close, ip.stochastic[0].k_period, ip.stochastic[0].d_period);
      window._lwc.addSeries(window._lwcPanelCharts.stochastic, {{type:'line', name:'%K', color:'#ffeb3b', lineWidth:1.5, data: toData(st2.k)}});
      window._lwc.addSeries(window._lwcPanelCharts.stochastic, {{type:'line', name:'%D', color:'#ff9800', lineWidth:1.5, data: toData(st2.d)}});
    }}

    /* Drawdown */
    if (ip.drawdown[0].enabled && window._lwcPanelCharts.drawdown) {{
      var ddVals = window._lwc.drawdown(close);
      window._lwc.addSeries(window._lwcPanelCharts.drawdown, {{
        type: 'line', name: 'Drawdown', color: '#ef5350', lineWidth: 1.5,
        data: toData(ddVals)
      }});
    }}

    /* ATR */
    if (ip.atr[0].enabled && window._lwcPanelCharts.atr) {{
      var atrVals = window._lwc.atr(high, low, close, ip.atr[0].period);
      window._lwc.addSeries(window._lwcPanelCharts.atr, {{type:'line', name:'ATR', color:'#00bcd4', lineWidth:1.5, data: toData(atrVals)}});
    }}

    /* Score de estrategia (panel separado, como el RSI) con los umbrales
       de entrada/salida como líneas de referencia.
       La serie cubre TODAS las barras del precio: las fechas sin score van
       como whitespace ({{time}} sin value) — los paneles se sincronizan por
       rango LÓGICO (índice de barra), así que si este chart tuviera menos
       barras que el de precio quedaría corrido hacia la izquierda. */
    if (showStrategy && window._lwcPanelCharts.strategy) {{
      /* OJO: NO llamar 'pc' a esta variable — var es function-scoped y
         pisaría el pc del panel de PRECIO (983), que se sigue usando más
         abajo (EMA de régimen, zonas de volatilidad). */
      var stratPc = window._lwcPanelCharts.strategy;
      var scoreByIdx = {{}};
      st.strategyData.scores.forEach(function(p) {{
        scoreByIdx[nearestBarIdx(p[0])] = p[1];  /* W/M: queda el último del período */
      }});

      /* Serie base: whitespace sobre TODAS las barras. Alinea el panel por
         índice lógico con el de precio (si arrancara en la primera barra
         con score quedaría corrido). */
      window._lwc.addSeries(stratPc, {{
        type: 'line', name: 'Score ' + (st.strategyData.name || ''),
        color: '#38bdf8', lineWidth: 1.5,
        data: times.map(function(t) {{ return {{time: t}}; }}),
      }});

      /* Líneas de umbral como SERIES horizontales (un punto por barra,
         punteadas) — NO como price lines: createPriceLine sobre las series
         de este panel demostró no pintarse (bug perseguido en vivo,
         jul-2026); una serie con datos usa el mismo camino de render que
         los segmentos de score, que sí se ven, y además participa del
         auto-escalado (el nivel siempre entra en la escala). Entrada:
         siempre (en modo percentil es orientativa — unidades de
         percentil); salida: solo en umbral absoluto (los demás modos no
         tienen nivel fijo de score). */
      var _spec = st.strategySpec || {{entries: [], score_exits: []}};
      var thrLines = [];
      (_spec.entries || []).forEach(function(e) {{
        if (e.type === 'score') thrLines.push({{price: e.th, color: '#4ade80'}});
      }});
      (_spec.score_exits || []).forEach(function(x) {{
        if (x.type === 'absolute' || x.type === 'absolute_above')
          thrLines.push({{price: x.x, color: '#ef5350'}});
      }});
      thrLines.forEach(function(pl) {{
        window._lwc.addSeries(stratPc, {{
          type: 'line', color: pl.color, lineWidth: 1, dashed: true,
          data: times.map(function(t) {{ return {{time: t, value: pl.price}}; }}),
        }});
      }});

      /* Score en SEGMENTOS: una línea por tramo contiguo de barras con score.
         Los días sin score (activo no elegible por el filtro) quedan como
         CORTES, no como una recta que cruza el hueco — en lightweight-charts el
         whitespace no corta la línea. Un tramo de una sola barra se dibuja como
         punto (una recta necesita 2). */
      var seg = [];
      var flushSeg = function() {{
        if (seg.length) {{
          window._lwc.addSeries(stratPc, {{
            type: 'line', color: '#38bdf8', lineWidth: 1.5, data: seg,
            pointMarkers: seg.length === 1,
          }});
        }}
        seg = [];
      }};
      for (var i = 0; i < times.length; i++) {{
        if (scoreByIdx.hasOwnProperty(i)) seg.push({{time: times[i], value: scoreByIdx[i]}});
        else flushSeg();
      }}
      flushSeg();
    }}

    /* Sync timescales */
    if (window._lwcCharts.length > 1) {{
      window._lwcCharts.forEach(function(src, i) {{
        src.timeScale().subscribeVisibleLogicalRangeChange(function(range) {{
          if (!range) return;
          window._lwcCharts.forEach(function(dst, j) {{
            if (i !== j) dst.timeScale().setVisibleLogicalRange(range);
          }});
        }});
      }});
    }}

    if (savedRange) {{
      window._lwcCharts.forEach(function(c) {{ c.timeScale().setVisibleLogicalRange(savedRange); }});
    }} else {{
      window._lwcCharts.forEach(function(c) {{ c.timeScale().fitContent(); }});
    }}

    /* Overlays de eventos */
    var evts = st.events || [];
    if (evts.length && st.eventsEnabled !== false) {{
      var allDivs = panels.map(function(p) {{ return window._lwcPanelDivs[p]; }}).filter(Boolean);
      setTimeout(function() {{
        window._lwc.drawEventOverlays(window._lwcCharts, allDivs, evts, times);
      }}, 0);
    }}

    /* EMA de régimen coloreada (sin sombreado de fondo) */
    if (st.regimeEnabled) {{
      var rzones = (st.regimeZones || {{}})[st.freq] || [];
      if (rzones.length) {{
        var emaPeriod = (st.regimeEmaPeriods || {{}})[st.freq] || 200;
        window._lwc.drawRegimeEma(pc, rzones, times, close, emaPeriod);
      }}
    }}

    /* Zonas de volatilidad ATR */
    if (st.volEnabled) {{
      var vzones = (st.volZones || {{}})[st.freq] || [];
      if (vzones.length) {{
        if (window._lwcPanelDivs.price) {{
          window._lwc.drawVolZones(pc, window._lwcPanelDivs.price, vzones, times);
        }}
        if (window._lwcPanelCharts.atr && window._lwcPanelDivs.atr) {{
          window._lwc.drawVolZones(window._lwcPanelCharts.atr, window._lwcPanelDivs.atr, vzones, times);
        }}
      }}
    }}

    /* Pivots S/R */
    if (st.srPivotEnabled && st.srPivots && window._lwcPriceSeries) {{
      var pivots = st.srPivots;
      (pivots.resist || []).forEach(function(lvl) {{
        window._lwcPriceSeries.createPriceLine({{
          price: lvl.price,
          color: 'rgba(239, 83, 80, 0.85)',
          lineWidth: lvl.touches >= 3 ? 2 : 1,
          lineStyle: 2,
          axisLabelVisible: true,
          title: 'R' + lvl.touches,
        }});
      }});
      (pivots.support || []).forEach(function(lvl) {{
        window._lwcPriceSeries.createPriceLine({{
          price: lvl.price,
          color: 'rgba(102, 187, 106, 0.85)',
          lineWidth: lvl.touches >= 3 ? 2 : 1,
          lineStyle: 2,
          axisLabelVisible: true,
          title: 'S' + lvl.touches,
        }});
      }});
    }}

    /* Marcadores sobre el precio: drawdown + estrategia comparten la
       misma llamada (setMarkers REEMPLAZA todos los markers de la serie) */
    var allMarkers = [];

    if (st.ddEnabled && st.ddEvents && st.ddEvents.length) {{
      st.ddEvents.forEach(function(ev) {{
        if (!ev.trough) return;
        allMarkers.push({{
          time: times[nearestBarIdx(ev.trough)],
          position: 'belowBar',
          color: '#ef5350',
          shape: 'arrowUp',
          text: Math.abs(ev.depth).toFixed(1) + '%',
          size: 1,
        }});
      }});
    }}

    /* Entradas/salidas de estrategia: window._lwc.simulateTrades (espejo del
       contrato Python trade_simulator.py). Acá solo se arma la spec desde los
       controles, se mapean los scores/percentiles a barras y se dibujan
       marcadores + métricas. */
    var stratLabel = document.getElementById('chart-strategy-label');
    if (st.strategyEnabled && st.strategyData
        && st.strategyData.asset_id === st.assetId
        && st.strategyData.scores && st.strategyData.scores.length) {{
      /* Scores/percentiles alineados a las barras propias (W/M: queda el
         último del período, igual que el panel de score). */
      var simScores = [], simPcts = [];
      var _sIdx = {{}}, _pIdx = {{}};
      st.strategyData.scores.forEach(function(p) {{ _sIdx[nearestBarIdx(p[0])] = p[1]; }});
      (st.strategyData.percentiles || []).forEach(function(p) {{ _pIdx[nearestBarIdx(p[0])] = p[1]; }});
      for (var bi = 0; bi < times.length; bi++) {{
        simScores.push(_sIdx.hasOwnProperty(bi) ? _sIdx[bi] : null);
        simPcts.push(_pIdx.hasOwnProperty(bi) ? _pIdx[bi] : null);
      }}

      var trades = window._lwc.simulateTrades(
        close, simScores,
        st.strategySpec || {{entries: [], score_exits: [], caps: []}},
        simPcts);

      var exitTxt = {{max_bars: 'S t', stop_loss: 'S SL',
                     trailing_stop: 'S TS', take_profit: 'S TP',
                     filter: 'S filtro'}};
      trades.forEach(function(t) {{
        var esc = simScores[t.entry_idx];
        allMarkers.push({{
          time: times[t.entry_idx], position: 'belowBar', color: '#4ade80',
          shape: 'arrowUp',
          text: 'E' + (esc == null ? '' : ' ' + Math.round(esc)), size: 1,
        }});
        if (t.exit_idx !== null) {{
          var xsc = simScores[t.exit_idx];
          var txt = exitTxt[t.reason]
                    || ('S' + (xsc == null ? '' : ' ' + Math.round(xsc)));
          allMarkers.push({{
            time: times[t.exit_idx], position: 'aboveBar', color: '#ef5350',
            shape: 'arrowDown', text: txt, size: 1,
          }});
        }}
      }});

      /* Métricas (espejo de summarize_trades). Retornos coloreados:
         verde >= 0, rojo < 0 — por eso innerHTML (solo números propios,
         sin datos externos). */
      if (stratLabel) {{
        var closedT = trades.filter(function(t) {{ return t.exit_idx !== null; }});
        var rets = closedT.map(function(t) {{ return t.ret; }})
                          .filter(function(r) {{ return r !== null; }});
        var openT = trades.length && trades[trades.length - 1].exit_idx === null
                    ? trades[trades.length - 1] : null;
        var fmt = function(r) {{
          var txt = (r >= 0 ? '+' : '') + (r * 100).toFixed(1) + '%';
          var col = r >= 0 ? '#4ade80' : '#ef5350';
          return '<span style="color:' + col + '">' + txt + '</span>';
        }};
        var parts = [trades.length + ' entrada' + (trades.length === 1 ? '' : 's')];
        if (rets.length) {{
          var wins = rets.filter(function(r) {{ return r > 0; }}).length;
          var avg = rets.reduce(function(a, b) {{ return a + b; }}, 0) / rets.length;
          var tot = rets.reduce(function(a, b) {{ return a * (1 + b); }}, 1) - 1;
          var sorted = rets.slice().sort(function(a, b) {{ return a - b; }});
          var mid = Math.floor(sorted.length / 2);
          var med = (sorted.length % 2) ? sorted[mid] : (sorted[mid - 1] + sorted[mid]) / 2;
          var bars = closedT.reduce(function(a, t) {{ return a + (t.exit_idx - t.entry_idx); }}, 0) / closedT.length;
          parts.push(closedT.length + ' cerrada' + (closedT.length === 1 ? '' : 's'));
          parts.push(Math.round(wins / rets.length * 100) + '% ganadoras');
          /* total compuesto: la métrica del ranking del optimizador */
          parts.push('total ' + fmt(tot));
          parts.push('media ' + fmt(avg) + ' mediana ' + fmt(med));
          parts.push('mín ' + fmt(sorted[0]) + ' máx ' + fmt(sorted[sorted.length - 1]));
          parts.push(bars.toFixed(1) + ' ruedas');
          var nFilt = closedT.filter(function(t) {{ return t.reason === 'filter'; }}).length;
          if (nFilt) parts.push(nFilt + ' cierre' + (nFilt === 1 ? '' : 's') + ' por filtro');
        }}
        if (openT && openT.ret !== null) parts.push('abierta ' + fmt(openT.ret));
        stratLabel.innerHTML = trades.length ? parts.join(' · ')
                                             : 'sin entradas con estos parámetros';
      }}
    }} else if (stratLabel) {{
      stratLabel.textContent = '';
    }}

    if (allMarkers.length && window._lwcPriceSeries) {{
      allMarkers.sort(function(a, b) {{ return a.time < b.time ? -1 : 1; }});
      window._lwcPriceSeries.setMarkers(allMarkers);
    }}

    if (window.ResizeObserver) {{
      window._lwcResizeObs = new ResizeObserver(function() {{
        var w = container.clientWidth;
        window._lwcCharts.forEach(function(c) {{ c.applyOptions({{width: w}}); }});
      }});
      window._lwcResizeObs.observe(container);
    }}
  }};

  /* ── Simulador de trades ──
     ESPEJO de app/services/trade_simulator.py (REGLA DE HOMOLOGACIÓN, ver
     CLAUDE.md): misma máquina de estados, mismo orden de evaluación
     (filtro → caps → score_exits), entries en AND, salidas en OR, misma
     semántica de cola sin score. Cualquier cambio de semántica va en AMBOS
     archivos en el mismo commit; el contrato ejecutable vive en
     tests/fixtures/trade_simulator_cases.json. */
  window._lwc.simulateTrades = function(closes, scores, spec, percentiles) {{
    var entries = spec.entries || [], scoreExits = spec.score_exits || [];
    var caps = spec.caps || [];
    var rearm = !!spec.rearm, cooldown = spec.cooldown || 0;
    var lastScored = -1;
    for (var j = scores.length - 1; j >= 0; j--) {{
      if (scores[j] !== null && scores[j] !== undefined) {{ lastScored = j; break; }}
    }}
    if (lastScored < 0) return [];

    /* AND de todas las condiciones activas; dato faltante = no cumple */
    var entryOk = function(sc, pc) {{
      if (!entries.length) return false;
      for (var e = 0; e < entries.length; e++) {{
        var v = entries[e].type === 'score' ? sc : pc;
        if (v === null || v < entries[e].th) return false;
      }}
      return true;
    }};

    var trades = [];
    var inPos = false, entryIdx = null, entryClose = null, entryScore = null;
    var maxScore = null, maxClose = null;
    var maWindow = [], k = null;
    for (var xk = 0; xk < scoreExits.length; xk++) {{
      if (scoreExits[xk].type === 'score_ma') {{ k = scoreExits[xk].k; break; }}
    }}
    var armed = true, lastExit = null;  /* re-armado por cruce + cooldown */
    var closeTrade = function(i, reason) {{
      var ret = (entryClose > 0) ? closes[i] / entryClose - 1 : null;
      trades.push({{entry_idx: entryIdx, exit_idx: i, entry_close: entryClose,
                   exit_close: closes[i], ret: ret, reason: reason}});
      inPos = false;
      armed = false;
      lastExit = i;
    }};
    for (var i = 0; i <= lastScored; i++) {{
      var c = closes[i];
      var sc = (scores[i] === undefined) ? null : scores[i];
      var pc = percentiles ? ((percentiles[i] === undefined) ? null : percentiles[i]) : null;
      /* media móvil del score: propiedad de la serie, no del trade */
      var ma = null;
      if (k !== null && sc !== null) {{
        maWindow.push(sc);
        if (maWindow.length > k) maWindow.shift();
        if (maWindow.length === k) {{
          ma = maWindow.reduce(function(a, b) {{ return a + b; }}, 0) / k;
        }}
      }}
      if (!inPos) {{
        if (sc === null) continue;  /* sin score no hay evaluación ni armado */
        if (!entryOk(sc, pc)) {{
          armed = true;  /* la señal se reseteó: re-arma el cruce */
        }} else if ((!rearm || armed)
                   && (lastExit === null || i - lastExit > cooldown)) {{
          inPos = true; entryIdx = i; entryClose = c;
          entryScore = sc; maxScore = sc; maxClose = c;
        }}
        continue;  /* en la barra de entrada no se evalúan salidas */
      }}
      /* 1) elegibilidad */
      if (sc === null) {{ closeTrade(i, 'filter'); continue; }}
      /* máximos INCLUYENDO la barra actual */
      if (maxScore === null || sc > maxScore) maxScore = sc;
      if (c > maxClose) maxClose = c;
      /* 2) salidas por precio/tiempo (orden de la lista; gana la primera) */
      var reason = null;
      for (var ci = 0; ci < caps.length && reason === null; ci++) {{
        var cap = caps[ci];
        if (cap.type === 'max_bars' && i - entryIdx >= cap.n) reason = 'max_bars';
        else if (cap.type === 'stop_loss' && entryClose > 0
                 && c <= entryClose * (1 - cap.pct / 100)) reason = 'stop_loss';
        else if (cap.type === 'trailing_stop' && maxClose > 0
                 && c <= maxClose * (1 - cap.pct / 100)) reason = 'trailing_stop';
        else if (cap.type === 'take_profit' && entryClose > 0
                 && c >= entryClose * (1 + cap.pct / 100)) reason = 'take_profit';
      }}
      /* 3) salidas por score (orden de la lista; gana la primera) */
      for (var xi = 0; xi < scoreExits.length && reason === null; xi++) {{
        var x = scoreExits[xi], t = x.type;
        if (t === 'absolute' && sc < x.x) reason = t;
        else if (t === 'absolute_above' && sc > x.x) reason = t;
        else if (t === 'delta_entry' && sc < entryScore - x.x) reason = t;
        else if (t === 'trailing_score' && sc < maxScore - x.x) reason = t;
        else if (t === 'score_ma' && ma !== null && sc < ma) reason = t;
        else if (t === 'percentile' && pc !== null && pc < x.x) reason = t;
      }}
      if (reason) closeTrade(i, reason);
    }}
    if (inPos) {{
      var oret = (entryClose > 0) ? closes[closes.length - 1] / entryClose - 1 : null;
      trades.push({{entry_idx: entryIdx, exit_idx: null, entry_close: entryClose,
                   exit_close: null, ret: oret, reason: null}});
    }}
    return trades;
  }};

  /* Spec del simulador desde los controles del panel, en el ORDEN CANÓNICO
     que el contrato evalúa (listas OR: gana la primera). Compartido por el
     callback de controles y el init del render — un solo armador, cero
     divergencia. Firma posicional = orden de los Inputs/States en ambos
     callbacks (mantener sincronizados los tres lugares). */
  window._lwc.buildSpec = function(
      entScOn, entSc, entPctOn, entPct,
      xsAbsOn, xsAbs, xsAbsUpOn, xsAbsUp, xsDentOn, xsDent, xsDmaxOn, xsDmax,
      xsMakOn, xsMak, xsPctOn, xsPct,
      capBarsOn, capBars, capSlOn, capSl, capTsOn, capTs, capTpOn, capTp,
      rearmOn, coolOn, cool) {{
    var on = function(v) {{ return !!(v && v.length); }};
    var num = function(v) {{
      var x = Number(v);
      return (v === null || v === undefined || v === '' || isNaN(x)) ? null : x;
    }};
    var entries = [];
    if (on(entScOn) && num(entSc) !== null)
      entries.push({{type: 'score', th: num(entSc)}});
    if (on(entPctOn) && num(entPct) !== null)
      entries.push({{type: 'pct', th: num(entPct)}});
    var scoreExits = [];
    if (on(xsAbsOn) && num(xsAbs) !== null)
      scoreExits.push({{type: 'absolute', x: num(xsAbs)}});
    if (on(xsAbsUpOn) && num(xsAbsUp) !== null)
      scoreExits.push({{type: 'absolute_above', x: num(xsAbsUp)}});
    if (on(xsDentOn) && num(xsDent) !== null)
      scoreExits.push({{type: 'delta_entry', x: num(xsDent)}});
    if (on(xsDmaxOn) && num(xsDmax) !== null)
      scoreExits.push({{type: 'trailing_score', x: num(xsDmax)}});
    if (on(xsMakOn) && num(xsMak) !== null)
      scoreExits.push({{type: 'score_ma', k: Math.max(2, Math.round(num(xsMak)))}});
    if (on(xsPctOn) && num(xsPct) !== null)
      scoreExits.push({{type: 'percentile', x: num(xsPct)}});
    var caps = [];
    if (on(capBarsOn) && num(capBars) !== null)
      caps.push({{type: 'max_bars', n: Math.max(1, Math.round(num(capBars)))}});
    if (on(capSlOn) && num(capSl) !== null)
      caps.push({{type: 'stop_loss', pct: num(capSl)}});
    if (on(capTsOn) && num(capTs) !== null)
      caps.push({{type: 'trailing_stop', pct: num(capTs)}});
    if (on(capTpOn) && num(capTp) !== null)
      caps.push({{type: 'take_profit', pct: num(capTp)}});
    var cd = (on(coolOn) && num(cool) !== null)
             ? Math.max(0, Math.round(num(cool))) : 0;
    return {{entries: entries, score_exits: scoreExits, caps: caps,
            rearm: on(rearmOn), cooldown: cd}};
  }};

  /* ── Actualizar estado y renderizar ── */
  var indParams = {_js_ind_params()};

  window._lwcState = {{
    rawDaily:          chartData.raw_daily,
    assetId:           chartData.asset_id,
    events:            chartData.events             || [],
    regimeZones:       {{}},
    regimeEmaPeriods:  chartData.regime_ema_periods || {{}},
    volZones:          {{}},
    volCurrent:        chartData.vol_current        || {{}},
    ddEvents:          [],
    bestMa:            chartData.best_ma            || {{}},
    srPivots:          chartData.sr_pivots          || null,
    pnf:               chartData.pnf                || null,
    eventsEnabled:     !!(eventsEnabled  && eventsEnabled.length),
    regimeEnabled:     !!(regimeEnabled  && regimeEnabled.length),
    ddEnabled:         !!(ddEnabled      && ddEnabled.length),
    volEnabled:        !!(volEnabled     && volEnabled.length),
    srPivotEnabled:    !!(srPivotEnabled && srPivotEnabled.length),
    strategyEnabled:   !!(strategyEnabled && strategyEnabled.length),
    strategySpec:      window._lwc.buildSpec(
                         entScOn, entSc, entPctOn, entPct,
                         xsAbsOn, xsAbs, xsAbsUpOn, xsAbsUp,
                         xsDentOn, xsDent, xsDmaxOn, xsDmax,
                         xsMakOn, xsMak, xsPctOn, xsPct,
                         capBarsOn, capBars, capSlOn, capSl, capTsOn, capTs,
                         capTpOn, capTp, rearmOn, coolOn, cool),
    strategyData:      strategyData || null,
    indParams:         indParams,
    volumeEnabled:     !!(volumeEnabled  && volumeEnabled.length),
    chartType:         chartType  || 'candlestick',
    freq:              freq       || 'D',
    logScale:          logScale   === 'log',
  }};
  window._lwc.fullRender();
  return null;
}}
"""

_JS_IND_UPDATE = f"""
function({_JS_ARGS_STR}) {{
  if (!window._lwcState || !window._lwc) return null;
  var indParams = {_js_ind_params()};
  window._lwcState.indParams = indParams;
  window._lwc.fullRender();
  return null;
}}
"""

# ─── Callback principal: chart-data → render completo ────────────────────────
clientside_callback(
    _JS_RENDER,
    Output("chart-render-dummy", "data"),
    Input("chart-data", "data"),
    State("chart-type", "value"),
    State("chart-freq", "value"),
    State("chart-yscale", "value"),
    State("chart-volume-enabled", "value"),
    State("chart-events-enabled", "value"),
    State("chart-regime-enabled", "value"),
    State("chart-dd-enabled", "value"),
    State("chart-vol-enabled", "value"),
    State("chart-sr-pivot-enabled", "value"),
    State("chart-strategy-enabled", "value"),
    *_sim_control_deps(State),
    State("chart-strategy-data", "data"),
    *_state_list(State),
    prevent_initial_call=True,
)

# ─── Callback de indicadores: param/toggle → recalcula en JS ─────────────────
clientside_callback(
    _JS_IND_UPDATE,
    Output("chart-ind-dummy", "data"),
    *_state_list(Input),
    prevent_initial_call=True,
)

# ─── Callbacks de controles sin round-trip ───────────────────────────────────
clientside_callback(
    "function(t){if(!window._lwcState||!window._lwc)return null;window._lwcState.chartType=t;window._lwc.fullRender();return null;}",
    Output("chart-type-dummy", "data"),
    Input("chart-type", "value"),
    prevent_initial_call=True,
)
clientside_callback(
    "function(f){if(!window._lwcState||!window._lwc)return null;window._lwcState.freq=f;window._lwc.fullRender();return null;}",
    Output("chart-freq-dummy", "data"),
    Input("chart-freq", "value"),
    prevent_initial_call=True,
)
clientside_callback(
    "function(s){if(!window._lwcState||!window._lwc)return null;window._lwcState.logScale=s==='log';window._lwc.fullRender();return null;}",
    Output("chart-scale-dummy", "data"),
    Input("chart-yscale", "value"),
    prevent_initial_call=True,
)
clientside_callback(
    "function(v){if(!window._lwcState||!window._lwc)return null;window._lwcState.volumeEnabled=!!(v&&v.length);window._lwc.fullRender();return null;}",
    Output("chart-volume-dummy", "data"),
    Input("chart-volume-enabled", "value"),
    prevent_initial_call=True,
)
clientside_callback(
    """function(enabled) {
        var _en = !!(enabled && enabled.length);
        if (window._lwcState) window._lwcState.eventsEnabled = _en;
        if (!_en) {
            /* Eliminar del DOM: reposition() no encontrará los elementos y no hará nada */
            document.querySelectorAll('.lwc-ev').forEach(function(el) { el.remove(); });
        } else if (window._lwc && window._lwcCharts && window._lwcPanelDivs && window._lwcState) {
            var st = window._lwcState;
            var evts = st.events || [];
            if (evts.length) {
                var ohlcv = window._lwc.resample(st.rawDaily, st.freq);
                var times = ohlcv.map(function(b) { return b.time; });
                var panels = Object.keys(window._lwcPanelDivs);
                var allDivs = panels.map(function(p) { return window._lwcPanelDivs[p]; }).filter(Boolean);
                setTimeout(function() {
                    window._lwc.drawEventOverlays(window._lwcCharts, allDivs, evts, times);
                }, 0);
            }
        }
        return null;
    }""",
    Output("chart-events-dummy", "data"),
    Input("chart-events-enabled", "value"),
    prevent_initial_call=True,
)

clientside_callback(
    "function(e){if(!window._lwcState||!window._lwc)return null;window._lwcState.regimeEnabled=!!(e&&e.length);window._lwc.fullRender();return null;}",
    Output("chart-regime-dummy", "data"),
    Input("chart-regime-enabled", "value"),
    prevent_initial_call=True,
)

clientside_callback(
    "function(e){if(!window._lwcState||!window._lwc)return null;window._lwcState.ddEnabled=!!(e&&e.length);window._lwc.fullRender();return null;}",
    Output("chart-dd-dummy", "data"),
    Input("chart-dd-enabled", "value"),
    prevent_initial_call=True,
)

clientside_callback(
    "function(e){if(!window._lwcState||!window._lwc)return null;window._lwcState.volEnabled=!!(e&&e.length);window._lwc.fullRender();return null;}",
    Output("chart-vol-dummy", "data"),
    Input("chart-vol-enabled", "value"),
    prevent_initial_call=True,
)

# ─── Clientside: actualiza _lwcState cuando llegan los datos lazy del servidor ──

clientside_callback(
    "function(d){if(!window._lwcState||!window._lwc||!d)return null;window._lwcState.regimeZones=d;window._lwc.fullRender();return null;}",
    Output("chart-regime-data-dummy", "data"),
    Input("chart-regime-data", "data"),
    prevent_initial_call=True,
)

clientside_callback(
    "function(d){if(!window._lwcState||!window._lwc||!d)return null;window._lwcState.volZones=d;window._lwc.fullRender();return null;}",
    Output("chart-vol-data-dummy", "data"),
    Input("chart-vol-data", "data"),
    prevent_initial_call=True,
)

clientside_callback(
    "function(d){if(!window._lwcState||!window._lwc||!d)return null;window._lwcState.ddEvents=d;window._lwc.fullRender();return null;}",
    Output("chart-dd-data-dummy", "data"),
    Input("chart-dd-data", "data"),
    prevent_initial_call=True,
)

# ─── Estrategia: toggle/controles y datos lazy, sin round-trip ────────────────
# El orden posicional de los Inputs replica _SIM_CONTROL_IDS / buildSpec.

clientside_callback(
    """function(en, entScOn, entSc, entPctOn, entPct,
                xsAbsOn, xsAbs, xsAbsUpOn, xsAbsUp,
                xsDentOn, xsDent, xsDmaxOn, xsDmax,
                xsMakOn, xsMak, xsPctOn, xsPct,
                capBarsOn, capBars, capSlOn, capSl, capTsOn, capTs,
                capTpOn, capTp, rearmOn, coolOn, cool) {
        if (!window._lwcState || !window._lwc) return null;
        var st = window._lwcState;
        st.strategyEnabled = !!(en && en.length);
        st.strategySpec = window._lwc.buildSpec(
            entScOn, entSc, entPctOn, entPct,
            xsAbsOn, xsAbs, xsAbsUpOn, xsAbsUp,
            xsDentOn, xsDent, xsDmaxOn, xsDmax,
            xsMakOn, xsMak, xsPctOn, xsPct,
            capBarsOn, capBars, capSlOn, capSl, capTsOn, capTs,
            capTpOn, capTp, rearmOn, coolOn, cool);
        window._lwc.fullRender();
        return null;
    }""",
    Output("chart-strategy-dummy", "data"),
    Input("chart-strategy-enabled", "value"),
    *_sim_control_deps(Input),
    prevent_initial_call=True,
)

clientside_callback(
    "function(d){if(!window._lwcState||!window._lwc||!d)return null;window._lwcState.strategyData=d;window._lwc.fullRender();return null;}",
    Output("chart-strategy-data-dummy", "data"),
    Input("chart-strategy-data", "data"),
    prevent_initial_call=True,
)


_REGIME_LABELS = {
    "bullish_nascent_strong": ("Alcista naciente fuerte", "#66bb6a"),
    "bullish_nascent":        ("Alcista naciente",        "#a5d6a7"),
    "bullish_strong":         ("Alcista fuerte",          "#2e7d32"),
    "bullish":                ("Alcista",                 "#4caf50"),
    "lateral_nascent":        ("Lateral naciente",        "#90caf9"),
    "lateral":                ("Lateral",                 "#6495ed"),
    "bearish_nascent_strong": ("Bajista naciente fuerte", "#ef5350"),
    "bearish_nascent":        ("Bajista naciente",        "#ef9a9a"),
    "bearish_strong":         ("Bajista fuerte",          "#b71c1c"),
    "bearish":                ("Bajista",                 "#ef5350"),
}


# ─── Etiqueta de régimen actual junto al toggle ────────────────────────────────
@callback(
    Output("chart-regime-label", "children"),
    Output("chart-regime-label", "style"),
    Input("chart-data", "data"),
    Input("chart-freq", "value"),
    prevent_initial_call=True,
)
def update_regime_label(chart_data, freq):
    if not chart_data:
        return "", {"fontSize": "0.68rem"}
    rc = chart_data.get("regime_current", {})
    regime = rc.get(freq or "D")
    if not regime:
        return "", {"fontSize": "0.68rem"}
    label, color = _REGIME_LABELS.get(regime, (regime.capitalize(), "#aaa"))
    return f"({label})", {"fontSize": "0.68rem", "color": color, "fontWeight": "bold"}


_VOL_LABELS_ES = {
    f"{vr}_{dr}": (f"{vl} | {dl}", clr)
    for (vr, vl, clr) in [
        ("extrema", "Extrema", "#ef5350"),
        ("alta",    "Alta",    "#ff9800"),
        ("normal",  "Normal",  "#90a4ae"),
        ("baja",    "Baja",    "#42a5f5"),
    ]
    for dr, dl in [("larga", "Larga"), ("media", "Media"), ("corta", "Corta")]
}


@callback(
    Output("chart-vol-label", "children"),
    Output("chart-vol-label", "style"),
    Input("chart-data", "data"),
    Input("chart-freq", "value"),
    prevent_initial_call=True,
)
def update_vol_label(chart_data, freq):
    if not chart_data:
        return "", {"fontSize": "0.68rem"}
    vc = chart_data.get("vol_current", {})
    vol = vc.get(freq or "D")
    if not vol:
        return "", {"fontSize": "0.68rem"}
    label, color = _VOL_LABELS_ES.get(vol, (vol.replace("_", " ").capitalize(), "#aaa"))
    return f"({label})", {"fontSize": "0.68rem", "color": color, "fontWeight": "bold"}


clientside_callback(
    "function(e){if(!window._lwcState||!window._lwc)return null;window._lwcState.srPivotEnabled=!!(e&&e.length);window._lwc.fullRender();return null;}",
    Output("chart-sr-pivot-dummy", "data"),
    Input("chart-sr-pivot-enabled", "value"),
    prevent_initial_call=True,
)


def _fmt_sr_label(resist_pct, support_pct):
    parts = []
    if resist_pct is not None:
        parts.append(html.Span(f"↑+{resist_pct:.1f}%", style={"color": "#f87171"}))
    if support_pct is not None:
        parts.append(html.Span(f" ↓{support_pct:.1f}%", style={"color": "#4ade80"}))
    return parts or ""


@callback(
    Output("chart-sr-pivot-label", "children"),
    Input("chart-data", "data"),
    prevent_initial_call=True,
)
def update_sr_pivot_label(chart_data):
    if not chart_data:
        return ""
    p = chart_data.get("sr_pivots") or {}
    return _fmt_sr_label(p.get("nearest_resist_pct"), p.get("nearest_support_pct"))




# ─── Actualizar período de SMA-1 / EMA-1 al cambiar activo o frecuencia ──────
def _ma_dist_label(raw_daily: list, period: int, kind: str) -> str:
    """Calcula la distancia % entre el precio actual y la SMA/EMA del período dado."""
    if not raw_daily or not period or period < 2:
        return ""
    closes = [b["close"] for b in raw_daily if b.get("close") is not None]
    if len(closes) < period:
        return ""
    last_close = closes[-1]
    if kind == "sma":
        ma_val = sum(closes[-period:]) / period
    else:
        k = 2 / (period + 1)
        ema = closes[0]
        for c in closes[1:]:
            ema = c * k + ema * (1 - k)
        ma_val = ema
    if not ma_val:
        return ""
    pct = (last_close - ma_val) / ma_val * 100
    sign = "+" if pct >= 0 else ""
    return f"{sign}{pct:.1f}%"


# Actualiza sólo los períodos óptimos de SMA-1 / EMA-1 al cambiar activo o frecuencia.
@callback(
    Output("chart-ind-sma-1-period", "value"),
    Output("chart-ind-ema-1-period", "value"),
    Input("chart-data", "data"),
    Input("chart-freq", "value"),
    prevent_initial_call=True,
)
def apply_best_ma(chart_data, freq):
    _SMA_DEFAULT = 20
    _EMA_DEFAULT = 9
    if not chart_data:
        return _SMA_DEFAULT, _EMA_DEFAULT
    best_ma = chart_data.get("best_ma", {})
    fd = best_ma.get(freq or "D", {})
    return fd.get("sma") or _SMA_DEFAULT, fd.get("ema") or _EMA_DEFAULT


# Recalcula los 6 labels de distancia % cada vez que cambia cualquier período o el activo.
@callback(
    Output("chart-sma-best-label", "children"),
    Output("chart-sma-2-label",    "children"),
    Output("chart-sma-3-label",    "children"),
    Output("chart-ema-best-label", "children"),
    Output("chart-ema-2-label",    "children"),
    Output("chart-ema-3-label",    "children"),
    Input("chart-data", "data"),
    Input("chart-freq", "value"),
    Input("chart-ind-sma-1-period", "value"),
    Input("chart-ind-sma-2-period", "value"),
    Input("chart-ind-sma-3-period", "value"),
    Input("chart-ind-ema-1-period", "value"),
    Input("chart-ind-ema-2-period", "value"),
    Input("chart-ind-ema-3-period", "value"),
    prevent_initial_call=True,
)
def update_ma_dist_labels(chart_data, freq, s1, s2, s3, e1, e2, e3):
    if not chart_data:
        return "", "", "", "", "", ""
    raw  = chart_data.get("raw_daily", [])
    mult = {"D": 1, "W": 5, "M": 21}.get(freq or "D", 1)
    def d(period, kind):
        return _colored_dist(_ma_dist_label(raw, (period or 1) * mult, kind))
    return d(s1, "sma"), d(s2, "sma"), d(s3, "sma"), d(e1, "ema"), d(e2, "ema"), d(e3, "ema")


def _colored_dist(label: str):
    if not label:
        return ""
    color = "#4ade80" if label.startswith("+") else "#f87171"
    return html.Span(label, style={"color": color, "fontSize": "0.68rem"})


# ─── P&F clásico (Plotly): alterna visibilidad con el gráfico lightweight ────

_LWC_STYLE = {"backgroundColor": "#1e1e1e", "padding": "8px", "borderRadius": "4px"}


@callback(
    Output("pnf-graph", "figure"),
    Output("pnf-graph", "style"),
    Output("lwc-container", "style"),
    Input("chart-type", "value"),
    Input("analysis-asset-select", "value"),
    prevent_initial_call=True,
)
def toggle_pnf_classic(chart_type, asset_id):
    if chart_type != "pnf_classic":
        return no_update, {"display": "none"}, _LWC_STYLE
    if not asset_id:
        return no_update, {"display": "none"}, _LWC_STYLE

    from app.services import pnf_service
    df = get_prices_df(int(asset_id))
    if df.empty:
        return no_update, {"display": "none"}, _LWC_STYLE

    fig = pnf_service.build_pnf_figure(df)
    return (
        fig,
        {"display": "block", "height": "calc(100vh - 230px)"},
        {**_LWC_STYLE, "display": "none"},
    )
