import dash
import dash_bootstrap_components as dbc
from dash import dcc, html


def layout(**kwargs):
    return dbc.Container(
        dbc.Row(
            dbc.Col(
                dbc.Card(
                    dbc.CardBody(
                        [
                            html.H4("Stock Market Analysis", className="card-title text-center mb-4"),
                            dbc.Alert(id="login-alert", is_open=False, color="danger", dismissable=True),
                            dbc.Label("Usuario"),
                            dbc.Input(id="login-username", type="text", placeholder="Usuario", className="mb-3", n_submit=0),
                            dbc.Label("Contraseña"),
                            dbc.Input(id="login-password", type="password", placeholder="Contraseña", className="mb-4", n_submit=0),
                            dbc.Button("Iniciar sesión", id="login-btn", color="primary", className="w-100"),
                            dcc.Location(id="login-redirect"),
                        ]
                    ),
                    className="shadow-sm p-3",
                ),
                md=4,
                className="mx-auto mt-5",
            )
        ),
        fluid=True,
    )


dash.register_page(__name__, path="/login", title="Iniciar sesión", layout=layout)
