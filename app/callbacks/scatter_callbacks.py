from collections import defaultdict
from datetime import date as _date

import numpy as np
import plotly.graph_objects as go
from dash import Input, Output, State, callback, html, no_update
import dash_bootstrap_components as dbc

import app.services.scatter_service as svc

_BG      = "#111827"
_RED     = "#ef4444"
_TREND_COLOR = "#facc15"


@callback(
    Output("scatter-asset1", "options"),
    Output("scatter-asset2", "options"),
    Input("scatter-asset1", "id"),
)
def load_options(_):
    opts = svc.get_all_assets_options()
    return opts, opts


@callback(
    Output("scatter-asset1", "value", allow_duplicate=True),
    Output("scatter-asset2", "value", allow_duplicate=True),
    Input("scatter-swap-btn", "n_clicks"),
    State("scatter-asset1", "value"),
    State("scatter-asset2", "value"),
    prevent_initial_call=True,
)
def swap_assets(_, a1, a2):
    if a1 is None and a2 is None:
        return no_update, no_update
    return a2, a1


@callback(
    Output("scatter-poly-degree-col", "style"),
    Input("scatter-trend-type", "value"),
)
def toggle_degree_col(trend_type):
    return {"display": "block"} if trend_type == "poly" else {"display": "none"}


def _compute_trend(xs, ys, trend_type, degree=2):
    """
    Returns (x_line, y_line, r2, equation_label) or None on failure.
    R² is always computed on original (non-log) residuals.
    """
    x = np.array(xs, dtype=float)
    y = np.array(ys, dtype=float)
    n = len(x)
    if n < 3:
        return None

    x_line = np.linspace(x.min(), x.max(), 300)

    try:
        if trend_type == "linear":
            coeffs   = np.polyfit(x, y, 1)
            y_fit    = np.polyval(coeffs, x)
            y_line   = np.polyval(coeffs, x_line)
            a, b     = coeffs
            eq       = f"y = {a:.4g}x + {b:.4g}"

        elif trend_type == "log":
            if np.any(x <= 0):
                return None
            coeffs   = np.polyfit(np.log(x), y, 1)
            y_fit    = np.polyval(coeffs, np.log(x))
            y_line   = np.polyval(coeffs, np.log(x_line))
            a, b     = coeffs
            eq       = f"y = {a:.4g}·ln(x) + {b:.4g}"

        elif trend_type == "poly":
            deg      = max(2, min(10, int(degree or 2)))
            coeffs   = np.polyfit(x, y, deg)
            y_fit    = np.polyval(coeffs, x)
            y_line   = np.polyval(coeffs, x_line)
            eq       = f"Polinómica grado {deg}"

        elif trend_type == "exp":
            if np.any(y <= 0):
                return None
            coeffs   = np.polyfit(x, np.log(y), 1)
            y_fit    = np.exp(np.polyval(coeffs, x))
            y_line   = np.exp(np.polyval(coeffs, x_line))
            b, ln_a  = coeffs
            eq       = f"y = {np.exp(ln_a):.4g}·e^({b:.4g}x)"

        else:
            return None

        ss_res = float(np.sum((y - y_fit) ** 2))
        ss_tot = float(np.sum((y - y.mean()) ** 2))
        r2     = 1.0 - ss_res / ss_tot if ss_tot > 0 else 0.0

        return x_line.tolist(), y_line.tolist(), r2, eq

    except Exception:
        return None


@callback(
    Output("scatter-graph",  "figure"),
    Output("scatter-stats",  "children"),
    Input("scatter-asset1",       "value"),
    Input("scatter-asset2",       "value"),
    Input("scatter-show-events",  "value"),
    Input("scatter-trend-type",   "value"),
    Input("scatter-poly-degree",  "value"),
    Input("scatter-show-r2",      "value"),
    Input("scatter-log-axes",     "value"),
)
def render_scatter(asset1_id, asset2_id, show_events_opt,
                   trend_type, poly_degree, show_r2, log_axes):
    empty = _empty_fig()

    if not asset1_id or not asset2_id:
        return empty, ""

    if asset1_id == asset2_id:
        return empty, dbc.Alert("Seleccioná dos activos diferentes.",
                                color="warning", className="mt-2 py-1",
                                style={"fontSize": "0.82rem"})

    pairs = svc.get_paired_prices(asset1_id, asset2_id)
    if not pairs:
        return empty, dbc.Alert("Sin precios en común para ambos activos.",
                                color="warning", className="mt-2 py-1",
                                style={"fontSize": "0.82rem"})

    label1 = svc.get_asset_label(asset1_id)
    label2 = svc.get_asset_label(asset2_id)
    tick1  = label1.split(" — ")[0]
    tick2  = label2.split(" — ")[0]

    xs    = [p["p1"]   for p in pairs]
    ys    = [p["p2"]   for p in pairs]
    dates = [p["date"] for p in pairs]
    n     = len(pairs)

    hover = [
        f"<b>{dates[i]}</b><br>{tick1}: {xs[i]:.6g}<br>{tick2}: {ys[i]:.6g}"
        for i in range(n)
    ]

    # ── Eventos ───────────────────────────────────────────────────────────────
    show_events = "events" in (show_events_opt or [])
    events = svc.get_events_with_coords(asset1_id, asset2_id, pairs) if show_events else []

    event_color_for_date: dict[str, str] = {}
    for ev in events:
        sd = _date.fromisoformat(ev["start_date"])
        ed = _date.fromisoformat(ev["end_date"])
        for p in pairs:
            if sd <= _date.fromisoformat(p["date"]) <= ed:
                event_color_for_date[p["date"]] = ev["color"]

    last_date = dates[-1]
    normal_idx: list[int] = []
    event_by_color: dict[str, list[int]] = defaultdict(list)

    for i in range(n - 1):
        d = dates[i]
        if d in event_color_for_date:
            event_by_color[event_color_for_date[d]].append(i)
        else:
            normal_idx.append(i)

    # ── Figura ────────────────────────────────────────────────────────────────
    fig = go.Figure()

    if normal_idx:
        fig.add_trace(go.Scatter(
            x=[xs[i] for i in normal_idx],
            y=[ys[i] for i in normal_idx],
            mode="markers",
            marker=dict(
                size=5,
                color=normal_idx,
                colorscale="Plasma",
                opacity=0.7,
                showscale=True,
                cmin=0, cmax=n - 1,
                colorbar=dict(
                    title=dict(text="Tiempo", side="right", font=dict(size=10)),
                    tickvals=[0, n - 1],
                    ticktext=[dates[0], dates[-1]],
                    tickfont=dict(size=9),
                    thickness=12, len=0.6,
                ),
            ),
            hovertemplate="%{customdata}<extra></extra>",
            customdata=[hover[i] for i in normal_idx],
            showlegend=False,
        ))

    for color, indices in event_by_color.items():
        fig.add_trace(go.Scatter(
            x=[xs[i] for i in indices],
            y=[ys[i] for i in indices],
            mode="markers",
            marker=dict(size=7, color=color, opacity=0.9,
                        line=dict(color="#ffffff", width=0.8)),
            hovertemplate="%{customdata}<extra></extra>",
            customdata=[hover[i] for i in indices],
            showlegend=False,
        ))

    fig.add_trace(go.Scatter(
        x=[xs[-1]], y=[ys[-1]],
        mode="markers+text",
        marker=dict(size=11, color=_RED, symbol="circle",
                    line=dict(color="#ffffff", width=1.5)),
        text=[last_date],
        textposition="top right",
        textfont=dict(color=_RED, size=8),
        hovertemplate=hover[-1] + "<extra></extra>",
        showlegend=False,
    ))

    for ev in events:
        fig.add_trace(go.Scatter(
            x=[ev["p1"]], y=[ev["p2"]],
            mode="markers+text",
            marker=dict(size=14, color=ev["color"], symbol="star",
                        line=dict(color="#1f2937", width=1)),
            text=[ev["name"]],
            textposition="top center",
            textfont=dict(color=ev["color"], size=8),
            hovertemplate=(
                f"<b>{ev['name']}</b><br>"
                f"{ev['start_date']} → {ev['end_date']}"
                "<extra></extra>"
            ),
            showlegend=False,
        ))

    # ── Línea de tendencia ───────────────────────────────────────────────────
    trend_result = None
    trend_note   = ""
    if trend_type and trend_type != "none":
        trend_result = _compute_trend(xs, ys, trend_type, poly_degree)
        if trend_result is None:
            trend_note = " · Tendencia no disponible (valores no válidos para este tipo)"

    if trend_result:
        x_line, y_line, r2, eq = trend_result
        trend_label = eq
        if show_r2:
            trend_label += f"  (R² = {r2:.4f})"
        fig.add_trace(go.Scatter(
            x=x_line,
            y=y_line,
            mode="lines",
            line=dict(color=_TREND_COLOR, width=1.5, dash="dash"),
            name=trend_label,
            hoverinfo="skip",
        ))
        # Anotación de R² en el gráfico
        if show_r2:
            fig.add_annotation(
                xref="paper", yref="paper",
                x=0.01, y=0.99,
                text=f"<b>R² = {r2:.4f}</b>",
                showarrow=False,
                font=dict(size=11, color=_TREND_COLOR),
                bgcolor="rgba(0,0,0,0.5)",
                borderpad=4,
                xanchor="left", yanchor="top",
            )

    # ── Log scale ─────────────────────────────────────────────────────────────
    log_axes   = log_axes or []
    xaxis_type = "log" if "x" in log_axes else "linear"
    yaxis_type = "log" if "y" in log_axes else "linear"

    fig.update_layout(
        plot_bgcolor=_BG,
        paper_bgcolor=_BG,
        font=dict(color="#dee2e6", size=11),
        xaxis=dict(
            title=label1,
            type=xaxis_type,
            gridcolor="#1f2937",
            zerolinecolor="#4b5563",
            tickfont=dict(size=10),
        ),
        yaxis=dict(
            title=label2,
            type=yaxis_type,
            gridcolor="#1f2937",
            zerolinecolor="#4b5563",
            tickfont=dict(size=10),
        ),
        margin=dict(l=60, r=90, t=20, b=50),
        hovermode="closest",
        legend=dict(
            x=0.01, y=0.01,
            font=dict(size=9, color=_TREND_COLOR),
            bgcolor="rgba(0,0,0,0)",
            xanchor="left", yanchor="bottom",
        ),
    )

    corr = float(np.corrcoef(xs, ys)[0, 1]) if n > 2 else None
    stats = (
        f"N = {n} puntos  ·  {dates[0]} → {dates[-1]}"
        + (f"  ·  Correlación: {corr:.3f}" if corr is not None else "")
        + trend_note
    )
    return fig, stats


def _empty_fig() -> go.Figure:
    fig = go.Figure()
    fig.update_layout(
        plot_bgcolor=_BG, paper_bgcolor=_BG,
        font=dict(color="#dee2e6"),
        xaxis=dict(gridcolor="#1f2937"),
        yaxis=dict(gridcolor="#1f2937"),
        margin=dict(l=60, r=20, t=20, b=50),
    )
    return fig
