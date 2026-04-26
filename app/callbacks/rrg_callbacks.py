import logging
import math

import plotly.graph_objects as go
from dash import Input, Output, State, callback, no_update, ALL, ctx
import dash_bootstrap_components as dbc
from dash import html

import app.services.rrg_service as rrg_svc

logger = logging.getLogger(__name__)

_PALETTE = [
    "#00e676", "#40c4ff", "#ff6d00", "#ea80fc", "#ffff00",
    "#ff4081", "#69f0ae", "#18ffff", "#b388ff", "#ff6e40",
    "#f06292", "#4dd0e1", "#dce775", "#ff8a65", "#a1887f",
]

_BG = "#111827"


# ── Opciones de dropdowns ─────────────────────────────────────────────────────
@callback(
    Output("rrg-benchmark-select",  "options"),
    Output("rrg-asset-add-select",  "options"),
    Input("rrg-benchmark-select",   "id"),
)
def load_rrg_options(_):
    opts = rrg_svc.get_all_assets_options()
    return opts, opts


# ── Auto-carga al elegir benchmark ───────────────────────────────────────────
@callback(
    Output("rrg-selected-assets", "data", allow_duplicate=True),
    Input("rrg-benchmark-select", "value"),
    prevent_initial_call=True,
)
def auto_load_benchmark_assets(benchmark_id):
    if not benchmark_id:
        return []
    return rrg_svc.get_assets_for_benchmark(benchmark_id)


# ── Gestión de activos seleccionados ─────────────────────────────────────────
@callback(
    Output("rrg-selected-assets",  "data"),
    Output("rrg-asset-add-select", "value"),
    Input("rrg-btn-add",           "n_clicks"),
    Input("rrg-btn-clear",         "n_clicks"),
    Input({"type": "rrg-remove", "index": ALL}, "n_clicks"),
    State("rrg-asset-add-select",  "value"),
    State("rrg-selected-assets",   "data"),
    prevent_initial_call=True,
)
def manage_assets(add_clicks, clear_clicks, remove_clicks, new_id, current):
    trigger = ctx.triggered_id

    if trigger == "rrg-btn-clear":
        return [], no_update

    if trigger == "rrg-btn-add":
        if not new_id:
            return no_update, no_update
        current = current or []
        if new_id in current:
            return no_update, no_update
        return current + [new_id], None

    if isinstance(trigger, dict) and trigger.get("type") == "rrg-remove":
        if not any(n for n in remove_clicks if n):
            return no_update, no_update
        return [a for a in (current or []) if a != trigger["index"]], no_update

    return no_update, no_update


# ── Cálculo pesado: acceso a BD → Store ──────────────────────────────────────
@callback(
    Output("rrg-full-data",      "data"),
    Output("rrg-load-trigger",   "children"),
    Output("rrg-alert",          "children"),
    Output("rrg-alert",          "is_open"),
    Output("rrg-alert",          "color"),
    Input("rrg-selected-assets", "data"),
    Input("rrg-benchmark-select", "value"),
)
def compute_data(asset_ids, benchmark_id):
    try:
        if not benchmark_id:
            return None, None, "Seleccioná un benchmark para comenzar.", True, "info"

        if not asset_ids:
            return None, None, "", False, "info"

        data, warnings = rrg_svc.compute_rrg(asset_ids, benchmark_id, tail_weeks=rrg_svc._MAX_TRAIL)

        skipped_labels = {str(w["id"]): w["ticker"] for w in warnings}

        if warnings:
            items = [html.Li(f"{w['ticker']}: {w['reason']}") for w in warnings]
            alert_msg = html.Div([
                html.Strong(f"{len(warnings)} activo(s) omitido(s):"),
                html.Ul(items, style={"marginBottom": 0, "paddingLeft": "1.2rem", "marginTop": "4px"}),
            ])
            alert_color = "warning"
        else:
            alert_msg = ""
            alert_color = "info"

        if not data:
            return None, None, alert_msg or "Sin datos para mostrar.", True, "warning" if warnings else "danger"

        payload = {
            "benchmark_id":   benchmark_id,
            "asset_ids":      asset_ids,
            "data":           {str(k): v for k, v in data.items()},
            "skipped_labels": skipped_labels,
        }
        return payload, None, alert_msg, bool(warnings), alert_color

    except Exception as exc:
        logger.exception("RRG compute_data: error inesperado")
        return None, None, f"Error inesperado al calcular RRG: {exc}", True, "danger"


# ── Render rápido: Store + slider → figura (sin BD) ──────────────────────────
@callback(
    Output("rrg-graph",      "figure"),
    Output("rrg-asset-list", "children"),
    Input("rrg-full-data",   "data"),
    Input("rrg-tail",        "value"),
)
def render_figure(payload, tail_weeks):
    tail_weeks = tail_weeks or 12

    if not payload or not payload.get("data"):
        fig = _empty_fig()
        # uirevision fijo para que el zoom no se resetee al limpiar
        fig.update_layout(uirevision="empty")
        return fig, html.Div()

    benchmark_id   = payload["benchmark_id"]
    asset_ids      = payload["asset_ids"]
    raw_data       = payload["data"]
    skipped_labels = payload.get("skipped_labels", {})

    # Recortar trail al valor del slider
    data = {}
    for k, info in raw_data.items():
        trail = info["trail"][-tail_weeks:] if tail_weeks < len(info["trail"]) else info["trail"]
        if trail:
            data[int(k)] = {**info, "trail": trail}

    # uirevision incluye tail_weeks: fuerza re-render limpio al cambiar la cola,
    # evitando que Plotly intente mergear trazas cuando cambia su cantidad y
    # el gráfico quede en estado corrupto permanentemente.
    uirev = f"{benchmark_id}_{sorted(asset_ids)}_{tail_weeks}"

    fig   = _build_figure(data, uirev)
    table = _build_table(asset_ids, raw_data, skipped_labels)
    return fig, table


# ── Helpers de figura ─────────────────────────────────────────────────────────
def _empty_fig() -> go.Figure:
    fig = go.Figure()
    _apply_layout(fig, [90, 110], [90, 110], uirevision="empty")
    return fig


def _build_figure(data: dict, uirevision: str) -> go.Figure:
    fig   = go.Figure()
    all_x = [100.0]
    all_y = [100.0]

    for i, (aid, info) in enumerate(data.items()):
        color = _PALETTE[i % len(_PALETTE)]
        trail = info["trail"]
        if not trail:
            continue

        xs    = [p["ratio"]    for p in trail]
        ys    = [p["momentum"] for p in trail]
        dates = [p["date"]     for p in trail]
        all_x.extend(xs)
        all_y.extend(ys)

        n = len(xs)
        opacities = [0.15 + 0.85 * (j / max(n - 1, 1)) for j in range(n)]
        sizes     = [3    + 5    * (j / max(n - 1, 1)) for j in range(n)]

        hover = [
            f"<b>{info['ticker']}</b><br>{dates[j]}<br>RS-Ratio: {xs[j]:.2f}<br>RS-Mom: {ys[j]:.2f}"
            for j in range(n)
        ]

        rgb = _hex_to_rgb(color)
        for j in range(n - 1):
            mx = (xs[j] + xs[j + 1]) / 2
            my = (ys[j] + ys[j + 1]) / 2
            dist = math.hypot(mx - 100.0, my - 100.0)
            width = max(0.6, min(5.0, 0.6 + dist / 10))
            seg_opacity = opacities[j]
            fig.add_trace(go.Scatter(
                x=[xs[j], xs[j + 1]],
                y=[ys[j], ys[j + 1]],
                mode="lines+markers",
                line=dict(color=f"rgba({rgb},{seg_opacity:.2f})", width=width),
                marker=dict(
                    size=[sizes[j], sizes[j + 1]],
                    color=[
                        f"rgba({rgb},{opacities[j]:.2f})",
                        f"rgba({rgb},{opacities[j+1]:.2f})",
                    ],
                ),
                name=info["ticker"],
                legendgroup=info["ticker"],
                showlegend=False,
                hovertemplate="%{customdata}<extra></extra>",
                customdata=[hover[j], hover[j + 1]],
            ))

        fig.add_trace(go.Scatter(
            x=[xs[-1]], y=[ys[-1]],
            mode="markers+text",
            marker=dict(size=11, color=color, symbol="square"),
            text=[info["ticker"]],
            textposition="top center",
            textfont=dict(color=color, size=11, family="monospace"),
            name=info["ticker"],
            legendgroup=info["ticker"],
            showlegend=True,
            hovertemplate="%{customdata}<extra></extra>",
            customdata=[hover[-1]],
        ))

    pad_x = max((max(all_x) - min(all_x)) * 0.12, 1.5)
    pad_y = max((max(all_y) - min(all_y)) * 0.12, 1.5)
    x_range = [min(all_x) - pad_x, max(all_x) + pad_x]
    y_range = [min(all_y) - pad_y, max(all_y) + pad_y]

    _apply_layout(fig, x_range, y_range, uirevision)
    return fig


def _apply_layout(fig: go.Figure, x_range: list, y_range: list, uirevision: str = "rrg"):
    cx, cy = 100.0, 100.0
    xlo, xhi = x_range
    ylo, yhi = y_range

    shapes = [
        dict(type="rect", x0=cx, y0=cy, x1=xhi, y1=yhi,
             fillcolor="rgba(27,94,32,0.22)",   line_width=0),
        dict(type="rect", x0=xlo, y0=cy, x1=cx, y1=yhi,
             fillcolor="rgba(13,71,161,0.22)",  line_width=0),
        dict(type="rect", x0=xlo, y0=ylo, x1=cx, y1=cy,
             fillcolor="rgba(183,28,28,0.22)",  line_width=0),
        dict(type="rect", x0=cx, y0=ylo, x1=xhi, y1=cy,
             fillcolor="rgba(230,119,0,0.18)",  line_width=0),
        dict(type="line", x0=cx, y0=ylo, x1=cx, y1=yhi,
             line=dict(color="#4b5563", width=1)),
        dict(type="line", x0=xlo, y0=cy, x1=xhi, y1=cy,
             line=dict(color="#4b5563", width=1)),
    ]

    annotations = [
        dict(x=xlo + (xhi - xlo) * 0.02, y=yhi, text="Improving",
             font=dict(color="#93c5fd", size=12), showarrow=False,
             xanchor="left", yanchor="top"),
        dict(x=xhi - (xhi - xlo) * 0.02, y=yhi, text="Leading",
             font=dict(color="#86efac", size=12), showarrow=False,
             xanchor="right", yanchor="top"),
        dict(x=xlo + (xhi - xlo) * 0.02, y=ylo, text="Lagging",
             font=dict(color="#fca5a5", size=12), showarrow=False,
             xanchor="left", yanchor="bottom"),
        dict(x=xhi - (xhi - xlo) * 0.02, y=ylo, text="Weakening",
             font=dict(color="#fde68a", size=12), showarrow=False,
             xanchor="right", yanchor="bottom"),
    ]

    fig.update_layout(
        uirevision=uirevision,
        plot_bgcolor=_BG,
        paper_bgcolor=_BG,
        font=dict(color="#dee2e6", size=11),
        shapes=shapes,
        annotations=annotations,
        xaxis=dict(
            title="JdK RS-Ratio",
            range=x_range,
            gridcolor="#1f2937",
            zerolinecolor="#4b5563",
            tickfont=dict(size=10),
        ),
        yaxis=dict(
            title="JdK RS-Momentum",
            range=y_range,
            gridcolor="#1f2937",
            zerolinecolor="#4b5563",
            tickfont=dict(size=10),
        ),
        legend=dict(
            bgcolor="#1f2937",
            bordercolor="#374151",
            borderwidth=1,
            font=dict(size=10),
            orientation="v",
        ),
        margin=dict(l=55, r=20, t=15, b=50),
        hovermode="closest",
    )


# ── Helpers de tabla ──────────────────────────────────────────────────────────
def _build_table(asset_ids: list, raw_data: dict, skipped_labels: dict = None) -> html.Div:
    skipped_labels = skipped_labels or {}
    rows = []
    for i, aid in enumerate(asset_ids):
        color   = _PALETTE[i % len(_PALETTE)]
        info    = raw_data.get(str(aid)) or raw_data.get(aid)
        skipped = info is None
        ticker  = info["ticker"] if info else skipped_labels.get(str(aid), str(aid))
        name    = info["name"]   if info else "—"
        trail   = info["trail"]  if info else []
        ratio    = f"{trail[-1]['ratio']:.2f}"    if trail else "—"
        momentum = f"{trail[-1]['momentum']:.2f}" if trail else "—"
        date_lbl = trail[-1]["date"]               if trail else "—"

        row_style = {"borderBottom": "1px solid #1f2937"}
        if skipped:
            row_style["opacity"] = "0.45"

        rows.append(html.Tr([
            html.Td(html.Div(style={
                "width": "12px", "height": "12px",
                "backgroundColor": color, "borderRadius": "2px", "margin": "auto",
            })),
            html.Td(ticker,  style={"fontWeight": "bold",  "fontSize": "0.82rem", "paddingLeft": "6px"}),
            html.Td(name,    style={
                "color": "#9ca3af", "maxWidth": "180px", "overflow": "hidden",
                "textOverflow": "ellipsis", "whiteSpace": "nowrap", "paddingRight": "16px",
            }),
            html.Td(date_lbl, style={"textAlign": "center", "color": "#9ca3af", "whiteSpace": "nowrap"}),
            html.Td(ratio,    style={"textAlign": "center"}),
            html.Td(momentum, style={"textAlign": "center"}),
            html.Td(
                dbc.Button("×", id={"type": "rrg-remove", "index": aid},
                           color="link", size="sm",
                           style={"color": "#ef5350", "padding": "0 4px", "lineHeight": 1}),
            ),
        ], style=row_style))

    if not rows:
        return html.Div()

    _th = {"fontSize": "0.72rem", "color": "#6b7280", "fontWeight": "normal",
           "padding": "3px 8px", "borderBottom": "1px solid #374151", "whiteSpace": "nowrap"}

    return html.Div(html.Table([
        html.Thead(html.Tr([
            html.Th("",         style={**_th, "width": "16px", "padding": "3px 4px"}),
            html.Th("Ticker",   style={**_th, "paddingLeft": "6px"}),
            html.Th("Nombre",   style=_th),
            html.Th("Semana",   style={**_th, "textAlign": "center"}),
            html.Th("RS-Ratio", style={**_th, "textAlign": "center"}),
            html.Th("RS-Mom.",  style={**_th, "textAlign": "center"}),
            html.Th("",         style={**_th, "width": "24px", "padding": "3px 2px"}),
        ])),
        html.Tbody(rows),
    ], style={"borderCollapse": "collapse", "fontSize": "0.80rem"}),
    style={"display": "inline-block", "maxWidth": "100%", "overflowX": "auto"})


def _hex_to_rgb(hex_color: str) -> str:
    h = hex_color.lstrip("#")
    r, g, b = int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)
    return f"{r},{g},{b}"
