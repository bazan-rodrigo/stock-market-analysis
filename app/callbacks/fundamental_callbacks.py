from collections import defaultdict

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


def _ratio_card(key, label, display, color=None, tip=None):
    """Devuelve (dbc.Col, dbc.Tooltip|None)."""
    tip_id = f"fund-tip-{key}"
    label_children = [
        html.Span(label, style={"fontSize": "0.7rem", "textTransform": "uppercase",
                                 "letterSpacing": "0.05em"}),
    ]
    if tip:
        label_children.append(
            html.Span(" ⓘ", id=tip_id,
                      style={"cursor": "help", "fontSize": "0.65rem", "color": "#6b7280",
                             "verticalAlign": "super"})
        )
    col = dbc.Col(dbc.Card(dbc.CardBody([
        html.Div(label_children, className="text-muted mb-1"),
        html.Div(display, style={"fontSize": "1.3rem", "fontWeight": "700",
                                  "color": color or "#f59e0b"}),
    ]), style=_CARD), xs=6, sm=4, md=3, lg=2, className="mb-2")

    tooltip = dbc.Tooltip(tip, target=tip_id, placement="top") if tip else None
    return col, tooltip


def _ratio_section(definitions, snap):
    """Construye las tarjetas de ratios y sus tooltips."""
    cols, tips = [], []
    for key, label, display, color, tip in definitions:
        col, tooltip = _ratio_card(key, label, display, color, tip)
        cols.append(col)
        if tooltip:
            tips.append(tooltip)
    return html.Div([dbc.Row(cols, className="g-2 mb-3")] + tips)


def _to_annual(quarters: list[dict]) -> list[dict]:
    _SUM  = {"revenue", "gross_profit", "operating_income", "net_income", "ebitda", "fcf", "eps_actual"}
    _LAST = {"total_debt", "equity", "shares"}

    by_year: dict = defaultdict(lambda: {k: None for k in _SUM | _LAST} | {"_n": 0})
    for q in sorted(quarters, key=lambda x: x["period"]):
        year = q["period"][:4]
        d = by_year[year]
        d["_n"] += 1
        for k in _SUM:
            if q.get(k) is not None:
                d[k] = (d[k] or 0) + q[k]
        for k in _LAST:
            if q.get(k) is not None:
                d[k] = q[k]

    result = []
    for year in sorted(by_year):
        d = by_year[year]
        row = {"period": year}
        row.update({k: d[k] for k in _SUM | _LAST})
        if d["_n"] < 4:
            row["_partial"] = True
        result.append(row)
    return result


def _bar_chart(data, y_key, title, color="#60a5fa", pct=False):
    xs = [q["period"] for q in data]
    ys = [q[y_key] for q in data]
    if all(v is None for v in ys):
        return None
    scale = 100 if pct else 1e-6
    ys_s  = [v * scale if v is not None else None for v in ys]
    sfx   = "%" if pct else "M"
    colors = ["#6b7280" if q.get("_partial") else color for q in data]
    fig = go.Figure(go.Bar(
        x=xs, y=ys_s,
        marker_color=colors,
        text=[f"{v:.1f}{sfx}{'*' if q.get('_partial') else ''}" if v is not None else ""
              for v, q in zip(ys_s, data)],
        textposition="outside",
        textfont=dict(size=10, color="#dee2e6"),
        cliponaxis=False,
    ))
    vals    = [v for v in ys_s if v is not None]
    ymax    = max(vals, default=1)
    ymin    = min(vals, default=0)
    padding = max(abs(ymax), abs(ymin)) * 0.2 or 1
    fig.update_layout(
        title=dict(text=title, font=dict(color="#9ca3af", size=13), x=0),
        plot_bgcolor=_BG, paper_bgcolor=_BG,
        font=dict(color="#dee2e6", size=10),
        margin=dict(l=40, r=10, t=40, b=40),
        xaxis=dict(tickfont=dict(size=9), gridcolor="#1f2937"),
        yaxis=dict(ticksuffix=sfx, gridcolor="#1f2937",
                   range=[min(ymin - padding, 0), ymax + padding]),
        showlegend=False,
    )
    return fig


def _graph(fig, h=240):
    if fig is None:
        return html.Div()
    from dash import dcc
    return dbc.Col(
        dbc.Card(dbc.CardBody(
            dcc.Graph(figure=fig, config={"displayModeBar": False},
                      style={"height": f"{h}px"}),
            style={"padding": "8px"}
        ), style=_CARD),
        md=6, className="mb-2"
    )


def _charts_row(data):
    return dbc.Row([
        _graph(_bar_chart(data, "revenue",          "Revenue",        "#60a5fa")),
        _graph(_bar_chart(data, "net_income",       "Net Income",     "#4ade80")),
        _graph(_bar_chart(data, "gross_profit",     "Gross Profit",   "#a78bfa")),
        _graph(_bar_chart(data, "ebitda",           "EBITDA",         "#f59e0b")),
        _graph(_bar_chart(data, "fcf",              "Free Cash Flow", "#34d399")),
        _graph(_bar_chart(data, "eps_actual",       "EPS",            "#f472b6")),
    ], className="g-2")


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
            dbc.Alert("No hay datos fundamentales para este activo. "
                      "Ejecutá la actualización desde Datos de Mercado → "
                      "Actualización de fundamentales.",
                      color="warning"),
        ), "", False, "info"

    upd = snap.get("updated_at") or "—"

    _cv = _color_val

    ratio_defs = [
        # (key, label, display, color, tooltip)
        ("pe_ttm",    "P/E TTM",          _val(snap.get("pe_ttm"),  ".1f", "x"), None,
         "Precio actual / (Net Income últimos 4 trimestres / Acciones en circulación)"),
        ("pb",        "P/B",              _val(snap.get("pb"),      ".2f", "x"), None,
         "Precio actual / (Equity / Acciones en circulación) — último trimestre"),
        ("ps_ttm",    "P/S TTM",          _val(snap.get("ps_ttm"),  ".2f", "x"), None,
         "Precio actual / (Revenue últimos 4 trimestres / Acciones en circulación)"),
        ("roic",      "ROIC",             _pct(snap.get("roic")),   _cv(snap.get("roic")),
         "Si la fuente provee NOPAT e Invested Capital promedio: NOPAT TTM / IC promedio. "
         "Sino (ej. Yahoo Finance): Net Income TTM / (Equity + Total Debt)."),
        ("net_mg",    "Margen Neto",      _pct(snap.get("net_margin")),      _cv(snap.get("net_margin")),
         "Net Income / Revenue — último trimestre disponible"),
        ("gross_mg",  "Margen Bruto",     _pct(snap.get("gross_margin")),    _cv(snap.get("gross_margin")),
         "Gross Profit / Revenue — último trimestre disponible"),
        ("op_mg",     "Margen Operativo", _pct(snap.get("operating_margin")),_cv(snap.get("operating_margin")),
         "Operating Income / Revenue — último trimestre disponible"),
        ("de",        "Deuda/Equity",     _val(snap.get("debt_to_equity"), ".2f", "x"), None,
         "Total Debt / Equity — último trimestre disponible"),
        ("rev_yoy",   "Revenue YoY",      _pct(snap.get("revenue_growth_yoy")), _cv(snap.get("revenue_growth_yoy")),
         "Variación del Revenue del último trimestre vs el mismo trimestre del año anterior: (Q0 − Q4) / |Q4|"),
        ("eps_yoy",   "EPS YoY",          _pct(snap.get("eps_growth_yoy")),  _cv(snap.get("eps_growth_yoy")),
         "Variación del Net Income del último trimestre vs el mismo trimestre del año anterior: (Q0 − Q4) / |Q4|"),
        ("pe_yoy",    "P/E YoY",          _pct(snap.get("pe_growth_yoy")),   _cv(snap.get("pe_growth_yoy")),
         "Variación del P/E TTM actual vs el P/E TTM de hace 365 días "
         "(usando el precio más cercano a esa fecha del historial de precios)"),
    ]

    annual = _to_annual(quarters)
    _s     = {"fontWeight": "600", "fontSize": "0.85rem"}

    content = html.Div([
        html.Div([
            html.Span("Ratios actuales", style=_s),
            html.Span(f" — datos al {upd}", className="text-muted ms-2",
                      style={"fontSize": "0.75rem"}),
        ], className="mb-2"),
        _ratio_section(ratio_defs, snap),
        html.Hr(style={"borderColor": "#374151"}),
        dbc.Tabs([
            dbc.Tab(_charts_row(quarters), label="Trimestral", tab_id="q"),
            dbc.Tab(
                html.Div([
                    html.Div("* año incompleto (menos de 4 trimestres)",
                             className="text-muted mb-2",
                             style={"fontSize": "0.72rem"}),
                    _charts_row(annual),
                ]),
                label="Anual", tab_id="a",
            ),
        ], active_tab="q", className="mt-2"),
    ])

    return content, "", False, "info"
