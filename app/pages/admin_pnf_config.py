import dash
import dash_bootstrap_components as dbc
from dash import html

_HELP = (
    "El gráfico Punto y Figura ignora el tiempo: dibuja columnas de X (sube) y O (baja) "
    "en cajas de precio de tamaño fijo. Una columna se revierte cuando el precio retrocede "
    "la cantidad de cajas configurada. Disponible en Análisis de Activo → Gráfico Técnico, "
    "opciones 'P&F' (columnas sobre el gráfico principal) y 'P&F X/O' (clásico con grilla). "
    "Los cambios aplican al volver a cargar el activo en el gráfico."
)


def layout(**kwargs):
    from flask_login import current_user
    if not current_user.is_authenticated or not current_user.is_admin:
        return html.Div("Acceso denegado", className="text-danger mt-4")

    return html.Div([
        html.H4("Punto y Figura — Configuración", className="mb-2"),
        dbc.Alert(_HELP, color="info", className="mb-3 small py-2"),

        dbc.Card(dbc.CardBody([
            dbc.Row([
                dbc.Col([
                    dbc.Label("Método de tamaño de caja", className="small fw-semibold mb-0"),
                    dbc.Select(
                        id="pnf-box-method", size="sm",
                        options=[
                            {"label": "ATR (volatilidad del activo)", "value": "atr"},
                            {"label": "Porcentaje del precio",        "value": "percent"},
                            {"label": "Valor fijo",                   "value": "fixed"},
                        ],
                    ),
                    html.Small(
                        "ATR se adapta a cada activo (recomendado para carteras mixtas). "
                        "Porcentaje escala con el precio. Fijo usa el mismo valor absoluto "
                        "para todos los activos.",
                        className="text-muted d-block mt-1",
                        style={"fontSize": "0.72rem", "lineHeight": "1.3"},
                    ),
                ], md=4, className="mb-2"),
                dbc.Col([
                    dbc.Label("Caja: % del precio", className="small fw-semibold mb-0"),
                    dbc.Input(id="pnf-box-pct", type="number", min=0.1, max=20, step=0.1, size="sm"),
                    html.Small("Usado con método Porcentaje. Clásico: 1 %.",
                               className="text-muted d-block mt-1", style={"fontSize": "0.72rem"}),
                ], md=2, className="mb-2"),
                dbc.Col([
                    dbc.Label("Caja: período ATR", className="small fw-semibold mb-0"),
                    dbc.Input(id="pnf-atr-period", type="number", min=2, max=100, step=1, size="sm"),
                    html.Small("Usado con método ATR. Típico: 14.",
                               className="text-muted d-block mt-1", style={"fontSize": "0.72rem"}),
                ], md=2, className="mb-2"),
                dbc.Col([
                    dbc.Label("Caja: valor fijo", className="small fw-semibold mb-0"),
                    dbc.Input(id="pnf-box-fixed", type="number", min=0.0001, step=0.0001, size="sm"),
                    html.Small("Usado con método Fijo, en unidades de precio.",
                               className="text-muted d-block mt-1", style={"fontSize": "0.72rem"}),
                ], md=2, className="mb-2"),
            ]),
            dbc.Row([
                dbc.Col([
                    dbc.Label("Reversión (cajas)", className="small fw-semibold mb-0"),
                    dbc.Input(id="pnf-reversal", type="number", min=1, max=10, step=1, size="sm"),
                    html.Small(
                        "Cajas en contra para abrir la columna opuesta. El clásico es 3: "
                        "menor valor = más columnas y más ruido; mayor = solo movimientos grandes.",
                        className="text-muted d-block mt-1",
                        style={"fontSize": "0.72rem", "lineHeight": "1.3"},
                    ),
                ], md=4, className="mb-2"),
                dbc.Col([
                    dbc.Label("Fuente de precio", className="small fw-semibold mb-0"),
                    dbc.RadioItems(
                        id="pnf-source",
                        options=[
                            {"label": "Solo cierres",        "value": "close"},
                            {"label": "Máximos y mínimos",   "value": "hl"},
                        ],
                        inline=True, className="small",
                    ),
                    html.Small(
                        "Cierres filtra el ruido intradiario; Máx/Mín (método clásico de "
                        "high/low) captura los extremos de cada rueda.",
                        className="text-muted d-block mt-1",
                        style={"fontSize": "0.72rem", "lineHeight": "1.3"},
                    ),
                ], md=5, className="mb-2"),
            ]),

            dbc.Button("Guardar", id="pnf-btn-save", color="primary", size="sm", className="mt-1"),
            dbc.Alert(id="pnf-alert", is_open=False, dismissable=True, className="mt-2 small"),
        ], className="py-2 px-3")),
    ])


dash.register_page(__name__, path="/admin/pnf-config", title="Punto y Figura", layout=layout)
