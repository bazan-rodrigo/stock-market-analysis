"""
Callbacks del gráfico técnico.
Produce un dict JSON con datos de precios e indicadores para Lightweight Charts (TradingView).
El render lo ejecuta un clientside_callback en assets/chart.js.
"""
from datetime import date

import pandas as pd
from dash import Input, Output, State, callback, clientside_callback, no_update

from app.indicators.base import PANEL_OVERLAY, PANEL_SEPARATE
from app.indicators.registry import all_indicators, overlay_indicators, separate_indicators
from app.services.asset_service import get_assets
from app.services.price_service import get_prices_df


# ── Paleta de colores para series ─────────────────────────────────────────────
_PALETTE = [
    "#ff9800", "#00bcd4", "#9c27b0", "#f44336", "#4caf50",
    "#ffeb3b", "#e91e63", "#ff5722", "#00e5ff", "#cddc39",
]


def _series_color(name: str, index: int = 0) -> str:
    if name.startswith("SMA"):       return "#ff9800"
    if name.startswith("EMA"):       return "#00bcd4"
    if "Superior" in name:           return "#7e57c2"
    if "Inferior" in name:           return "#7e57c2"
    if "Media" in name:              return "#e91e63"
    if name.startswith("RSI"):       return "#9c27b0"
    if name == "MACD":               return "#2196f3"
    if "Señal" in name:              return "#ff5722"
    if name.startswith("%K"):        return "#ffeb3b"
    if name.startswith("%D"):        return "#ff9800"
    if name.startswith("ATR"):       return "#00bcd4"
    return _PALETTE[index % len(_PALETTE)]


def _t(d) -> str:
    """Convierte datetime.date o string a 'YYYY-MM-DD' para LWC."""
    return str(d)[:10]


def _build_chart_data(df: pd.DataFrame, chart_type: str, yscale: str, indicator_config: dict) -> dict:
    """
    Convierte un DataFrame de precios + configuración de indicadores al contrato
    JSON consumido por window.dashLWC.render en assets/chart.js.
    """
    panels = ["price", "volume"]
    series = []

    # ── Precio ────────────────────────────────────────────────────────────────
    if chart_type == "candlestick":
        series.append({
            "type": "candlestick",
            "panel": "price",
            "data": [
                {
                    "time": _t(row.date),
                    "open": row.open, "high": row.high,
                    "low": row.low,   "close": row.close,
                }
                for row in df.itertuples(index=False)
            ],
        })
    else:
        series.append({
            "type": "line",
            "panel": "price",
            "name": "Precio",
            "color": "#2196f3",
            "data": [
                {"time": _t(row.date), "value": row.close}
                for row in df.itertuples(index=False)
            ],
        })

    # ── Indicadores overlay (sobre precio) ───────────────────────────────────
    color_idx = 0
    for cfg in indicator_config.values():
        if not cfg["enabled"] or cfg["indicator"].PANEL != PANEL_OVERLAY:
            continue
        ind = cfg["indicator"]
        for series_name, s in ind.compute(df, **cfg["params"]).items():
            series.append({
                "type": "line",
                "panel": "price",
                "name": series_name,
                "color": _series_color(series_name, color_idx),
                "data": [
                    {"time": _t(t), "value": float(v)}
                    for t, v in zip(df["date"], s) if pd.notna(v)
                ],
            })
            color_idx += 1

    # ── Volumen ───────────────────────────────────────────────────────────────
    series.append({
        "type": "histogram",
        "panel": "volume",
        "name": "Volumen",
        "data": [
            {
                "time": _t(row.date),
                "value": float(row.volume or 0),
                "color": "#00b050" if row.close >= row.open else "#ef5350",
            }
            for row in df.itertuples(index=False)
        ],
    })

    # ── Indicadores en paneles separados ─────────────────────────────────────
    for cfg in indicator_config.values():
        if not cfg["enabled"] or cfg["indicator"].PANEL != PANEL_SEPARATE:
            continue
        ind = cfg["indicator"]
        panel_id = ind.NAME
        if panel_id not in panels:
            panels.append(panel_id)

        # Líneas de referencia por indicador
        ref_lines: dict[str, list] = {}
        if ind.NAME == "rsi":
            ref_lines["RSI"] = [
                {"price": 70, "color": "#ef5350"},
                {"price": 30, "color": "#4caf50"},
            ]
        elif ind.NAME == "stochastic":
            ref_lines["%K"] = [
                {"price": 80, "color": "#ef5350"},
                {"price": 20, "color": "#4caf50"},
            ]

        for i, (series_name, s) in enumerate(ind.compute(df, **cfg["params"]).items()):
            is_hist = (ind.NAME == "macd" and "Histograma" in series_name)
            entry: dict = {
                "panel": panel_id,
                "name": series_name,
                "color": _series_color(series_name, i),
            }
            if is_hist:
                entry["type"] = "histogram"
                entry["data"] = [
                    {
                        "time": _t(t),
                        "value": float(v) if pd.notna(v) else 0.0,
                        "color": "#00b050" if (pd.notna(v) and v >= 0) else "#ef5350",
                    }
                    for t, v in zip(df["date"], s)
                ]
            else:
                entry["type"] = "line"
                entry["data"] = [
                    {"time": _t(t), "value": float(v)}
                    for t, v in zip(df["date"], s) if pd.notna(v)
                ]
                for key, lines in ref_lines.items():
                    if series_name.startswith(key):
                        entry["priceLines"] = lines
                        break
            series.append(entry)

    return {"panels": panels, "series": series, "log_scale": yscale == "log"}


# ── Carga de activos ──────────────────────────────────────────────────────────
@callback(
    Output("chart-asset-select", "options"),
    Input("chart-asset-select", "id"),
)
def load_chart_assets(_):
    assets = get_assets(only_active=True)
    return [{"label": f"{a.ticker} — {a.name or a.ticker}", "value": a.id} for a in assets]


# ── Mostrar/ocultar parámetros de indicadores ─────────────────────────────────
for _ind in all_indicators():
    _ind_id = _ind.NAME

    @callback(
        Output(f"chart-ind-{_ind_id}-params", "style"),
        Input(f"chart-ind-{_ind_id}-enabled", "value"),
    )
    def _toggle_params(enabled, ind_id=_ind_id):
        return {"display": "block"} if enabled else {"display": "none"}


# ── Callback principal: construir JSON para LWC ───────────────────────────────
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
    asset_id  = args[idx]; idx += 1
    date_from = args[idx]; idx += 1
    date_to   = args[idx]; idx += 1
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


# ── Clientside callback: render en Lightweight Charts ────────────────────────
clientside_callback(
    """
    function(chartData) {
        if (!chartData) return window.dash_clientside.no_update;
        if (window._lwcRender) window._lwcRender(chartData);
        return null;
    }
    """,
    Output("chart-render-dummy", "data"),
    Input("chart-data", "data"),
    prevent_initial_call=True,
)
