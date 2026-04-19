import dash
import dash_bootstrap_components as dbc
from dash import html

_HELP = (
    "Pivots S/R: detecta extremos locales (máximos y mínimos) en el precio y agrupa "
    "niveles cercanos en zonas. Perfil de Volumen (VPVR): identifica los rangos de precio "
    "donde más volumen se operó (HVN) y el punto de mayor actividad (POC)."
)


def _field(label, id_, min_, max_, step, desc):
    return dbc.Col([
        dbc.Label(label, className="small fw-semibold mb-0"),
        dbc.Input(id=id_, type="number", min=min_, max=max_, step=step, size="sm"),
        html.Small(desc, className="text-muted d-block mt-1", style={"fontSize": "0.72rem", "lineHeight": "1.3"}),
    ], md=4, className="mb-3")


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
                       "Cantidad de barras diarias hacia atrás a analizar. 252 ≈ 1 año de trading. "
                       "Más días captura niveles históricos más lejanos pero puede incluir zonas ya irrelevantes."),
            ]),

            _section("Pivot S/R — Extremos locales de precio"),
            dbc.Row([
                _field("Ventana (barras)", "sr-pivot-window", 2, 30, 1,
                       "Barras a cada lado para considerar un punto como extremo local. "
                       "Ej: ventana=5 → el máximo debe ser el más alto en ±5 velas. "
                       "Más alto = niveles más significativos pero menos frecuentes."),
                _field("Agrupamiento (%)", "sr-cluster-pct", 0.1, 5.0, 0.1,
                       "Niveles dentro de este porcentaje de diferencia se fusionan en una sola zona. "
                       "Ej: 0.5% → niveles a $100 y $100.40 se unen. "
                       "Valores bajos = zonas más precisas; altos = zonas más amplias."),
                _field("Mín. toques", "sr-min-touches", 1, 10, 1,
                       "Veces mínimas que el precio debe haber tocado un nivel para mostrarlo. "
                       "Con 1 aparece cualquier extremo; con 2+ solo los que el precio respetó más de una vez."),
            ]),

            _section("Perfil de Volumen (VPVR) — Nodos de alto volumen"),
            dbc.Row([
                _field("Buckets de precio", "sr-vpvr-buckets", 20, 500, 10,
                       "Divide el rango de precios en N franjas y suma el volumen operado en cada una. "
                       "Más buckets = más granularidad. 100 es un buen balance para la mayoría de activos."),
                _field("Factor HVN", "sr-hvn-factor", 0.1, 5.0, 0.1,
                       "Un bucket se considera nodo de alto volumen (HVN) si su volumen supera "
                       "el promedio × este factor. Factor=1.0 → todos los buckets por encima del promedio. "
                       "Factor=1.5 → solo los más activos. Mayor factor = menos niveles mostrados."),
            ]),

            dbc.Button("Guardar", id="sr-btn-save", color="primary", size="sm", className="mt-1"),
            dbc.Alert(id="sr-alert", is_open=False, dismissable=True, className="mt-2 small"),
        ], className="py-2 px-3")),
    ])


dash.register_page(__name__, path="/admin/sr-config", title="S/R Config", layout=layout)
