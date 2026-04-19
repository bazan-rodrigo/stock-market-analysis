import dash
import dash_bootstrap_components as dbc
from dash import html

_HELP = (
    "Identifica grandes caídas históricas: desde un máximo histórico (ATH) hasta la recuperación. "
    "En el gráfico se muestran como triángulos rojos en el mínimo de cada caída. "
    "En el screener aparece la profundidad del drawdown actual y los 3 peores históricos. "
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
                    html.Small(
                        "Caídas menores a este % desde el ATH previo se ignoran. "
                        "Valores sugeridos: acciones individuales 20–30 %, índices 10–15 %, cripto 40–50 %. "
                        "Un valor bajo registra más eventos; uno alto solo captura crisis significativas.",
                        className="text-muted d-block mt-1", style={"fontSize": "0.72rem", "lineHeight": "1.3"},
                    ),
                ], md=5, className="mb-2"),
            ]),

            dbc.Button("Guardar", id="dd-btn-save", color="primary", size="sm", className="mt-1"),
            dbc.Alert(id="dd-alert", is_open=False, dismissable=True, className="mt-2 small"),
        ], className="py-2 px-3")),
    ])


dash.register_page(__name__, path="/admin/drawdown-config", title="Drawdowns", layout=layout)
