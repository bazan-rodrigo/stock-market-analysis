"""
Callbacks del gráfico técnico.
Construye un gráfico Plotly con subplots para precio, volumen e indicadores separados.
"""
from datetime import date

import plotly.graph_objects as go
from plotly.subplots import make_subplots
from dash import Input, Output, State, callback, no_update

from app.indicators.registry import all_indicators, overlay_indicators, separate_indicators
from app.indicators.base import PANEL_SEPARATE
from app.services.asset_service import get_assets
from app.services.price_service import get_prices_df


def _sma_filter(value):
    """Convierte el valor del radio item de SMA en bool o None."""
    if value == "above":
        return True
    if value == "below":
        return False
    return None


# Carga dinámica de opciones de activos
@callback(
    Output("chart-asset-select", "options"),
    Input("chart-asset-select", "id"),
)
def load_chart_assets(_):
    assets = get_assets(only_active=True)
    return [{"label": f"{a.ticker} — {a.name}", "value": a.id} for a in assets]


# Mostrar/ocultar parámetros cuando se activa un indicador
for _ind in all_indicators():
    _ind_id = _ind.NAME

    @callback(
        Output(f"chart-ind-{_ind_id}-params", "style"),
        Input(f"chart-ind-{_ind_id}-enabled", "value"),
    )
    def _toggle_params(enabled, ind_id=_ind_id):
        return {"display": "block"} if enabled else {"display": "none"}


# Callback principal: construir el gráfico
def _build_chart_inputs():
    inputs = [
        Input("chart-btn-update", "n_clicks"),
    ]
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


_chart_inputs, _chart_states = _build_chart_inputs()


@callback(
    Output("chart-figure", "figure"),
    *_chart_inputs,
    *_chart_states,
    prevent_initial_call=True,
)
def update_chart(n_clicks, *args):
    idx = 0
    asset_id = args[idx]; idx += 1
    date_from = args[idx]; idx += 1
    date_to = args[idx]; idx += 1
    chart_type = args[idx]; idx += 1
    yscale = args[idx]; idx += 1

    # Leer enabled + params por indicador
    indicator_config = {}
    for ind in all_indicators():
        enabled = args[idx]; idx += 1
        params = {}
        for p in ind.PARAMS:
            params[p.name] = args[idx]; idx += 1
        indicator_config[ind.NAME] = {"enabled": bool(enabled), "params": params, "indicator": ind}

    if not asset_id:
        return go.Figure()

    df = get_prices_df(int(asset_id))
    if df.empty:
        fig = go.Figure()
        fig.add_annotation(text="Sin datos de precios para este activo.", showarrow=False)
        return fig

    # Filtrar por rango de fechas
    if date_from:
        df = df[df["date"] >= date.fromisoformat(date_from)]
    if date_to:
        df = df[df["date"] <= date.fromisoformat(date_to)]

    if df.empty:
        fig = go.Figure()
        fig.add_annotation(text="Sin datos en el rango seleccionado.", showarrow=False)
        return fig

    # Determinar subplots necesarios
    active_separate = [
        cfg for cfg in indicator_config.values()
        if cfg["enabled"] and cfg["indicator"].PANEL == PANEL_SEPARATE
    ]
    n_subplots = 2 + len(active_separate)  # precio + volumen + indicadores separados
    row_heights = [0.5, 0.1] + [0.4 / max(len(active_separate), 1)] * len(active_separate)

    subplot_titles = ["Precio", "Volumen"] + [
        cfg["indicator"].LABEL for cfg in active_separate
    ]

    fig = make_subplots(
        rows=n_subplots,
        cols=1,
        shared_xaxes=True,
        vertical_spacing=0.03,
        row_heights=row_heights,
        subplot_titles=subplot_titles,
    )

    # --- Precio ---
    if chart_type == "candlestick":
        fig.add_trace(
            go.Candlestick(
                x=df["date"],
                open=df["open"],
                high=df["high"],
                low=df["low"],
                close=df["close"],
                name="Precio",
                increasing_line_color="#00b050",
                decreasing_line_color="#ff0000",
            ),
            row=1, col=1,
        )
    else:
        fig.add_trace(
            go.Scatter(x=df["date"], y=df["close"], name="Precio", line=dict(color="#2196F3")),
            row=1, col=1,
        )

    # --- Indicadores sobre precio ---
    for cfg in indicator_config.values():
        if not cfg["enabled"] or cfg["indicator"].PANEL != "overlay":
            continue
        ind = cfg["indicator"]
        series_dict = ind.compute(df, **cfg["params"])
        for series_name, series in series_dict.items():
            fig.add_trace(
                go.Scatter(x=df["date"], y=series, name=series_name, line=dict(width=1.5)),
                row=1, col=1,
            )

    # --- Volumen ---
    colors = ["#00b050" if c >= o else "#ff0000" for c, o in zip(df["close"], df["open"])]
    fig.add_trace(
        go.Bar(x=df["date"], y=df["volume"], name="Volumen", marker_color=colors, showlegend=False),
        row=2, col=1,
    )

    # --- Indicadores en paneles separados ---
    for i, cfg in enumerate(active_separate):
        row_idx = 3 + i
        ind = cfg["indicator"]
        series_dict = ind.compute(df, **cfg["params"])

        if ind.NAME == "macd":
            # MACD tiene histograma como barras
            for series_name, series in series_dict.items():
                if "Histograma" in series_name:
                    bar_colors = ["#00b050" if v >= 0 else "#ff0000" for v in series.fillna(0)]
                    fig.add_trace(
                        go.Bar(x=df["date"], y=series, name=series_name, marker_color=bar_colors),
                        row=row_idx, col=1,
                    )
                else:
                    fig.add_trace(
                        go.Scatter(x=df["date"], y=series, name=series_name, line=dict(width=1.5)),
                        row=row_idx, col=1,
                    )
        elif ind.NAME == "rsi":
            for series_name, series in series_dict.items():
                fig.add_trace(
                    go.Scatter(x=df["date"], y=series, name=series_name, line=dict(width=1.5)),
                    row=row_idx, col=1,
                )
            # Líneas de referencia 30 y 70
            fig.add_hline(y=70, line_dash="dot", line_color="red", row=row_idx, col=1)
            fig.add_hline(y=30, line_dash="dot", line_color="green", row=row_idx, col=1)
        else:
            for series_name, series in series_dict.items():
                fig.add_trace(
                    go.Scatter(x=df["date"], y=series, name=series_name, line=dict(width=1.5)),
                    row=row_idx, col=1,
                )

    fig.update_layout(
        height=700,
        xaxis_rangeslider_visible=False,
        template="plotly_dark",
        legend=dict(orientation="h", y=-0.05),
        margin=dict(l=40, r=20, t=40, b=40),
        paper_bgcolor="#1e1e1e",
        plot_bgcolor="#1e1e1e",
    )
    fig.update_xaxes(showgrid=True, gridcolor="#333")
    fig.update_yaxes(showgrid=True, gridcolor="#333")
    fig.update_yaxes(type=yscale, row=1, col=1)

    return fig
