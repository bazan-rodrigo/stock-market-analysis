/**
 * Lightweight Charts (TradingView) — integración con Dash.
 * Expone window.dashLWC.render, invocada por un clientside_callback de Dash.
 *
 * Contrato de entrada (chartData):
 * {
 *   panels:   string[]           — orden de paneles, p.ej. ["price","volume","rsi"]
 *   series:   SeriesSpec[]       — todas las series a renderizar
 *   log_scale: boolean           — escala logarítmica en el panel de precio
 * }
 *
 * SeriesSpec:
 * {
 *   type:        "candlestick" | "line" | "histogram"
 *   panel:       string          — panel al que pertenece
 *   name:        string          — título en la leyenda
 *   color:       string          — color CSS (para line/histogram sin color por barra)
 *   lineWidth:   number          — grosor (line)
 *   dashed:      boolean         — línea punteada (line)
 *   data:        object[]        — datos en formato LWC
 *   priceLines:  PriceLine[]     — líneas de referencia horizontales
 * }
 */

(function () {
    "use strict";

    /* ── Estado interno ─────────────────────────────────────────────────────── */
    var _charts = [];
    var _resizeObserver = null;

    /* ── Helpers ────────────────────────────────────────────────────────────── */

    function getContainer() {
        return document.getElementById("lwc-container");
    }

    function destroyCharts() {
        _charts.forEach(function (c) {
            try { c.remove(); } catch (_) {}
        });
        _charts = [];
        if (_resizeObserver) {
            _resizeObserver.disconnect();
            _resizeObserver = null;
        }
    }

    /**
     * Calcula la altura en píxeles de cada panel dado el total disponible.
     * Sin separados: precio 88%, volumen 12%.
     * Con N separados: precio 52%, volumen 8%, cada separado = resto/N.
     */
    function panelHeights(panels, totalH) {
        var separates = panels.filter(function (p) {
            return p !== "price" && p !== "volume";
        });
        var ns = separates.length;
        var heights = {};

        if (ns === 0) {
            heights["price"]  = Math.round(totalH * 0.88);
            heights["volume"] = totalH - heights["price"];
        } else {
            var priceH  = Math.round(totalH * 0.52);
            var volumeH = Math.round(totalH * 0.08);
            var sepH    = Math.floor((totalH - priceH - volumeH) / ns);
            heights["price"]  = priceH;
            heights["volume"] = volumeH;
            separates.forEach(function (p) { heights[p] = Math.max(sepH, 60); });
        }
        return heights;
    }

    /** Opciones base para createChart. */
    function baseChartOptions(width, height, showTimeAxis) {
        return {
            width:  width,
            height: height,
            layout: {
                background: { type: "solid", color: "#1e1e1e" },
                textColor: "#dee2e6",
                fontSize: 11,
            },
            grid: {
                vertLines: { color: "#2a2a2a" },
                horzLines: { color: "#2a2a2a" },
            },
            crosshair: {
                mode: LightweightCharts.CrosshairMode.Normal,
            },
            rightPriceScale: {
                borderColor: "#444",
                scaleMargins: { top: 0.05, bottom: 0.05 },
            },
            timeScale: {
                borderColor: "#444",
                visible: showTimeAxis,
                timeVisible: false,
                fixLeftEdge: false,
                fixRightEdge: false,
            },
            handleScroll: true,
            handleScale:  true,
        };
    }

    /** Agrega una serie a un chart y le aplica los datos. */
    function addSeries(chart, spec) {
        var series = null;

        if (spec.type === "candlestick") {
            series = chart.addCandlestickSeries({
                upColor:        "#00b050",
                downColor:      "#ef5350",
                borderUpColor:  "#00b050",
                borderDownColor:"#ef5350",
                wickUpColor:    "#00b050",
                wickDownColor:  "#ef5350",
            });

        } else if (spec.type === "line") {
            series = chart.addLineSeries({
                color:             spec.color   || "#2196f3",
                lineWidth:         spec.lineWidth || 1.5,
                title:             spec.name    || "",
                lineStyle:         spec.dashed
                    ? LightweightCharts.LineStyle.Dashed
                    : LightweightCharts.LineStyle.Solid,
                priceLineVisible:  false,
                lastValueVisible:  true,
            });

        } else if (spec.type === "histogram") {
            series = chart.addHistogramSeries({
                title:            spec.name || "",
                color:            spec.color || "#26a69a",
                priceFormat:      spec.panel === "volume"
                    ? { type: "volume" }
                    : { type: "price", precision: 4 },
                priceLineVisible: false,
                lastValueVisible: spec.panel !== "volume",
            });
        }

        if (!series) return;

        if (spec.data && spec.data.length) {
            series.setData(spec.data);
        }

        /* Líneas de referencia horizontales (RSI 70/30, Estocástico 80/20…) */
        if (spec.priceLines) {
            spec.priceLines.forEach(function (pl) {
                series.createPriceLine({
                    price:             pl.price,
                    color:             pl.color,
                    lineWidth:         1,
                    lineStyle:         LightweightCharts.LineStyle.Dotted,
                    axisLabelVisible:  true,
                    title:             String(pl.price),
                });
            });
        }
    }

    /** Sincroniza las timeScale de todos los charts para scroll/zoom solidario. */
    function syncTimeScales(charts) {
        if (charts.length < 2) return;
        charts.forEach(function (src, i) {
            src.timeScale().subscribeVisibleLogicalRangeChange(function (range) {
                if (!range) return;
                charts.forEach(function (dst, j) {
                    if (i !== j) dst.timeScale().setVisibleLogicalRange(range);
                });
            });
        });
    }

    /** Mantiene el ancho de los charts al redimensionar el contenedor. */
    function setupResizeObserver(container, charts) {
        if (!window.ResizeObserver) return;
        _resizeObserver = new ResizeObserver(function () {
            var w = container.clientWidth;
            charts.forEach(function (c) { c.applyOptions({ width: w }); });
        });
        _resizeObserver.observe(container);
    }

    /* ── Función principal ──────────────────────────────────────────────────── */

    /**
     * Punto de entrada llamado por el clientside_callback de Dash.
     * @param {object} chartData  — contrato JSON descrito en el encabezado
     * @returns {null}            — valor para el Store "chart-render-dummy"
     */
    function render(chartData) {
        if (!chartData) return null;

        var container = getContainer();
        if (!container) return null;

        destroyCharts();
        container.innerHTML = "";

        var panels  = chartData.panels  || ["price", "volume"];
        var totalH  = container.clientHeight || 600;
        var totalW  = container.clientWidth  || 800;
        var heights = panelHeights(panels, totalH);

        /* Crear un chart por panel */
        var panelCharts = {};
        panels.forEach(function (panel, idx) {
            var div = document.createElement("div");
            div.style.cssText = "width:100%;overflow:hidden;";
            container.appendChild(div);

            var isLast = (idx === panels.length - 1);
            var chart  = LightweightCharts.createChart(
                div,
                baseChartOptions(totalW, heights[panel] || 80, isLast)
            );

            panelCharts[panel] = chart;
            _charts.push(chart);
        });

        /* Escala logarítmica en el panel de precio */
        if (chartData.log_scale && panelCharts["price"]) {
            panelCharts["price"].priceScale("right").applyOptions({
                mode: LightweightCharts.PriceScaleMode.Logarithmic,
            });
        }

        /* Agregar todas las series */
        (chartData.series || []).forEach(function (spec) {
            var chart = panelCharts[spec.panel];
            if (chart) addSeries(chart, spec);
        });

        /* Ajustar vista y sincronizar */
        _charts.forEach(function (c) { c.timeScale().fitContent(); });
        syncTimeScales(_charts);
        setupResizeObserver(container, _charts);

        return null;
    }

    /* ── Exponer namespace para Dash ────────────────────────────────────────── */
    if (!window.dashLWC) window.dashLWC = {};
    window.dashLWC.render = render;

})();
