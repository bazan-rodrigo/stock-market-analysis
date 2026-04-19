import plotly.graph_objects as go
from dash import Input, Output, State, callback, no_update, ALL, ctx
import dash_bootstrap_components as dbc
from dash import html

import app.services.rrg_service as rrg_svc

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
        return current + [new_id], None   # None limpia el dropdown

    if isinstance(trigger, dict) and trigger.get("type") == "rrg-remove":
        return [a for a in (current or []) if a != trigger["index"]], no_update

    return no_update, no_update


# ── Render principal ──────────────────────────────────────────────────────────
@callback(
    Output("rrg-graph",      "figure"),
    Output("rrg-asset-list", "children"),
    Output("rrg-alert",      "children"),
    Output("rrg-alert",      "is_open"),
    Input("rrg-selected-assets",   "data"),
    Input("rrg-benchmark-select",  "value"),
    Input("rrg-tail",              "value"),
)
def render_rrg(asset_ids, benchmark_id, tail_weeks):
    if not benchmark_id:
        return _empty_fig(), html.Div(), "Seleccioná un benchmark para comenzar.", True

    if not asset_ids:
        return _empty_fig(), html.Div(), "", False

    tail_weeks = tail_weeks or 12
    data = rrg_svc.compute_rrg(asset_ids, benchmark_id, tail_weeks)

    skipped = len(asset_ids) - len(data)
    alert_msg = (
        f"{skipped} activo(s) omitido(s) por datos insuficientes (mínimo ~{52 + tail_weeks} semanas)."
        if skipped else ""
    )

    if not data:
        return _empty_fig(), html.Div(), alert_msg or "Sin datos.", True

    fig   = _build_figure(data, tail_weeks)
    table = _build_table(asset_ids, data)
    return fig, table, alert_msg, bool(skipped)


# ── Helpers de figura ─────────────────────────────────────────────────────────
def _empty_fig() -> go.Figure:
    fig = go.Figure()
    _apply_layout(fig, [90, 110], [90, 110])
    return fig


def _build_figure(data: dict, tail_weeks: int) -> go.Figure:
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
        # Opacidad creciente: más antiguo = más transparente
        opacities = [0.15 + 0.85 * (j / max(n - 1, 1)) for j in range(n)]
        sizes     = [3    + 5    * (j / max(n - 1, 1)) for j in range(n)]

        hover = [
            f"<b>{info['ticker']}</b><br>{dates[j]}<br>RS-Ratio: {xs[j]:.2f}<br>RS-Mom: {ys[j]:.2f}"
            for j in range(n)
        ]

        # Trail: línea + puntos con fade
        fig.add_trace(go.Scatter(
            x=xs[:-1], y=ys[:-1],
            mode="lines+markers",
            line=dict(color=color, width=1.5),
            marker=dict(
                size=sizes[:-1],
                color=[f"rgba({_hex_to_rgb(color)},{opacities[j]:.2f})" for j in range(n - 1)],
            ),
            name=info["ticker"],
            legendgroup=info["ticker"],
            showlegend=False,
            hovertemplate="%{customdata}<extra></extra>",
            customdata=hover[:-1],
        ))

        # Punto actual: cuadrado con label
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

    _apply_layout(fig, x_range, y_range)
    return fig


def _apply_layout(fig: go.Figure, x_range: list, y_range: list):
    cx, cy = 100.0, 100.0
    xlo, xhi = x_range
    ylo, yhi = y_range

    shapes = [
        # Cuadrantes
        dict(type="rect", x0=cx, y0=cy, x1=xhi, y1=yhi,
             fillcolor="rgba(27,94,32,0.22)",   line_width=0),   # Leading
        dict(type="rect", x0=xlo, y0=cy, x1=cx, y1=yhi,
             fillcolor="rgba(13,71,161,0.22)",  line_width=0),   # Improving
        dict(type="rect", x0=xlo, y0=ylo, x1=cx, y1=cy,
             fillcolor="rgba(183,28,28,0.22)",  line_width=0),   # Lagging
        dict(type="rect", x0=cx, y0=ylo, x1=xhi, y1=cy,
             fillcolor="rgba(230,119,0,0.18)",  line_width=0),   # Weakening
        # Líneas centrales
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
def _build_table(asset_ids: list, data: dict) -> html.Div:
    rows = []
    for i, aid in enumerate(asset_ids):
        color = _PALETTE[i % len(_PALETTE)]
        info  = data.get(aid)
        ticker = info["ticker"] if info else str(aid)
        name   = info["name"]   if info else "—"
        trail  = info["trail"]  if info else []
        ratio    = f"{trail[-1]['ratio']:.2f}"    if trail else "—"
        momentum = f"{trail[-1]['momentum']:.2f}" if trail else "—"
        date_lbl = trail[-1]["date"]               if trail else "—"

        rows.append(html.Tr([
            html.Td(html.Div(style={
                "width": "12px", "height": "12px",
                "backgroundColor": color, "borderRadius": "2px", "margin": "auto",
            })),
            html.Td(ticker,  style={"fontWeight": "bold",  "fontSize": "0.82rem", "paddingLeft": "6px"}),
            html.Td(name,    style={
                "fontSize": "0.78rem", "color": "#9ca3af",
                "maxWidth": "220px", "overflow": "hidden",
                "textOverflow": "ellipsis", "whiteSpace": "nowrap",
            }),
            html.Td(date_lbl, style={"textAlign": "center", "fontSize": "0.75rem", "color": "#9ca3af"}),
            html.Td(ratio,    style={"textAlign": "center", "fontSize": "0.78rem"}),
            html.Td(momentum, style={"textAlign": "center", "fontSize": "0.78rem"}),
            html.Td(
                dbc.Button("×", id={"type": "rrg-remove", "index": aid},
                           color="link", size="sm",
                           style={"color": "#ef5350", "padding": "0 4px", "lineHeight": 1}),
            ),
        ], style={"borderBottom": "1px solid #1f2937"}))

    if not rows:
        return html.Div()

    _th = {"fontSize": "0.72rem", "color": "#6b7280", "fontWeight": "normal",
           "padding": "4px 6px", "borderBottom": "1px solid #374151"}

    return html.Table([
        html.Thead(html.Tr([
            html.Th("",         style={**_th, "width": "20px"}),
            html.Th("Ticker",   style={**_th, "paddingLeft": "6px"}),
            html.Th("Nombre",   style=_th),
            html.Th("Semana",   style={**_th, "textAlign": "center", "width": "100px"}),
            html.Th("RS-Ratio", style={**_th, "textAlign": "center", "width": "80px"}),
            html.Th("RS-Mom.",  style={**_th, "textAlign": "center", "width": "80px"}),
            html.Th("",         style={**_th, "width": "30px"}),
        ])),
        html.Tbody(rows),
    ], style={"width": "100%", "borderCollapse": "collapse"})


def _hex_to_rgb(hex_color: str) -> str:
    h = hex_color.lstrip("#")
    r, g, b = int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)
    return f"{r},{g},{b}"
