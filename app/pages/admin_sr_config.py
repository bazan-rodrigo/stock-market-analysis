import dash
import dash_bootstrap_components as dbc
from dash import html

_HELP = (
    "Pivots S/R: detecta extremos locales (máximos y mínimos) en el precio y agrupa "
    "niveles cercanos en zonas. Perfil de Volumen (VPVR): identifica los rangos de precio "
    "donde más volumen se operó (HVN) y el punto de mayor actividad (POC)."
)


def _field(label, id_, min_, max_, step, tooltip):
    return dbc.Col([
        dbc.Label(label, className="small fw-semibold mb-0"),
        dbc.Input(id=id_, type="number", min=min_, max=max_, step=step, size="sm"),
        dbc.Tooltip(tooltip, target=id_, placement="top"),
    ], md=3, className="mb-2")


def _section(title):
    return html.P(title, className="text-secondary small fw-semibold mb-1 mt-2 border-bottom pb-1")


def layout(**kwargs):
    from flask_login import current_user
    if not current_user.is_authenticated or not current_user.is_admin:
        return html.Div("Acceso denegado", className="text-danger mt-4")

    return html.Div([
        html.H4("Soporte / Resistencia — Configuración", className="mb-2"),
        dbc.Alert(_HELP, color="info", className="mb-3 small py-2"),

        dbc.Card(dbc.CardBody([
            _section("General"),
            dbc.Row([
                _field("Lookback (días)", "sr-lookback", 50, 1000, 1,
                       "Barras diarias a analizar. 252 ≈ 1 año de trading."),
            ]),

            _section("Pivot S/R"),
            dbc.Row([
                _field("Ventana (barras)", "sr-pivot-window", 2, 30, 1,
                       "Barras a cada lado para identificar un extremo local. Más alto = niveles más significativos."),
                _field("Agrupamiento (%)", "sr-cluster-pct", 0.1, 5.0, 0.1,
                       "Niveles dentro de este % se fusionan en uno solo."),
                _field("Mín. toques", "sr-min-touches", 1, 10, 1,
                       "Cantidad mínima de veces que el precio debe tocar un nivel para considerarlo válido."),
            ]),

            _section("Perfil de Volumen (VPVR)"),
            dbc.Row([
                _field("Buckets de precio", "sr-vpvr-buckets", 20, 500, 10,
                       "Cantidad de rangos de precio para distribuir el volumen. Más = más granular."),
                _field("Factor HVN", "sr-hvn-factor", 0.1, 5.0, 0.1,
                       "Un bucket es HVN si su volumen supera la media × este factor. Mayor = menos niveles."),
            ]),

            dbc.Button("Guardar", id="sr-btn-save", color="primary", size="sm", className="mt-1"),
            dbc.Alert(id="sr-alert", is_open=False, dismissable=True, className="mt-2 small"),
        ], className="py-2 px-3")),
    ])


dash.register_page(__name__, path="/admin/sr-config", title="S/R Config", layout=layout)
