import dash
import dash_bootstrap_components as dbc
from dash import html

from app.components.ui_constants import BORDER_CARD

_PRICE_META = {
    "Yahoo Finance": {
        "mecanismo": "Librería yfinance (Python)",
        "notas": "Soporta cualquier ticker de Yahoo Finance: acciones, ETFs, índices, bonos, FX.",
    },
    "Ambito": {
        "mecanismo": "API REST pública de Ámbito Financiero",
        "notas": "Solo acepta el ticker RIESGO_PAIS_AR. Endpoint: mercados.ambito.com",
    },
    "Calculado": {
        "mecanismo": "Cálculo interno",
        "notas": "Precios derivados de otros activos del sistema (ratios, spreads, conversiones).",
    },
}

_FUND_META = {
    "Yahoo Finance": {
        "mecanismo": "Librería yfinance (Python)",
        "campos": [
            "Revenue", "Gross Profit", "Operating Income", "Net Income",
            "EBITDA", "Total Debt", "Equity", "Shares", "FCF",
            "Operating CF", "EPS actual", "EPS estimado",
        ],
    },
}

_CARD_HEADER = {"backgroundColor": "#2c2c2c", "borderBottom": f"1px solid {BORDER_CARD}"}
_CARD_BODY   = {"backgroundColor": "#1f2937"}
_CARD_STYLE  = {"border": f"1px solid {BORDER_CARD}", "height": "100%"}

_LABEL_STYLE = {"fontSize": "0.78rem", "color": "#9ca3af", "fontWeight": "600"}
_VALUE_STYLE = {"fontSize": "0.78rem", "color": "#d1d5db"}
_NOTE_STYLE  = {"fontSize": "0.78rem", "color": "#6b7280"}
_DESC_STYLE  = {"fontSize": "0.83rem", "color": "#d1d5db"}


def _row(label, value, note=False):
    return html.Div([
        html.Span(f"{label}: ", style=_LABEL_STYLE),
        html.Span(value, style=_NOTE_STYLE if note else _VALUE_STYLE),
    ], className="mb-1")


def _price_card(name, description, meta):
    body = [html.P(description or "—", className="mb-2", style=_DESC_STYLE)]
    body.append(_row("Mecanismo", meta.get("mecanismo", "—")))
    if "notas" in meta:
        body.append(_row("Notas", meta["notas"], note=True))

    return dbc.Col(
        dbc.Card([
            dbc.CardHeader(
                html.Strong(name, style={"color": "#e5e7eb", "fontSize": "0.92rem"}),
                style=_CARD_HEADER,
            ),
            dbc.CardBody(body, style=_CARD_BODY),
        ], style=_CARD_STYLE),
        md=4, className="mb-3",
    )


def _fund_card(name, description, meta):
    body = [html.P(description or "—", className="mb-2", style=_DESC_STYLE)]
    body.append(_row("Mecanismo", meta.get("mecanismo", "—")))
    if "campos" in meta:
        body.append(html.Div([
            html.Span("Campos: ", style=_LABEL_STYLE),
            html.Span(", ".join(meta["campos"]), style=_NOTE_STYLE),
        ]))

    return dbc.Col(
        dbc.Card([
            dbc.CardHeader(
                html.Strong(name, style={"color": "#e5e7eb", "fontSize": "0.92rem"}),
                style=_CARD_HEADER,
            ),
            dbc.CardBody(body, style=_CARD_BODY),
        ], style=_CARD_STYLE),
        md=4, className="mb-3",
    )


def layout(**kwargs):
    from flask_login import current_user
    if not current_user.is_authenticated or not current_user.is_admin:
        return html.Div("Acceso denegado", className="text-danger mt-4")

    from app.database import get_session
    from app.models import PriceSource, FundamentalSource
    s = get_session()
    price_sources = s.query(PriceSource).order_by(PriceSource.id).all()
    fund_sources  = s.query(FundamentalSource).order_by(FundamentalSource.id).all()

    price_cards = [_price_card(ps.name, ps.description, _PRICE_META.get(ps.name, {}))
                   for ps in price_sources]
    fund_cards  = [_fund_card(fs.name, fs.description, _FUND_META.get(fs.name, {}))
                   for fs in fund_sources]

    return html.Div([
        html.H3("Fuentes de Datos", className="mb-4"),

        html.H5("Fuentes de Precios", className="mb-3", style={"color": "#9ca3af"}),
        dbc.Row(price_cards),

        html.H5("Fuentes de Fundamentales", className="mb-3 mt-2", style={"color": "#9ca3af"}),
        dbc.Row(fund_cards),
    ])


dash.register_page(__name__, path="/admin/price-sources", title="Fuentes de datos", layout=layout)
