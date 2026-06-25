import dash
import dash_bootstrap_components as dbc
from dash import html

_CARD = {"backgroundColor": "#1f2937", "border": "1px solid #374151", "borderRadius": "8px"}


def layout(**kwargs):
    from flask_login import current_user
    if not current_user.is_authenticated or not current_user.is_admin:
        return html.Div()

    from app.services.app_config_service import is_public_access_enabled
    enabled = is_public_access_enabled()

    return html.Div([
        html.H4("Configuración de la aplicación", className="mb-4"),

        dbc.Alert(id="appsettings-alert", is_open=False, dismissable=True, className="mb-3"),

        dbc.Card(dbc.CardBody([
            dbc.Row([
                dbc.Col([
                    html.Div("Acceso sin login", style={"fontWeight": "600", "fontSize": "0.95rem"}),
                    html.Div(
                        "Permite navegar todas las pantallas sin iniciar sesión. "
                        "El menú de administración permanece oculto para visitantes.",
                        className="text-muted", style={"fontSize": "0.8rem", "marginTop": "2px"},
                    ),
                ]),
                dbc.Col(
                    dbc.Switch(
                        id="appsettings-public-access",
                        value=enabled,
                        label="Habilitado" if enabled else "Deshabilitado",
                        className="ms-auto",
                    ),
                    width="auto",
                    className="d-flex align-items-center",
                ),
            ], align="center"),
        ]), style=_CARD),

    ], style={"padding": "0 8px"})


dash.register_page(
    __name__,
    path="/admin/app-settings",
    title="Configuración de la app",
    layout=layout,
)
