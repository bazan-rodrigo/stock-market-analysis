import dash
import dash_bootstrap_components as dbc
from dash import html

_HELP = (
    "Identifica grandes caídas históricas: desde un ATH hasta recuperación. "
    "En el gráfico se muestran como triángulos rojos en el mínimo de cada caída. "
    "Recalculá los snapshots para aplicar cambios."
)


def layout(**kwargs):
    from flask_login import current_user
    if not current_user.is_authenticated or not current_user.is_admin:
        return html.Div("Acceso denegado", className="text-danger mt-4")

    return html.Div([
        html.H4("Drawdowns — Configuración", className="mb-2"),
        dbc.Alert(_HELP, color="info", className="mb-3 small py-2"),

        dbc.Card(dbc.CardBody([
            dbc.Row([
                dbc.Col([
                    dbc.Label("Profundidad mínima (%)", className="small fw-semibold mb-0"),
                    dbc.Input(id="dd-min-depth", type="number", min=1, max=90, step=0.5, size="sm"),
                    dbc.Tooltip(
                        "Solo se registran caídas que superen este % desde el ATH previo. "
                        "Acciones individuales: 20–30 %. Índices: 10–15 %. Cripto: 40–50 %.",
                        target="dd-min-depth", placement="top",
                    ),
                ], md=3, className="mb-2"),
            ]),

            dbc.Button("Guardar", id="dd-btn-save", color="primary", size="sm", className="mt-1"),
            dbc.Alert(id="dd-alert", is_open=False, dismissable=True, className="mt-2 small"),
        ], className="py-2 px-3")),
    ])


dash.register_page(__name__, path="/admin/drawdown-config", title="Drawdowns", layout=layout)
