import dash
import dash_bootstrap_components as dbc
from dash import html

_HELP_ALGO = (
    "Calcula la EMA del cierre y mide su pendiente relativa en N barras. "
    "Pendiente > umbral y precio > EMA → Alcista. "
    "Pendiente < −umbral y precio < EMA → Bajista. "
    "Cualquier otro caso → Lateral. "
    "El cambio solo se confirma tras N barras consecutivas (anti-whipsaw)."
)


def _field(label, id_, min_, max_, step, desc):
    return dbc.Col([
        dbc.Label(label, className="small fw-semibold mb-0"),
        dbc.Input(id=id_, type="number", min=min_, max=max_, step=step, size="sm"),
        html.Small(desc, className="text-muted d-block mt-1", style={"fontSize": "0.72rem", "lineHeight": "1.3"}),
    ], md=3, className="mb-2")


def _section(title):
    return html.P(title, className="text-secondary small fw-semibold mb-1 mt-2 border-bottom pb-1")


def layout(**kwargs):
    from flask_login import current_user
    if not current_user.is_authenticated or not current_user.is_admin:
        return html.Div("Acceso denegado", className="text-danger mt-4")

    return html.Div([
        html.H4("Régimen de Tendencia — Configuración", className="mb-2"),
        dbc.Alert(_HELP_ALGO, color="info", className="mb-3 small py-2"),

        dbc.Card(dbc.CardBody([
            _section("Período de la EMA por temporalidad"),
            dbc.Row([
                _field("EMA diaria", "regime-ema-d", 10, 500, 1,
                       "Barras de la EMA sobre velas diarias. Ej: 200 → tendencia largo plazo."),
                _field("EMA semanal", "regime-ema-w", 5, 300, 1,
                       "Barras de la EMA sobre velas semanales. Ej: 50 ≈ 1 año."),
                _field("EMA mensual", "regime-ema-m", 3, 100, 1,
                       "Barras de la EMA sobre velas mensuales. Ej: 20 ≈ 20 meses."),
            ]),

            _section("Parámetros de la pendiente"),
            dbc.Row([
                _field("Lookback pendiente", "regime-slope-lb", 1, 100, 1,
                       "Barras atrás para medir la pendiente. Más barras → señal más suave."),
                _field("Umbral pendiente (%)", "regime-slope-thr", 0.01, 20.0, 0.01,
                       "Variación mínima de la EMA (%) para declarar tendencia. Ej: 0.5 %."),
            ]),

            _section("Confirmación y sub-categorías"),
            dbc.Row([
                _field("Barras confirmación", "regime-confirm", 1, 20, 1,
                       "Barras consecutivas en el nuevo régimen antes de activarlo."),
                _field("Barras naciente", "regime-nascent", 1, 200, 1,
                       "Una zona con menos de N barras se etiqueta 'naciente'."),
                _field("Mult. fuerte", "regime-strong-mult", 1.0, 10.0, 0.1,
                       "Pendiente debe superar umbral × multiplicador para ser 'fuerte'."),
            ]),

            dbc.Button("Guardar", id="regime-btn-save", color="primary", size="sm", className="mt-1"),
            dbc.Alert(id="regime-alert", is_open=False, dismissable=True, className="mt-2 small"),
        ], className="py-2 px-3")),
    ])


dash.register_page(__name__, path="/admin/regime-config", title="Régimen de Tendencia", layout=layout)
