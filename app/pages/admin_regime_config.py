import dash
import dash_bootstrap_components as dbc
from dash import html

_HELP_ALGO = (
    "El algoritmo calcula la EMA del precio de cierre y mide su pendiente relativa en N barras. "
    "Si la pendiente supera el umbral y el precio está sobre la EMA → Alcista. "
    "Si la pendiente es menor al umbral negativo y el precio está bajo la EMA → Bajista. "
    "En cualquier otro caso → Lateral. "
    "El cambio de régimen solo se confirma si se mantiene durante N barras consecutivas (anti-whipsaw)."
)


def _field(label, id_, min_, max_, step, help_text):
    return dbc.Col([
        dbc.Label(label, className="fw-semibold"),
        dbc.Input(id=id_, type="number", min=min_, max=max_, step=step),
        dbc.FormText(help_text, className="text-muted"),
    ], md=4, className="mb-3")


def layout(**kwargs):
    from flask_login import current_user
    if not current_user.is_authenticated or not current_user.is_admin:
        return html.Div("Acceso denegado", className="text-danger mt-4")

    return html.Div([
        html.H3("Configuración de régimen de mercado", className="mb-3"),
        dbc.Alert(_HELP_ALGO, color="info", className="mb-4"),

        dbc.Card(dbc.CardBody([
            html.H5("Período de la EMA por temporalidad", className="mb-3 text-secondary"),
            dbc.Row([
                _field(
                    "EMA diaria (períodos)",
                    "regime-ema-d",
                    10, 500, 1,
                    "Barras para calcular la EMA sobre el gráfico diario. "
                    "Valores altos (ej. 200) capturan tendencias de largo plazo. "
                    "Valores bajos son más reactivos al precio reciente.",
                ),
                _field(
                    "EMA semanal (períodos)",
                    "regime-ema-w",
                    5, 300, 1,
                    "Barras para la EMA sobre velas semanales. "
                    "Por defecto 50, equivale a ~un año de historia semanal.",
                ),
                _field(
                    "EMA mensual (períodos)",
                    "regime-ema-m",
                    3, 100, 1,
                    "Barras para la EMA sobre velas mensuales. "
                    "Por defecto 20, equivale a ~20 meses de historia.",
                ),
            ]),

            html.Hr(),
            html.H5("Parámetros de la pendiente", className="mb-3 text-secondary"),
            dbc.Row([
                _field(
                    "Lookback de pendiente (barras)",
                    "regime-slope-lb",
                    1, 100, 1,
                    "Cuántas barras atrás comparar para calcular la pendiente de la EMA. "
                    "Ejemplo: 20 → compara EMA[hoy] con EMA[hace 20 barras]. "
                    "Valores mayores suavizan y reducen señales falsas.",
                ),
                _field(
                    "Umbral de pendiente (%)",
                    "regime-slope-thr",
                    0.01, 20.0, 0.01,
                    "Variación mínima de la EMA (en %) en N barras para considerar tendencia. "
                    "Ejemplo: 0.5 → la EMA debe subir/bajar más del 0.5 % en el lookback. "
                    "Valores altos exigen pendientes más pronunciadas antes de declarar tendencia.",
                ),
            ]),

            html.Hr(),
            html.H5("Confirmación de cambio de régimen", className="mb-3 text-secondary"),
            dbc.Row([
                _field(
                    "Barras de confirmación",
                    "regime-confirm",
                    1, 20, 1,
                    "Cantidad de barras consecutivas con el mismo régimen crudo antes de oficializarlo. "
                    "Evita cambios bruscos por una sola barra fuera del rango. "
                    "Ejemplo: 3 → el nuevo régimen debe observarse 3 barras seguidas para activarse.",
                ),
            ]),

            dbc.Button("Guardar configuración", id="regime-btn-save", color="primary", size="sm", className="mt-2"),
            dbc.Alert(id="regime-alert", is_open=False, dismissable=True, className="mt-3"),
        ])),
    ])


dash.register_page(__name__, path="/admin/regime-config", title="Configuración de régimen", layout=layout)
