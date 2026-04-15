"""
Callbacks del grafico tecnico.
Produce un dict JSON con datos de precios e indicadores para Lightweight Charts (TradingView).
El render lo ejecuta un clientside_callback con la logica JS inline.
"""
from datetime import date

import pandas as pd
from dash import Input, Output, State, callback, clientside_callback, no_update

from app.indicators.base import PANEL_OVERLAY, PANEL_SEPARATE
from app.indicators.registry import all_indicators, overlay_indicators, separate_indicators
from app.services.asset_service import get_assets
from app.services.price_service import get_prices_df


# -- Paleta de colores para series --------------------------------------------
_PALETTE = [
    "#ff9800", "#00bcd4", "#9c27b0", "#f44336", "#4caf50",
    "#ffeb3b", "#e91e63", "#ff5722", "#00e5ff", "#cddc39",
]


def _series_color(name, index=0):
    if name.startswith("SMA"):       return "#ff9800"
    if name.startswith("EMA"):       return "#00bcd4"
    if "Superior" in name:           return "#7e57c2"
    if "Inferior" in name:           return "#7e57c2"
    if "Media" in name:              return "#e91e63"
    if name.startswith("RSI"):       return "#9c27b0"
    if name == "MACD":               return "#2196f3"
    if "Se" in name and "al" in name: return "#ff5722"  # Senal MACD
    if name.startswith("%K"):        return "#ffeb3b"
    if name.startswith("%D"):        return "#ff9800"
    if name.startswith("ATR"):       return "#00bcd4"
    return _PALETTE[index % len(_PALETTE)]


def _t(d):
    return str(d)[:10]


def _build_chart_data(df, chart_type, yscale, indicator_config):
    panels = ["price", "volume"]
    series = []

    # Precio
    if chart_type == "candlestick":
        series.append({
            "type": "candlestick",
            "panel": "price",
            "data": [
                {"time": _t(row.date), "open": row.open, "high": row.high,
                 "low": row.low, "close": row.close}
                for row in df.itertuples(index=False)
            ],
        })
    else:
        series.append({
            "type": "line", "panel": "price", "name": "Precio", "color": "#2196f3",
            "data": [{"time": _t(row.date), "value": row.close}
                     for row in df.itertuples(index=False)],
        })

    # Overlay indicators
    color_idx = 0
    for cfg in indicator_config.values():
        if not cfg["enabled"] or cfg["indicator"].PANEL != PANEL_OVERLAY:
            continue
        ind = cfg["indicator"]
        for sname, s in ind.compute(df, **cfg["params"]).items():
            series.append({
                "type": "line", "panel": "price", "name": sname,
                "color": _series_color(sname, color_idx),
                "data": [{"time": _t(t), "value": float(v)}
                         for t, v in zip(df["date"], s) if pd.notna(v)],
            })
            color_idx += 1

    # Volumen
    series.append({
        "type": "histogram", "panel": "volume", "name": "Volumen",
        "data": [
            {"time": _t(row.date), "value": float(row.volume or 0),
             "color": "#00b050" if row.close >= row.open else "#ef5350"}
            for row in df.itertuples(index=False)
        ],
    })

    # Indicadores en paneles separados
    for cfg in indicator_config.values():
        if not cfg["enabled"] or cfg["indicator"].PANEL != PANEL_SEPARATE:
            continue
        ind = cfg["indicator"]
        panel_id = ind.NAME
        if panel_id not in panels:
            panels.append(panel_id)

        ref_lines = {}
        if ind.NAME == "rsi":
            ref_lines["RSI"] = [{"price": 70, "color": "#ef5350"}, {"price": 30, "color": "#4caf50"}]
        elif ind.NAME == "stochastic":
            ref_lines["%K"] = [{"price": 80, "color": "#ef5350"}, {"price": 20, "color": "#4caf50"}]

        for i, (sname, s) in enumerate(ind.compute(df, **cfg["params"]).items()):
            is_hist = (ind.NAME == "macd" and "Histograma" in sname)
            entry = {"panel": panel_id, "name": sname, "color": _series_color(sname, i)}
            if is_hist:
                entry["type"] = "histogram"
                entry["data"] = [
                    {"time": _t(t), "value": float(v) if pd.notna(v) else 0.0,
                     "color": "#00b050" if (pd.notna(v) and v >= 0) else "#ef5350"}
                    for t, v in zip(df["date"], s)
                ]
            else:
                entry["type"] = "line"
                entry["data"] = [{"time": _t(t), "value": float(v)}
                                 for t, v in zip(df["date"], s) if pd.notna(v)]
                for key, lines in ref_lines.items():
                    if sname.startswith(key):
                        entry["priceLines"] = lines
                        break
            series.append(entry)

    return {"panels": panels, "series": series, "log_scale": yscale == "log"}


# -- Carga de activos ---------------------------------------------------------
@callback(
    Output("chart-asset-select", "options"),
    Input("chart-asset-select", "id"),
)
def load_chart_assets(_):
    assets = get_assets(only_active=True)
    return [{"label": f"{a.ticker} - {a.name or a.ticker}", "value": a.id} for a in assets]


# -- Mostrar/ocultar parametros de indicadores --------------------------------
for _ind in all_indicators():
    _ind_id = _ind.NAME

    @callback(
        Output(f"chart-ind-{_ind_id}-params", "style"),
        Input(f"chart-ind-{_ind_id}-enabled", "value"),
    )
    def _toggle_params(enabled, ind_id=_ind_id):
        return {"display": "block"} if enabled else {"display": "none"}


# -- Callback principal: construir JSON para LWC ------------------------------
def _build_inputs():
    inputs = [Input("chart-btn-update", "n_clicks")]
    states = [
        State("chart-asset-select", "value"),
        State("chart-date-from", "value"),
        State("chart-date-to", "value"),
        State("chart-type", "value"),
        State("chart-yscale", "value"),
    ]
    for ind in all_indicators():
        states.append(State(f"chart-ind-{ind.NAME}-enabled", "value"))
        for p in ind.PARAMS:
            states.append(State(f"chart-ind-{ind.NAME}-{p.name}", "value"))
    return inputs, states


_inputs, _states = _build_inputs()


@callback(
    Output("chart-data", "data"),
    *_inputs,
    *_states,
    prevent_initial_call=True,
)
def update_chart_data(n_clicks, *args):
    idx = 0
    asset_id   = args[idx]; idx += 1
    date_from  = args[idx]; idx += 1
    date_to    = args[idx]; idx += 1
    chart_type = args[idx]; idx += 1
    yscale     = args[idx]; idx += 1

    indicator_config = {}
    for ind in all_indicators():
        enabled = args[idx]; idx += 1
        params = {}
        for p in ind.PARAMS:
            params[p.name] = args[idx]; idx += 1
        indicator_config[ind.NAME] = {"enabled": bool(enabled), "params": params, "indicator": ind}

    if not asset_id:
        return no_update

    df = get_prices_df(int(asset_id))
    if df.empty:
        return no_update

    if date_from:
        df = df[df["date"] >= date.fromisoformat(date_from)]
    if date_to:
        df = df[df["date"] <= date.fromisoformat(date_to)]

    if df.empty:
        return no_update

    return _build_chart_data(df, chart_type, yscale, indicator_config)


# -- Clientside callback: render en Lightweight Charts (logica inline) --------
_LWC_JS = """
function(chartData) {
    if (!chartData) return window.dash_clientside.no_update;

    var container = document.getElementById('lwc-container');
    if (!container) return null;

    // Destruir charts previos
    if (window._lwcCharts) {
        window._lwcCharts.forEach(function(c) { try { c.remove(); } catch(e) {} });
    }
    if (window._lwcResizeObs) { window._lwcResizeObs.disconnect(); }
    window._lwcCharts = [];
    container.innerHTML = '';

    var panels = chartData.panels || ['price', 'volume'];
    var totalH = container.clientHeight || 600;
    var totalW = container.clientWidth  || 800;

    // Calcular alturas
    var separates = panels.filter(function(p) { return p !== 'price' && p !== 'volume'; });
    var ns = separates.length;
    var heights = {};
    if (ns === 0) {
        heights['price']  = Math.round(totalH * 0.88);
        heights['volume'] = totalH - heights['price'];
    } else {
        var priceH  = Math.round(totalH * 0.52);
        var volumeH = Math.round(totalH * 0.08);
        var sepH    = Math.floor((totalH - priceH - volumeH) / ns);
        heights['price']  = priceH;
        heights['volume'] = volumeH;
        separates.forEach(function(p) { heights[p] = Math.max(sepH, 60); });
    }

    // Crear un chart por panel
    var panelCharts = {};
    panels.forEach(function(panel, idx) {
        var div = document.createElement('div');
        div.style.cssText = 'width:100%;overflow:hidden;';
        container.appendChild(div);

        var isLast = (idx === panels.length - 1);
        var chart = LightweightCharts.createChart(div, {
            width:  totalW,
            height: heights[panel] || 80,
            layout: {
                background: { type: 'solid', color: '#1e1e1e' },
                textColor: '#dee2e6',
                fontSize: 11
            },
            grid: {
                vertLines: { color: '#2a2a2a' },
                horzLines: { color: '#2a2a2a' }
            },
            crosshair: { mode: LightweightCharts.CrosshairMode.Normal },
            rightPriceScale: { borderColor: '#444', scaleMargins: { top: 0.05, bottom: 0.05 } },
            timeScale: { borderColor: '#444', visible: isLast, timeVisible: false },
            handleScroll: true,
            handleScale:  true
        });

        panelCharts[panel] = chart;
        window._lwcCharts.push(chart);
    });

    // Escala logaritmica
    if (chartData.log_scale && panelCharts['price']) {
        panelCharts['price'].priceScale('right').applyOptions({
            mode: LightweightCharts.PriceScaleMode.Logarithmic
        });
    }

    // Agregar series
    (chartData.series || []).forEach(function(spec) {
        var chart = panelCharts[spec.panel];
        if (!chart) return;
        var series = null;

        if (spec.type === 'candlestick') {
            series = chart.addCandlestickSeries({
                upColor: '#00b050', downColor: '#ef5350',
                borderUpColor: '#00b050', borderDownColor: '#ef5350',
                wickUpColor: '#00b050', wickDownColor: '#ef5350'
            });
        } else if (spec.type === 'line') {
            series = chart.addLineSeries({
                color: spec.color || '#2196f3',
                lineWidth: spec.lineWidth || 1.5,
                title: spec.name || '',
                lineStyle: spec.dashed
                    ? LightweightCharts.LineStyle.Dashed
                    : LightweightCharts.LineStyle.Solid,
                priceLineVisible: false,
                lastValueVisible: true
            });
        } else if (spec.type === 'histogram') {
            series = chart.addHistogramSeries({
                title: spec.name || '',
                color: spec.color || '#26a69a',
                priceFormat: spec.panel === 'volume' ? { type: 'volume' } : { type: 'price', precision: 4 },
                priceLineVisible: false,
                lastValueVisible: spec.panel !== 'volume'
            });
        }

        if (!series) return;
        if (spec.data && spec.data.length) series.setData(spec.data);

        if (spec.priceLines) {
            spec.priceLines.forEach(function(pl) {
                series.createPriceLine({
                    price: pl.price, color: pl.color, lineWidth: 1,
                    lineStyle: LightweightCharts.LineStyle.Dotted,
                    axisLabelVisible: true, title: String(pl.price)
                });
            });
        }
    });

    // Ajustar y sincronizar
    window._lwcCharts.forEach(function(c) { c.timeScale().fitContent(); });

    if (window._lwcCharts.length > 1) {
        window._lwcCharts.forEach(function(src, i) {
            src.timeScale().subscribeVisibleLogicalRangeChange(function(range) {
                if (!range) return;
                window._lwcCharts.forEach(function(dst, j) {
                    if (i !== j) dst.timeScale().setVisibleLogicalRange(range);
                });
            });
        });
    }

    if (window.ResizeObserver) {
        window._lwcResizeObs = new ResizeObserver(function() {
            var w = container.clientWidth;
            window._lwcCharts.forEach(function(c) { c.applyOptions({ width: w }); });
        });
        window._lwcResizeObs.observe(container);
    }

    return null;
}
"""

clientside_callback(
    _LWC_JS,
    Output("chart-render-dummy", "data"),
    Input("chart-data", "data"),
    prevent_initial_call=True,
)
