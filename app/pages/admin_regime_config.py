import dash
import dash_bootstrap_components as dbc
from dash import html

_HELP = (
    "El régimen se calcula comparando dos medias móviles simples (SMA). "
    "Si la SMA rápida supera a la lenta por más del umbral lateral → alcista. "
    "Si la SMA rápida cae por debajo de la lenta en más del umbral → bajista. "
    "Si la diferencia está dentro del umbral → lateral."
)


def layout(**kwargs):
    from flask_login import current_user
    if not current_user.is_authenticated or not current_user.is_admin:
        return html.Div("Acceso denegado", className="text-danger mt-4")

    return html.Div([
        html.H3("Configuración de régimen de mercado", className="mb-3"),
        dbc.Alert(_HELP, color="info", className="mb-4"),

        dbc.Card(dbc.CardBody([
            dbc.Row([
                dbc.Col([
                    dbc.Label("SMA rápida (períodos)"),
                    dbc.Input(id="regime-fast", type="number", min=5, max=500, step=1),
                ], md=3),
                dbc.Col([
                    dbc.Label("SMA lenta (períodos)"),
                    dbc.Input(id="regime-slow", type="number", min=10, max=500, step=1),
                ], md=3),
                dbc.Col([
                    dbc.Label("Umbral lateral (%)"),
                    dbc.Input(id="regime-band", type="number", min=0.1, max=20, step=0.1),
                    dbc.FormText("Diferencia mínima entre SMAs para considerar tendencia."),
                ], md=3),
            ], className="mb-3"),
            dbc.Button("Guardar", id="regime-btn-save", color="primary", size="sm"),
            dbc.Alert(id="regime-alert", is_open=False, dismissable=True, className="mt-3"),
        ])),
    ])


dash.register_page(__name__, path="/admin/regime-config", title="Configuración de régimen", layout=layout)
