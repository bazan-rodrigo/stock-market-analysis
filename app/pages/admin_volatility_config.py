import dash
import dash_bootstrap_components as dbc
from dash import html

_HELP_ALGO = (
    "Calcula el ATR y lo clasifica por percentiles históricos propios de cada activo y temporalidad. "
    "'Alta' significa que el ATR supera el P_alto de su historia propia, no un valor absoluto. "
    "La duración compara cuánto tiempo lleva el activo en ese régimen contra la distribución "
    "histórica de duraciones del mismo régimen."
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
        html.H4("Volatilidad ATR — Configuración", className="mb-2"),
        dbc.Alert(_HELP_ALGO, color="info", className="mb-3 small py-2"),

        dbc.Card(dbc.CardBody([
            _section("Cálculo del ATR"),
            dbc.Row([
                _field("Período ATR", "vol-atr-period", 2, 100, 1,
                       "Barras para el ATR de Wilder. Estándar: 14. Más bajo = más reactivo."),
                _field("Barras confirmación", "vol-confirm", 1, 20, 1,
                       "Barras consecutivas en el nuevo régimen antes de activarlo. Evita spikes."),
            ]),

            _section("Umbrales de percentil"),
            dbc.Row([
                _field("P_bajo (%)", "vol-pct-low", 5.0, 49.0, 0.5,
                       "ATR por debajo de este percentil → Baja volatilidad. Ej: 25 = cuartil inferior."),
                _field("P_alto (%)", "vol-pct-high", 51.0, 95.0, 0.5,
                       "ATR por encima de este percentil → Alta. Entre P_bajo y P_alto = Normal."),
                _field("P_extremo (%)", "vol-pct-extreme", 60.0, 99.0, 0.5,
                       "ATR por encima de este percentil → Extrema. Debe ser > P_alto."),
            ]),

            _section("Clasificación de duración"),
            dbc.Row([
                _field("Duración corta (%)", "vol-dur-short", 10.0, 49.0, 1.0,
                       "Si la duración cae por debajo de este percentil histórico → Corta. Ej: 33."),
                _field("Duración larga (%)", "vol-dur-long", 51.0, 95.0, 1.0,
                       "Si la duración supera este percentil histórico → Larga. Entre ambos = Media."),
            ]),

            dbc.Button("Guardar", id="vol-btn-save", color="primary", size="sm", className="mt-1"),
            dbc.Alert(id="vol-alert", is_open=False, dismissable=True, className="mt-2 small"),
        ], className="py-2 px-3")),
    ])


dash.register_page(__name__, path="/admin/volatility-config", title="Volatilidad ATR", layout=layout)
