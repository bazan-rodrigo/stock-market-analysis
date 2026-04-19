import dash
import dash_bootstrap_components as dbc
import plotly.graph_objects as go
from dash import dcc, html

_DIMS = [
    ("sector",   "Sectores"),
    ("industry", "Industrias"),
    ("country",  "Países"),
    ("itype",    "Tipos"),
    ("market",   "Mercados"),
]

_BG = "#111827"


def _score_label(score):
    if score is None:
        return None, "#555"
    if score >= 50:
        return "Alcista", "#4caf50"
    if score >= 20:
        return "Mejorando", "#a5d6a7"
    if score <= -50:
        return "Bajista", "#ef5350"
    if score <= -20:
        return "Deteriorando", "#ef9a9a"
    return "Lateral", "#90a4ae"


def _score_badge(score):
    if score is None:
        return html.Td("—", style={"color": "#555", "textAlign": "center"})
    label, color = _score_label(score)
    return html.Td(
        html.Div([
            html.Div(label, style={"fontWeight": "bold", "fontSize": "0.78rem", "lineHeight": "1.2"}),
            html.Div(f"{score:+.0f}", style={"fontSize": "0.68rem", "opacity": "0.7"}),
        ]),
        style={"color": color, "textAlign": "center", "width": "80px"},
    )


def _build_table(dim_data: dict) -> html.Table:
    rows_sorted = sorted(
        dim_data.values(),
        key=lambda g: (g.get("d") or 0),
        reverse=True,
    )
    tbody_rows = []
    for g in rows_sorted:
        tbody_rows.append(html.Tr([
            html.Td(g["name"],
                    style={"fontSize": "0.82rem", "whiteSpace": "nowrap",
                           "overflow": "hidden", "textOverflow": "ellipsis",
                           "maxWidth": "200px"}),
            html.Td(str(g["n"]),
                    style={"textAlign": "center", "color": "#aaa", "fontSize": "0.78rem"}),
            _score_badge(g.get("d")),
            _score_badge(g.get("w")),
            _score_badge(g.get("m")),
        ]))

    _th = {"fontSize": "0.78rem", "color": "#aaa", "fontWeight": "normal"}
    return html.Table([
        html.Thead(html.Tr([
            html.Th("Grupo",   style=_th),
            html.Th("N",       style={**_th, "textAlign": "center", "width": "40px"}),
            html.Th("Score Diario",   style={**_th, "textAlign": "center", "width": "80px"}),
            html.Th("Score Semanal", style={**_th, "textAlign": "center", "width": "80px"}),
            html.Th("Score Mensual", style={**_th, "textAlign": "center", "width": "80px"}),
        ]), style={"borderBottom": "1px solid #444"}),
        html.Tbody(tbody_rows),
    ], style={"width": "100%", "borderCollapse": "collapse"})


def _quad_info(sm, sd):
    if sm is None or sd is None:
        return "Sin datos", "#9e9e9e"
    if sm >= 0 and sd >= 0:
        return "Alcista confirmado", "#4caf50"
    if sm < 0 and sd >= 0:
        return "Rebotando", "#64b5f6"
    if sm >= 0 and sd < 0:
        return "Corrigiendo", "#ffa726"
    return "Bajista confirmado", "#ef5350"


def _build_quadrant_figure(dim_data: dict) -> go.Figure:
    fig = go.Figure()

    shapes = [
        dict(type="rect", x0=-105, y0=0,    x1=0,   y1=105,
             fillcolor="rgba(100,181,246,0.08)", line_width=0),
        dict(type="rect", x0=0,    y0=0,    x1=105, y1=105,
             fillcolor="rgba(76,175,80,0.08)",  line_width=0),
        dict(type="rect", x0=-105, y0=-105, x1=0,   y1=0,
             fillcolor="rgba(239,83,80,0.08)",  line_width=0),
        dict(type="rect", x0=0,    y0=-105, x1=105, y1=0,
             fillcolor="rgba(255,167,38,0.08)", line_width=0),
        dict(type="line", x0=0, y0=-105, x1=0, y1=105,
             line=dict(color="#4b5563", width=1, dash="dot")),
        dict(type="line", x0=-105, y0=0, x1=105, y1=0,
             line=dict(color="#4b5563", width=1, dash="dot")),
    ]

    quad_annotations = [
        dict(x=-52, y=100, text="Rebotando",          font=dict(color="#64b5f6", size=11),
             showarrow=False, xanchor="center", yanchor="top"),
        dict(x=52,  y=100, text="Alcista confirmado", font=dict(color="#4caf50", size=11),
             showarrow=False, xanchor="center", yanchor="top"),
        dict(x=-52, y=-100, text="Bajista confirmado", font=dict(color="#ef5350", size=11),
             showarrow=False, xanchor="center", yanchor="bottom"),
        dict(x=52,  y=-100, text="Corrigiendo",        font=dict(color="#ffa726", size=11),
             showarrow=False, xanchor="center", yanchor="bottom"),
    ]

    for g in dim_data.values():
        sm = g.get("m")
        sd = g.get("d")
        if sm is None or sd is None:
            continue
        quad_label, color = _quad_info(sm, sd)
        sw_str = f"{g['w']:+.0f}" if g.get("w") is not None else "—"
        hover = (
            f"<b>{g['name']}</b><br>"
            f"Score Diario: {sd:+.0f}<br>"
            f"Score Semanal: {sw_str}<br>"
            f"Score Mensual: {sm:+.0f}<br>"
            f"N activos: {g['n']}<br>"
            f"<i>{quad_label}</i>"
        )
        size = max(10, min(28, 10 + g["n"] * 1.5))
        fig.add_trace(go.Scatter(
            x=[sm], y=[sd],
            mode="markers+text",
            marker=dict(size=size, color=color, opacity=0.85,
                        line=dict(color="#1f2937", width=1)),
            text=[g["name"]],
            textposition="top center",
            textfont=dict(color=color, size=9),
            hovertemplate=hover + "<extra></extra>",
            showlegend=False,
        ))

    fig.update_layout(
        plot_bgcolor=_BG,
        paper_bgcolor=_BG,
        font=dict(color="#dee2e6", size=11),
        shapes=shapes,
        annotations=quad_annotations,
        xaxis=dict(
            title="Score Mensual  →  tendencia de largo plazo",
            range=[-105, 105],
            gridcolor="#1f2937",
            zerolinecolor="#4b5563",
            tickfont=dict(size=10),
        ),
        yaxis=dict(
            title="Score Diario  →  momentum / dirección reciente",
            range=[-105, 105],
            gridcolor="#1f2937",
            zerolinecolor="#4b5563",
            tickfont=dict(size=10),
        ),
        margin=dict(l=60, r=20, t=15, b=50),
        hovermode="closest",
    )
    return fig


def _legend_card():
    _st = {"fontSize": "0.78rem", "marginBottom": "6px", "color": "#d1d5db"}
    _card_style = {"backgroundColor": "#1f2937", "border": "1px solid #374151"}
    return dbc.Card(
        dbc.CardBody([
            html.H6("¿Cómo leer el Mapa de Mercado?",
                    className="mb-2", style={"fontSize": "0.85rem", "color": "#9ca3af"}),
            html.P([
                html.Strong("Score de tendencia (−100 a +100): ", style={"color": "#e5e7eb"}),
                "Promedio de los scores de régimen de todos los activos activos del grupo. "
                "Cada activo recibe un score según su régimen técnico: "
                "Alcista fuerte = +100, Alcista = +60, Lateral = 0, Bajista = −60, Bajista fuerte = −100.",
            ], style=_st),
            html.P([
                html.Strong("Columnas D / S / M: ", style={"color": "#e5e7eb"}),
                "Score calculado sobre el régimen ",
                html.Strong("D", style={"color": "#e5e7eb"}), "iario (EMA 200), ",
                html.Strong("S", style={"color": "#e5e7eb"}), "emanal (EMA 50) y ",
                html.Strong("M", style={"color": "#e5e7eb"}), "ensual (EMA 20) de cada activo.",
            ], style=_st),
            html.P([
                html.Strong("Categorías: ", style={"color": "#e5e7eb"}),
                html.Span("Alcista", style={"color": "#4caf50", "fontWeight": "bold"}), " (≥ 50)  ·  ",
                html.Span("Mejorando", style={"color": "#a5d6a7", "fontWeight": "bold"}), " (20–49)  ·  ",
                html.Span("Lateral", style={"color": "#90a4ae", "fontWeight": "bold"}), " (−19 a 19)  ·  ",
                html.Span("Deteriorando", style={"color": "#ef9a9a", "fontWeight": "bold"}), " (−20 a −49)  ·  ",
                html.Span("Bajista", style={"color": "#ef5350", "fontWeight": "bold"}), " (≤ −50).",
            ], style=_st),
            html.Hr(style={"borderColor": "#374151", "margin": "8px 0"}),
            html.P([
                html.Strong("Cuadrantes: ", style={"color": "#e5e7eb"}),
                "Cada grupo se posiciona según su ",
                html.Strong("Score Mensual", style={"color": "#e5e7eb"}),
                " (eje X — tendencia de largo plazo) y ",
                html.Strong("Score Diario", style={"color": "#e5e7eb"}),
                " (eje Y — momentum / dirección reciente). "
                "El tamaño del punto refleja la cantidad de activos del grupo.",
            ], style=_st),
            dbc.Row([
                dbc.Col(html.Span("■ Alcista confirmado",
                                  style={"color": "#4caf50", "fontSize": "0.75rem"}), width="auto"),
                dbc.Col(html.Span("■ Rebotando",
                                  style={"color": "#64b5f6", "fontSize": "0.75rem"}), width="auto"),
                dbc.Col(html.Span("■ Corrigiendo",
                                  style={"color": "#ffa726", "fontSize": "0.75rem"}), width="auto"),
                dbc.Col(html.Span("■ Bajista confirmado",
                                  style={"color": "#ef5350", "fontSize": "0.75rem"}), width="auto"),
            ], className="g-3 mt-1"),
        ]),
        className="mt-3",
        style=_card_style,
    )


def layout(**kwargs):
    from flask_login import current_user
    if not current_user.is_authenticated:
        return html.Div()

    return html.Div([
        dbc.Row([
            dbc.Col(html.H4("Mapa de Mercado", className="mb-0"), width="auto"),
            dbc.Col(
                html.Small(
                    "Score de tendencia por grupo. "
                    "Calculado sobre todos los activos activos con snapshot.",
                    className="text-muted",
                    style={"fontSize": "0.75rem"},
                ),
                className="d-flex align-items-center",
            ),
        ], className="mb-3 align-items-center"),

        dbc.Alert(id="market-map-alert", is_open=False, dismissable=True, className="mb-2"),

        dbc.Tabs(
            [dbc.Tab(label=label, tab_id=dim_key) for dim_key, label in _DIMS],
            id="market-map-tabs",
            active_tab="sector",
            className="mb-0",
        ),

        dcc.Loading(
            html.Div(id="market-map-content", className="mt-3"),
            type="circle",
            color="#dee2e6",
        ),

        _legend_card(),

    ], style={"padding": "0 8px"})


dash.register_page(__name__, path="/market-map", title="Mapa de Mercado", layout=layout)
