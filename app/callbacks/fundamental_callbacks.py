import plotly.graph_objects as go
from dash import Input, Output, callback, html
import dash_bootstrap_components as dbc

import app.services.fundamental_service as svc

_BG   = "#111827"
_CARD = {"backgroundColor": "#1f2937", "border": "1px solid #374151", "borderRadius": "8px"}


def _pct(v):
    return f"{v*100:+.1f}%" if v is not None else "—"

def _val(v, fmt=".2f", suffix="x"):
    return f"{v:{fmt}}{suffix}" if v is not None else "—"

def _color_val(v):
    if v is None: return "#6b7280"
    return "#4ade80" if v >= 0 else "#f87171"


def _ratio_card(label, display, color=None):
    return dbc.Col(dbc.Card(dbc.CardBody([
        html.Div(label, className="text-muted mb-1",
                 style={"fontSize": "0.7rem", "textTransform": "uppercase", "letterSpacing": "0.05em"}),
        html.Div(display, style={"fontSize": "1.3rem", "fontWeight": "700",
                                  "color": color or "#f59e0b"}),
    ]), style=_CARD), xs=6, sm=4, md=3, lg=2, className="mb-2")


def _bar_chart(quarters, y_key, title, color="#60a5fa", pct=False):
    xs = [q["period"] for q in quarters]
    ys = [q[y_key] for q in quarters]
    if all(v is None for v in ys):
        return None
    scale = 100 if pct else 1e-6
    ys_s  = [v * scale if v is not None else None for v in ys]
    sfx   = "%" if pct else "M"
    fig   = go.Figure(go.Bar(
        x=xs, y=ys_s,
        marker_color=color,
        text=[f"{v:.1f}{sfx}" if v is not None else "" for v in ys_s],
        textposition="outside",
        textfont=dict(size=10, color="#dee2e6"),
        cliponaxis=False,
    ))
    ymax = max((v for v in ys_s if v is not None), default=1)
    fig.update_layout(
        title=dict(text=title, font=dict(color="#9ca3af", size=13), x=0),
        plot_bgcolor=_BG, paper_bgcolor=_BG,
        font=dict(color="#dee2e6", size=10),
        margin=dict(l=40, r=10, t=40, b=40),
        xaxis=dict(tickfont=dict(size=9), gridcolor="#1f2937"),
        yaxis=dict(ticksuffix=sfx, gridcolor="#1f2937",
                   range=[0, ymax * 1.2]),
        showlegend=False,
    )
    return fig


@callback(
    Output("fund-content", "children"),
    Output("fund-alert",   "children"),
    Output("fund-alert",   "is_open"),
    Output("fund-alert",   "color"),
    Input("fund-asset-select", "value"),
)
def load_fundamentals(asset_id):
    if not asset_id:
        return html.Div(), "", False, "info"

    try:
        data = svc.get_asset_fundamentals(int(asset_id))
    except Exception as exc:
        return html.Div(), f"Error al cargar datos: {exc}", True, "danger"

    quarters = data["quarters"]
    snap     = data["snapshot"]

    if not quarters:
        return html.Div(
            dbc.Alert("No hay datos fundamentales para este activo. Ejecutá la actualización desde la pantalla de administración.",
                      color="warning"),
        ), "", False, "info"

    upd = snap.get("updated_at") or "—"

    # ── Tarjetas de ratios actuales ───────────────────────────────────────────
    ratio_cards = dbc.Row([
        _ratio_card("P/E TTM",          _val(snap.get("pe_ttm"), ".1f")),
        _ratio_card("P/B",              _val(snap.get("pb"),     ".2f")),
        _ratio_card("P/S TTM",          _val(snap.get("ps_ttm"),".2f")),
        _ratio_card("Margen Neto",      _pct(snap.get("net_margin")),
                    _color_val(snap.get("net_margin"))),
        _ratio_card("Margen Bruto",     _pct(snap.get("gross_margin")),
                    _color_val(snap.get("gross_margin"))),
        _ratio_card("Margen Operativo", _pct(snap.get("operating_margin")),
                    _color_val(snap.get("operating_margin"))),
        _ratio_card("Deuda/Equity",     _val(snap.get("debt_to_equity"), ".2f", "x")),
        _ratio_card("Revenue YoY",      _pct(snap.get("revenue_growth_yoy")),
                    _color_val(snap.get("revenue_growth_yoy"))),
        _ratio_card("EPS YoY",          _pct(snap.get("eps_growth_yoy")),
                    _color_val(snap.get("eps_growth_yoy"))),
    ], className="g-2 mb-3")

    # ── Gráficos trimestrales ─────────────────────────────────────────────────
    def _graph(fig, h=240):
        if fig is None:
            return html.Div()
        return dbc.Col(
            dbc.Card(dbc.CardBody(
                __import__("dash").dcc.Graph(figure=fig, config={"displayModeBar": False},
                                             style={"height": f"{h}px"}),
                style={"padding": "8px"}
            ), style=_CARD),
            md=6, className="mb-2"
        )

    charts = dbc.Row([
        _graph(_bar_chart(quarters, "revenue",         "Revenue",           "#60a5fa")),
        _graph(_bar_chart(quarters, "net_income",      "Net Income",        "#4ade80")),
        _graph(_bar_chart(quarters, "gross_profit",    "Gross Profit",      "#a78bfa")),
        _graph(_bar_chart(quarters, "ebitda",          "EBITDA",            "#f59e0b")),
        _graph(_bar_chart(quarters, "fcf",             "Free Cash Flow",    "#34d399")),
        _graph(_bar_chart(quarters, "eps_actual",      "EPS", "#f472b6", pct=False)),
    ], className="g-2")

    content = html.Div([
        html.Div([
            html.Span("Ratios actuales", style={"fontWeight": "600", "fontSize": "0.85rem"}),
            html.Span(f" — datos al {upd}", className="text-muted ms-2",
                      style={"fontSize": "0.75rem"}),
        ], className="mb-2"),
        ratio_cards,
        html.Hr(style={"borderColor": "#374151"}),
        html.Div("Evolución trimestral", className="mb-2",
                 style={"fontWeight": "600", "fontSize": "0.85rem"}),
        charts,
    ])

    return content, "", False, "info"
