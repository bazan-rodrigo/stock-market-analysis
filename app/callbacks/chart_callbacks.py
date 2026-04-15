"""
Callbacks del grafico tecnico.

Arquitectura:
  - Python: calcula raw_daily + TODOS los indicadores con params actuales
  - JS (clientside): maneja frecuencia, tipo de grafico, escala y toggles de
    indicadores sin round-trip al servidor.

Flujo:
  1. Seleccionar activo (o cambiar params) -> Python -> chart-data
  2. chart-data change -> clientside: render completo
  3. Cambiar tipo/frecuencia/escala/indicadores -> clientside: actualiza en lugar
"""
from dash import Input, Output, State, callback, clientside_callback, no_update, callback_context

import pandas as pd

from app.indicators.base import PANEL_OVERLAY, PANEL_SEPARATE
from app.indicators.registry import all_indicators, overlay_indicators, separate_indicators
from app.services.asset_service import get_assets
from app.services.price_service import get_prices_df


# ── Paleta de colores ─────────────────────────────────────────────────────────
_PALETTE = [
    "#ff9800", "#00bcd4", "#9c27b0", "#f44336", "#4caf50",
    "#ffeb3b", "#e91e63", "#ff5722", "#00e5ff", "#cddc39",
]

def _color(name, idx=0):
    if name.startswith("SMA"):        return "#ff9800"
    if name.startswith("EMA"):        return "#00bcd4"
    if "Superior" in name:            return "#7e57c2"
    if "Inferior" in name:            return "#7e57c2"
    if "Media" in name:               return "#e91e63"
    if name.startswith("RSI"):        return "#9c27b0"
    if name == "MACD":                return "#2196f3"
    if "Se" in name and "al" in name: return "#ff5722"
    if name.startswith("%K"):         return "#ffeb3b"
    if name.startswith("%D"):         return "#ff9800"
    if name.startswith("ATR"):        return "#00bcd4"
    return _PALETTE[idx % len(_PALETTE)]

def _t(d): return str(d)[:10]


# ── Carga de activos ──────────────────────────────────────────────────────────
@callback(
    Output("chart-asset-select", "options"),
    Input("chart-asset-select", "id"),
)
def load_chart_assets(_):
    assets = get_assets(only_active=True)
    return [{"label": f"{a.ticker} - {a.name or a.ticker}", "value": a.id} for a in assets]


# ── Mostrar/ocultar params de indicadores ─────────────────────────────────────
for _ind in all_indicators():
    _ind_id = _ind.NAME
    @callback(
        Output(f"chart-ind-{_ind_id}-params", "style"),
        Input(f"chart-ind-{_ind_id}-enabled", "value"),
    )
    def _toggle_params(enabled, ind_id=_ind_id):
        return {"display": "flex"} if enabled else {"display": "none"}


# ── Python: calcula datos al seleccionar activo o cambiar params ──────────────
def _param_inputs():
    return [Input(f"chart-ind-{ind.NAME}-{p.name}", "value")
            for ind in all_indicators() for p in ind.PARAMS]

@callback(
    Output("chart-data", "data"),
    Input("chart-asset-select", "value"),
    *_param_inputs(),
    State("chart-data", "data"),
    prevent_initial_call=True,
)
def load_chart_data(asset_id, *args):
    *param_vals, current_data = args

    if not asset_id:
        return no_update

    asset_changed = any(
        "chart-asset-select" in t["prop_id"]
        for t in callback_context.triggered
    )

    if asset_changed or not current_data or current_data.get("asset_id") != int(asset_id):
        df = get_prices_df(int(asset_id))
        if df.empty:
            return no_update
        raw_daily = [
            {"time": _t(row.date), "open": row.open, "high": row.high,
             "low": row.low,  "close": row.close, "volume": float(row.volume or 0)}
            for row in df.itertuples(index=False)
        ]
    else:
        raw_daily = current_data["raw_daily"]
        df = pd.DataFrame([
            {"date": pd.Timestamp(r["time"]),
             "open": r["open"], "high": r["high"],
             "low": r["low"],  "close": r["close"], "volume": r.get("volume", 0)}
            for r in raw_daily
        ])

    # Calcular TODOS los indicadores con los params actuales
    indicator_series = []
    idx = 0
    for ind in all_indicators():
        params = {}
        for p in ind.PARAMS:
            v = param_vals[idx]
            params[p.name] = v if v is not None else p.default
            idx += 1

        ref_lines_map = {}
        if ind.NAME == "rsi":
            ref_lines_map["RSI"] = [{"price": 70, "color": "#ef5350"}, {"price": 30, "color": "#4caf50"}]
        elif ind.NAME == "stochastic":
            ref_lines_map["%K"] = [{"price": 80, "color": "#ef5350"}, {"price": 20, "color": "#4caf50"}]

        for i, (sname, s) in enumerate(ind.compute(df, **params).items()):
            is_hist = (ind.NAME == "macd" and "Histograma" in sname)
            entry = {
                "ind_id": ind.NAME,
                "panel":  ind.PANEL,
                "sid":    f"{ind.NAME}_{i}",
                "name":   sname,
                "type":   "histogram" if is_hist else "line",
                "color":  _color(sname, i),
            }
            if is_hist:
                entry["data"] = [
                    {"time": _t(t), "value": float(v) if pd.notna(v) else 0.0,
                     "color": "#00b050" if (pd.notna(v) and v >= 0) else "#ef5350"}
                    for t, v in zip(df["date"], s)
                ]
            else:
                entry["data"] = [
                    {"time": _t(t), "value": float(v)}
                    for t, v in zip(df["date"], s) if pd.notna(v)
                ]
                for key, lines in ref_lines_map.items():
                    if sname.startswith(key):
                        entry["price_lines"] = lines
                        break

            indicator_series.append(entry)

    return {"raw_daily": raw_daily, "indicator_series": indicator_series, "asset_id": int(asset_id)}


# ── JS compartido ─────────────────────────────────────────────────────────────
# Toda la logica de render se define en el primer clientside_callback y queda
# disponible via window._lwc para los callbacks de tipo/freq/escala/indicadores.

_IND_IDS = [ind.NAME for ind in all_indicators()]
_IND_IDS_JS = str(_IND_IDS).replace("'", '"')

_JS_RENDER = f"""
function(chartData, chartType, freq, logScale, {", ".join(f"en_{n}" for n in _IND_IDS)}) {{

    /* ---- setup compartido (solo la primera vez) ---- */
    if (!window._lwc) {{ window._lwc = {{}}; }}

    window._lwc.IND_IDS = {_IND_IDS_JS};

    window._lwc.resample = function(daily, freq) {{
        if (freq === 'D') return daily;
        var groups = {{}}, keys = [];
        daily.forEach(function(b) {{
            var key;
            if (freq === 'W') {{
                var d = new Date(b.time + 'T00:00:00Z');
                var dow = d.getUTCDay() || 7;
                d.setUTCDate(d.getUTCDate() - (dow - 1));
                key = d.toISOString().slice(0, 10);
            }} else {{
                key = b.time.slice(0, 7) + '-01';
            }}
            if (!groups[key]) {{
                groups[key] = {{time:key, open:b.open, high:b.high, low:b.low, close:b.close, volume:b.volume||0}};
                keys.push(key);
            }} else {{
                var g = groups[key];
                if (b.high > g.high) g.high = b.high;
                if (b.low  < g.low)  g.low  = b.low;
                g.close  = b.close;
                g.volume = (g.volume||0) + (b.volume||0);
            }}
        }});
        return keys.sort().map(function(k) {{ return groups[k]; }});
    }};

    window._lwc.buildChart = function(panel, height, totalW, isLast) {{
        var div = document.createElement('div');
        div.style.cssText = 'width:100%;overflow:hidden;';
        document.getElementById('lwc-container').appendChild(div);
        var c = LightweightCharts.createChart(div, {{
            width: totalW, height: height,
            layout: {{ background:{{type:'solid',color:'#1e1e1e'}}, textColor:'#dee2e6', fontSize:11 }},
            grid:   {{ vertLines:{{color:'#2a2a2a'}}, horzLines:{{color:'#2a2a2a'}} }},
            crosshair: {{ mode: LightweightCharts.CrosshairMode.Normal }},
            rightPriceScale: {{ borderColor:'#444', scaleMargins:{{top:0.05,bottom:0.05}} }},
            timeScale: {{ borderColor:'#444', visible:isLast, timeVisible:false }},
            handleScroll:true, handleScale:true
        }});
        return c;
    }};

    window._lwc.addSeries = function(chart, spec) {{
        var s;
        if (spec.type === 'candlestick') {{
            s = chart.addCandlestickSeries({{
                upColor:'#00b050', downColor:'#ef5350',
                borderUpColor:'#00b050', borderDownColor:'#ef5350',
                wickUpColor:'#00b050', wickDownColor:'#ef5350'
            }});
        }} else if (spec.type === 'line') {{
            s = chart.addLineSeries({{
                color: spec.color||'#2196f3', lineWidth: spec.lineWidth||1.5,
                title: spec.name||'', priceLineVisible:false, lastValueVisible:true
            }});
        }} else if (spec.type === 'histogram') {{
            s = chart.addHistogramSeries({{
                title: spec.name||'', color: spec.color||'#26a69a',
                priceFormat: spec.panel==='volume' ? {{type:'volume'}} : {{type:'price',precision:4}},
                priceLineVisible:false, lastValueVisible: spec.panel!=='volume'
            }});
        }}
        if (!s) return;
        if (spec.data && spec.data.length) s.setData(spec.data);
        if (spec.price_lines) {{
            spec.price_lines.forEach(function(pl) {{
                s.createPriceLine({{price:pl.price, color:pl.color, lineWidth:1,
                    lineStyle:LightweightCharts.LineStyle.Dotted,
                    axisLabelVisible:true, title:String(pl.price)}});
            }});
        }}
        return s;
    }};

    window._lwc.fullRender = function() {{
        var st = window._lwcState;
        if (!st) return;
        var container = document.getElementById('lwc-container');
        if (!container) return;

        /* Guardar rango visible si es el mismo activo */
        var savedRange = null;
        var sameAsset = (window._lwcLastAssetId !== undefined && window._lwcLastAssetId === st.assetId);
        if (sameAsset && window._lwcCharts && window._lwcCharts.length > 0) {{
            try {{ savedRange = window._lwcCharts[0].timeScale().getVisibleLogicalRange(); }} catch(e) {{}}
        }}
        window._lwcLastAssetId = st.assetId;

        if (window._lwcCharts) window._lwcCharts.forEach(function(c){{try{{c.remove();}}catch(e){{ }}}});
        if (window._lwcResizeObs) window._lwcResizeObs.disconnect();
        window._lwcCharts = [];
        window._lwcPanelCharts = {{}};
        container.innerHTML = '';

        var ohlcv = window._lwc.resample(st.rawDaily, st.freq);
        var totalH = container.clientHeight || 600;
        var totalW = container.clientWidth  || 800;

        // Paneles activos
        var activeSeps = [];
        st.indicatorSeries.forEach(function(spec) {{
            if (st.enabledMap[spec.ind_id] && spec.panel === 'separate') {{
                if (activeSeps.indexOf(spec.ind_id) === -1) activeSeps.push(spec.ind_id);
            }}
        }});
        var panels = ['price', 'volume'].concat(activeSeps);

        // Alturas
        var heights = {{}};
        var ns = activeSeps.length;
        if (ns === 0) {{
            heights.price  = Math.round(totalH * 0.88);
            heights.volume = totalH - heights.price;
        }} else {{
            heights.price  = Math.round(totalH * 0.52);
            heights.volume = Math.round(totalH * 0.08);
            var sepH = Math.floor((totalH - heights.price - heights.volume) / ns);
            activeSeps.forEach(function(p) {{ heights[p] = Math.max(sepH, 60); }});
        }}

        panels.forEach(function(panel, idx) {{
            var c = window._lwc.buildChart(panel, heights[panel]||80, totalW, idx===panels.length-1);
            window._lwcPanelCharts[panel] = c;
            window._lwcCharts.push(c);
        }});

        // Escala log
        if (st.logScale && window._lwcPanelCharts.price) {{
            window._lwcPanelCharts.price.priceScale('right').applyOptions({{
                mode: LightweightCharts.PriceScaleMode.Logarithmic
            }});
        }}

        // Serie de precio
        var pc = window._lwcPanelCharts.price;
        if (st.chartType === 'candlestick') {{
            window._lwc.addSeries(pc, {{type:'candlestick', data:ohlcv}});
        }} else {{
            window._lwc.addSeries(pc, {{type:'line', color:'#2196f3', lineWidth:1.5,
                data: ohlcv.map(function(b){{return{{time:b.time,value:b.close}};}})}});
        }}

        // Volumen
        window._lwc.addSeries(window._lwcPanelCharts.volume, {{
            type:'histogram', panel:'volume',
            data: ohlcv.map(function(b){{
                return{{time:b.time, value:b.volume||0, color:b.close>=b.open?'#00b050':'#ef5350'}};
            }})
        }});

        // Indicadores activos
        st.indicatorSeries.forEach(function(spec) {{
            if (!st.enabledMap[spec.ind_id]) return;
            var panelKey = spec.panel === 'overlay' ? 'price' : spec.ind_id;
            var c = window._lwcPanelCharts[panelKey];
            if (c) window._lwc.addSeries(c, spec);
        }});

        // Sync timescales
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

        if (window.ResizeObserver) {{
            window._lwcResizeObs = new ResizeObserver(function() {{
                var w = container.clientWidth;
                window._lwcCharts.forEach(function(c) {{ c.applyOptions({{width:w}}); }});
            }});
            window._lwcResizeObs.observe(container);
        }}
    }};

    /* ---- llamada principal ---- */
    var enabledMap = {{}};
    var ids = window._lwc.IND_IDS;
    var flags = [{", ".join(f"en_{n}" for n in _IND_IDS)}];
    ids.forEach(function(id, i) {{ enabledMap[id] = !!flags[i]; }});

    window._lwcState = {{
        rawDaily:        chartData.raw_daily,
        indicatorSeries: chartData.indicator_series,
        assetId:         chartData.asset_id,
        enabledMap:      enabledMap,
        chartType:       chartType || 'candlestick',
        freq:            freq      || 'D',
        logScale:        logScale  === 'log'
    }};
    window._lwc.fullRender();
    return null;
}}
"""

# Callback principal: chart-data -> render completo
clientside_callback(
    _JS_RENDER,
    Output("chart-render-dummy", "data"),
    Input("chart-data", "data"),
    State("chart-type", "value"),
    State("chart-freq", "value"),
    State("chart-yscale", "value"),
    *[State(f"chart-ind-{n}-enabled", "value") for n in _IND_IDS],
    prevent_initial_call=True,
)

# Cambio de tipo de grafico (sin round-trip)
clientside_callback(
    """
    function(chartType) {
        if (!window._lwcState || !window._lwc) return null;
        window._lwcState.chartType = chartType;
        window._lwc.fullRender();
        return null;
    }
    """,
    Output("chart-type-dummy", "data"),
    Input("chart-type", "value"),
    prevent_initial_call=True,
)

# Cambio de frecuencia (sin round-trip)
clientside_callback(
    """
    function(freq) {
        if (!window._lwcState || !window._lwc) return null;
        window._lwcState.freq = freq;
        window._lwc.fullRender();
        return null;
    }
    """,
    Output("chart-freq-dummy", "data"),
    Input("chart-freq", "value"),
    prevent_initial_call=True,
)

# Cambio de escala (sin round-trip)
clientside_callback(
    """
    function(logScale) {
        if (!window._lwcState || !window._lwc) return null;
        window._lwcState.logScale = logScale === 'log';
        window._lwc.fullRender();
        return null;
    }
    """,
    Output("chart-scale-dummy", "data"),
    Input("chart-yscale", "value"),
    prevent_initial_call=True,
)

# Toggle de cualquier indicador (sin round-trip)
_enabled_inputs = [Input(f"chart-ind-{n}-enabled", "value") for n in _IND_IDS]
_enabled_args   = ", ".join(f"en_{n}" for n in _IND_IDS)
_map_build_js   = "; ".join(
    f'enabledMap["{n}"] = !!en_{n}'
    for n in _IND_IDS
)

clientside_callback(
    f"""
    function({_enabled_args}) {{
        if (!window._lwcState || !window._lwc) return null;
        var enabledMap = {{}};
        {_map_build_js};
        window._lwcState.enabledMap = enabledMap;
        window._lwc.fullRender();
        return null;
    }}
    """,
    Output("chart-ind-dummy", "data"),
    *_enabled_inputs,
    prevent_initial_call=True,
)
