import dash
import dash_bootstrap_components as dbc
from dash import html

_HELP = (
    "Los eventos de drawdown identifican las grandes caídas históricas de cada activo. "
    "Se detecta un evento cuando el precio cae desde un máximo histórico (ATH) y luego "
    "recupera ese nivel. Solo se registran las caídas que superan el umbral configurado. "
    "En el gráfico se muestran como triángulos rojos en el punto más bajo de cada caída, "
    "con el porcentaje de caída indicado. Recalculá los snapshots para aplicar cambios."
)


def layout(**kwargs):
    from flask_login import current_user
    if not current_user.is_authenticated or not current_user.is_admin:
        return html.Div("Acceso denegado", className="text-danger mt-4")

    return html.Div([
        html.H3("Configuración de drawdowns", className="mb-3"),
        dbc.Alert(_HELP, color="info", className="mb-4"),

        dbc.Card(dbc.CardBody([
            dbc.Row([
                dbc.Col([
                    dbc.Label("Profundidad mínima (%)", className="fw-semibold"),
                    dbc.Input(id="dd-min-depth", type="number", min=1, max=90, step=0.5),
                    dbc.FormText(
                        "Solo se registran caídas que superen este porcentaje desde el ATH previo. "
                        "Ejemplo: 20 → solo caídas mayores al 20%. "
                        "Valores típicos: acciones individuales 20-30%, índices 10-15%, cripto 40-50%.",
                        className="text-muted",
                    ),
                ], md=4),
            ], className="mb-3"),

            dbc.Button("Guardar", id="dd-btn-save", color="primary", size="sm"),
            dbc.Alert(id="dd-alert", is_open=False, dismissable=True, className="mt-3"),
        ])),
    ])


dash.register_page(__name__, path="/admin/drawdown-config", title="Configuración de drawdowns", layout=layout)
