import dash
import dash_bootstrap_components as dbc
from dash import dcc, html

_BG  = "#111827"
_CARD= {"backgroundColor": "#1f2937", "border": "1px solid #374151", "borderRadius": "8px"}


def _ratio_card(label, value, fmt=".2f", suffix="", color=None):
    if value is None:
        txt = "—"
        col = "#6b7280"
    else:
        txt = f"{value:{fmt}}{suffix}"
        col = color or "#f59e0b"
    return dbc.Col(dbc.Card(dbc.CardBody([
        html.Div(label, className="text-muted", style={"fontSize": "0.72rem",
                 "textTransform": "uppercase", "letterSpacing": "0.05em"}),
        html.Div(txt, style={"fontSize": "1.4rem", "fontWeight": "700", "color": col}),
    ]), style=_CARD), xs=6, sm=4, md=3, lg=2, className="mb-2")


def layout(**kwargs):
    from flask_login import current_user
    if not current_user.is_authenticated:
        return html.Div()

    from app.services.fundamental_service import get_assets_with_fundamentals
    assets = get_assets_with_fundamentals()
    opts   = [{"label": f"{a.ticker} — {a.name}", "value": a.id} for a in assets]

    return html.Div([
        dbc.Row([
            dbc.Col(html.H4("Análisis de Fundamentales", className="mb-0"), width="auto"),
            dbc.Col(
                html.Small("Datos trimestrales y ratios de valuación por activo.",
                           className="text-muted", style={"fontSize": "0.75rem"}),
                className="d-flex align-items-center",
            ),
        ], className="mb-3 align-items-center"),

        dbc.Row([
            dbc.Col(
                dcc.Dropdown(id="fund-asset-select", options=opts,
                             placeholder="Seleccioná un activo...",
                             style={"fontSize": "0.82rem"}),
                md=5,
            ),
        ], className="mb-3"),

        dbc.Alert(id="fund-alert", is_open=False, dismissable=True, className="mb-2"),

        dcc.Loading(
            html.Div(id="fund-content"),
            type="circle", color="#dee2e6",
        ),
    ], style={"padding": "0 8px"})


dash.register_page(__name__, path="/fundamentos", title="Análisis de Fundamentales", layout=layout)
