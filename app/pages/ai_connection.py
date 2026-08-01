"""Conexión IA: generar y revocar el token con el que un cliente de IA se
conecta al servidor MCP de esta instalación.

Abierta a TODOS los roles: cada usuario genera el suyo y ve exactamente lo que
vería en las pantallas — un analista, sus estrategias y las públicas; un
administrador, todo.
"""
import dash
import dash_bootstrap_components as dbc
from dash import dcc, html

from app.components.help import page_header
from app.components.ui_constants import TEXT_MUTED

_QUE_ES = (
    "Conectás tu propia cuenta de IA (Claude, ChatGPT o cualquier cliente que "
    "hable MCP) para consultar en lenguaje natural los datos de la plataforma. "
    "Tu cuenta de IA es tuya: la plataforma no la ve ni la guarda. Lo único "
    "que se guarda acá es un token que le dice al sistema que quien pregunta "
    "sos vos, para mostrarte lo mismo que verías en pantalla y nada más."
)


def layout(**kwargs):
    from flask_login import current_user

    if not current_user.is_authenticated:
        return html.Div()

    return html.Div([
        dcc.Store(id="ia-refresh", data=0),

        page_header("Conexión IA", "conexion-ia"),
        dbc.Alert(_QUE_ES, color="info", className="mb-3 small py-2"),

        dbc.Card(dbc.CardBody([
            html.Div(id="ia-estado", className="mb-3"),

            dbc.Button("Generar token", id="ia-btn-generar",
                       color="primary", size="sm", className="me-2"),
            dbc.Button("Revocar", id="ia-btn-revocar",
                       color="danger", size="sm", outline=True),

            html.Div(id="ia-token-nuevo", className="mt-3"),
            dbc.Alert(id="ia-alert", is_open=False, dismissable=True,
                      className="mt-3 mb-0"),
        ]), className="mb-3", style={"maxWidth": "760px"}),

        dbc.Card(dbc.CardBody([
            html.H6("Qué puede hacer", className="mb-2"),
            html.Ul([
                html.Li("Consultar el catálogo de indicadores, señales y "
                        "estrategias que ya ves."),
                html.Li("Leer rankings de estrategias y la evolución de un "
                        "puntaje."),
                html.Li("Buscar en el manual para explicarte cómo funciona "
                        "cada cálculo."),
            ], className="small mb-3"),
            html.H6("Qué NO puede hacer", className="mb-2"),
            html.Ul([
                html.Li("Crear, editar ni borrar señales: el catálogo de "
                        "señales lo mantiene un administrador desde su "
                        "pantalla."),
                html.Li("Modificar o borrar datos de ningún tipo."),
                html.Li("Ver algo que no verías vos entrando a la aplicación."),
            ], className="small mb-0"),
        ]), style={"maxWidth": "760px", "color": TEXT_MUTED}),
    ], style={"padding": "0 8px"})


dash.register_page(__name__, path="/ia", title="Conexión IA", layout=layout)
