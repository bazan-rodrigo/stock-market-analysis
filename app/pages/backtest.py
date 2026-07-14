import dash
import dash_bootstrap_components as dbc
from dash import dcc, html

_HELP = (
    "Mide si el ranking de la estrategia predice retornos: cada fecha parte "
    "los activos elegibles en cuantiles por score y mide el retorno posterior "
    "de cada cuantil a varios horizontes (en ruedas). La señal se ejecuta al "
    "cierre SIGUIENTE (sin look-ahead) y solo se scorea un activo en fechas "
    "donde cotizó (los scores arrastrados quedan afuera). Cada corrida queda "
    "guardada con su configuración para poder comparar."
)

_LBL = {"fontSize": "0.8rem"}
_IN = {"fontSize": "0.82rem"}


def layout(**kwargs):
    from flask_login import current_user
    if not current_user.is_authenticated:
        return html.Div()

    return html.Div([
        dcc.Interval(id="bt-interval", interval=1000, disabled=True),

        dbc.Row([
            dbc.Col(html.H4("Backtest de Estrategia", className="mb-0"),
                    width="auto"),
        ], className="mb-2 align-items-center"),
        dbc.Alert(_HELP, color="info", className="mb-3 small py-2"),

        # ── Configuración del run ─────────────────────────────────────────
        dbc.Card(dbc.CardBody([
            dbc.Row([
                dbc.Col([
                    dbc.Label("Estrategia", style=_LBL),
                    dcc.Dropdown(id="bt-strategy-sel",
                                 placeholder="Seleccionar estrategia...",
                                 style=_IN),
                ], md=3),
                dbc.Col([
                    dbc.Label("Horizontes (ruedas)", style=_LBL),
                    dcc.Dropdown(
                        id="bt-horizons", multi=True,
                        options=[{"label": f"{h}", "value": h}
                                 for h in (1, 5, 10, 20, 60, 120, 250)],
                        value=[1, 5, 20, 60], style=_IN),
                ], md=3),
                dbc.Col([
                    dbc.Label("Cuantiles", style=_LBL),
                    dbc.Input(id="bt-quantiles", type="number", value=10,
                              min=2, max=20, step=1, style=_IN),
                ], md=1),
                dbc.Col([
                    dbc.Label("Mín. activos", style=_LBL),
                    dbc.Input(id="bt-min-assets", type="number", value=20,
                              min=2, step=1, style=_IN),
                ], md=1),
                dbc.Col([
                    dbc.Label("Desde (opcional)", style=_LBL),
                    dcc.DatePickerSingle(id="bt-date-from", date=None,
                                         display_format="YYYY-MM-DD",
                                         clearable=True),
                ], md=2, className="d-flex flex-column"),
                dbc.Col([
                    dbc.Label(" ", style=_LBL),
                    dbc.Button("Ejecutar backtest", id="bt-btn-run",
                               color="primary", size="sm",
                               style={"display": "block"}),
                ], md=2, className="d-flex flex-column"),
            ], className="g-2"),

            dbc.Progress(id="bt-progress", value=0, striped=True,
                         animated=True, className="mt-2",
                         style={"display": "none", "height": "16px",
                                "fontSize": "0.72rem"}),
            dbc.Alert(id="bt-alert", is_open=False, dismissable=True,
                      className="mt-2 small py-1"),
        ]), className="mb-3",
            style={"backgroundColor": "#1f2937", "border": "1px solid #374151"}),

        # ── Runs guardados ────────────────────────────────────────────────
        dbc.Row([
            dbc.Col([
                dbc.Label("Corridas guardadas", style=_LBL),
                dcc.Dropdown(id="bt-run-sel", placeholder="Elegir corrida...",
                             style=_IN),
            ], md=6),
        ], className="mb-3 g-2"),

        # ── Resultados ────────────────────────────────────────────────────
        dcc.Loading(html.Div(id="bt-results"), type="circle", color="#dee2e6"),

    ], style={"padding": "0 8px"})


dash.register_page(__name__, path="/backtest",
                   title="Backtest de Estrategia", layout=layout)
