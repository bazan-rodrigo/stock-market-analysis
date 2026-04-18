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
from dash import Input, Output, State, callback, clientside_callback, no_update, callback_context

import pandas as pd

from app.services.asset_service import get_assets
from app.services.price_service import get_prices_df
import app.services.event_service as event_svc


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
_COLLAPSIBLE = {"bollinger", "rsi", "macd", "stochastic", "atr"}  # tienen params div

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
            fields = f"enabled: {en}"
            for pname, _ in params:
                fields += f", {pname}: ind_{name}_{slot}_{pname}"
            slots_js.append("{" + fields + "}")
        lines.append(f"    {name}: [{', '.join(slots_js)}]")
    return "{\n" + ",\n".join(lines) + "\n  }"


def _t(d):
    return str(d)[:10]


# ─── Carga de activos ─────────────────────────────────────────────────────────
@callback(
    Output("chart-asset-select", "options"),
    Input("chart-asset-select", "id"),
)
def load_chart_assets(_):
    assets = get_assets(only_active=True)
    return [{"label": f"{a.ticker} - {a.name or a.ticker}", "value": a.id} for a in assets]


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
    Input("chart-asset-select", "value"),
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

    # Cargar eventos y snapshot
    from app.database import get_session
    from app.models import Asset, ScreenerSnapshot
    db = get_session()
    asset = db.query(Asset).filter(Asset.id == int(asset_id)).first()
    country_id = asset.country_id if asset else None
    events = event_svc.get_events_for_asset(int(asset_id), country_id)

    import json as _json
    from app.models import RegimeConfig, DrawdownConfig
    regime_cfg = db.query(RegimeConfig).filter(RegimeConfig.id == 1).first()
    regime_ema_periods = {
        "D": regime_cfg.ema_period_d if regime_cfg else 200,
        "W": regime_cfg.ema_period_w if regime_cfg else 50,
        "M": regime_cfg.ema_period_m if regime_cfg else 20,
    }

    snap = db.query(ScreenerSnapshot).filter(ScreenerSnapshot.asset_id == int(asset_id)).first()
    best_ma = {}
    regime_zones = {}
    regime_current = {}
    dd_events = []
    if snap:
        best_ma = {
            "D": {"sma": snap.best_sma_d, "ema": snap.best_ema_d},
            "W": {"sma": snap.best_sma_w, "ema": snap.best_ema_w},
            "M": {"sma": snap.best_sma_m, "ema": snap.best_ema_m},
        }
        regime_zones = {
            "D": _json.loads(snap.regime_zones_d) if snap.regime_zones_d else [],
            "W": _json.loads(snap.regime_zones_w) if snap.regime_zones_w else [],
            "M": _json.loads(snap.regime_zones_m) if snap.regime_zones_m else [],
        }
        regime_current = {
            "D": snap.regime_d,
            "W": snap.regime_w,
            "M": snap.regime_m,
        }
        dd_events = _json.loads(snap.dd_events) if snap.dd_events else []

    return {"raw_daily": raw_daily, "asset_id": int(asset_id), "events": events,
            "best_ma": best_ma, "regime_zones": regime_zones,
            "regime_current": regime_current,
            "regime_ema_periods": regime_ema_periods,
            "dd_events": dd_events}, ""


# ─── JS compartido ───────────────────────────────────────────────────────────
_JS_RENDER = f"""
function(chartData, chartType, freq, logScale, volumeEnabled, eventsEnabled, regimeEnabled, ddEnabled, {_JS_ARGS_STR}) {{

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
    var tr = [0];
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
    if (spec.priceLines) spec.priceLines.forEach(function(pl) {{
      s.createPriceLine({{price: pl.price, color: pl.color, lineWidth: 1,
        lineStyle: LightweightCharts.LineStyle.Dotted,
        axisLabelVisible: true, title: String(pl.price)}});
    }});
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

    /* Paneles activos */
    var showVolume = !!st.volumeEnabled;
    ['rsi', 'macd', 'stochastic', 'atr', 'drawdown'].forEach(function(n) {{
      if (ip[n] && ip[n][0].enabled) activeSeps.push(n);
    }});

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
    if (st.chartType === 'candlestick') {{
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
    ip.sma.forEach(function(s, i) {{
      if (!s.enabled) return;
      var vals = window._lwc.sma(close, s.period);
      window._lwc.addSeries(pc, {{type:'line', name:'SMA '+s.period,
        color: smaColors[i], lineWidth: 1.5,
        data: toData(vals)}});
    }});

    /* EMA */
    var emaColors = ['#00bcd4','#9c27b0','#ffeb3b'];
    ip.ema.forEach(function(s, i) {{
      if (!s.enabled) return;
      var vals = window._lwc.ema(close, s.period);
      window._lwc.addSeries(pc, {{type:'line', name:'EMA '+s.period,
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

    /* Marcadores de drawdown */
    if (st.ddEnabled && st.ddEvents && st.ddEvents.length && window._lwcPriceSeries) {{
      /* Mapea fecha exacta al tiempo de barra más cercano (necesario para S/M) */
      function nearestBarTime(dateStr) {{
        for (var i = 0; i < times.length; i++) {{
          if (times[i] >= dateStr) return times[i];
        }}
        return times[times.length - 1];
      }}
      var markers = [];
      st.ddEvents.forEach(function(ev) {{
        if (!ev.trough) return;
        markers.push({{
          time: nearestBarTime(ev.trough),
          position: 'belowBar',
          color: '#ef5350',
          shape: 'arrowUp',
          text: Math.abs(ev.depth).toFixed(1) + '%',
          size: 1,
        }});
      }});
      if (markers.length) {{
        markers.sort(function(a, b) {{ return a.time < b.time ? -1 : 1; }});
        window._lwcPriceSeries.setMarkers(markers);
      }}
    }}

    if (window.ResizeObserver) {{
      window._lwcResizeObs = new ResizeObserver(function() {{
        var w = container.clientWidth;
        window._lwcCharts.forEach(function(c) {{ c.applyOptions({{width: w}}); }});
      }});
      window._lwcResizeObs.observe(container);
    }}
  }};

  /* ── Actualizar estado y renderizar ── */
  var indParams = {_js_ind_params()};

  window._lwcState = {{
    rawDaily:          chartData.raw_daily,
    assetId:           chartData.asset_id,
    events:            chartData.events            || [],
    regimeZones:       chartData.regime_zones      || {{}},
    regimeEmaPeriods:  chartData.regime_ema_periods || {{}},
    ddEvents:          chartData.dd_events          || [],
    eventsEnabled:     eventsEnabled  !== false,
    regimeEnabled:     regimeEnabled  === true,
    ddEnabled:         ddEnabled      === true,
    indParams:         indParams,
    volumeEnabled:     volumeEnabled  !== false,
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
    "function(v){if(!window._lwcState||!window._lwc)return null;window._lwcState.volumeEnabled=v!==false;window._lwc.fullRender();return null;}",
    Output("chart-volume-dummy", "data"),
    Input("chart-volume-enabled", "value"),
    prevent_initial_call=True,
)
clientside_callback(
    """function(enabled) {
        if (window._lwcState) window._lwcState.eventsEnabled = enabled !== false;
        if (enabled === false) {
            document.querySelectorAll('.lwc-ev').forEach(function(el) { el.style.display = 'none'; });
        } else {
            var existing = document.querySelectorAll('.lwc-ev');
            if (existing.length > 0) {
                existing.forEach(function(el) { el.style.display = ''; });
            } else if (window._lwc && window._lwcCharts && window._lwcPanelDivs && window._lwcState) {
                /* Los overlays fueron borrados por un re-render: reconstruir */
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
        }
        return null;
    }""",
    Output("chart-events-dummy", "data"),
    Input("chart-events-enabled", "value"),
    prevent_initial_call=True,
)

clientside_callback(
    "function(e){if(!window._lwcState||!window._lwc)return null;window._lwcState.regimeEnabled=e===true;window._lwc.fullRender();return null;}",
    Output("chart-regime-dummy", "data"),
    Input("chart-regime-enabled", "value"),
    prevent_initial_call=True,
)

clientside_callback(
    "function(e){if(!window._lwcState||!window._lwc)return null;window._lwcState.ddEnabled=e===true;window._lwc.fullRender();return null;}",
    Output("chart-dd-dummy", "data"),
    Input("chart-dd-enabled", "value"),
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


# ─── Actualizar SMA-1 / EMA-1 con la MA más respetada ────────────────────────
@callback(
    Output("chart-ind-sma-1-period",  "value"),
    Output("chart-ind-ema-1-period",  "value"),
    Output("chart-ind-sma-1-enabled", "value"),
    Output("chart-ind-ema-1-enabled", "value"),
    Input("chart-data", "data"),
    Input("chart-freq", "value"),
    prevent_initial_call=True,
)
def apply_best_ma(chart_data, freq):
    if not chart_data:
        return no_update, no_update, no_update, no_update
    best_ma = chart_data.get("best_ma", {})
    fd = best_ma.get(freq or "D", {})
    sma = fd.get("sma")
    ema = fd.get("ema")
    if sma is None and ema is None:
        return no_update, no_update, no_update, no_update
    return (
        sma if sma else no_update,
        ema if ema else no_update,
        bool(sma),
        bool(ema),
    )
