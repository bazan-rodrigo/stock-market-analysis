# -*- coding: utf-8 -*-
"""
Pantalla de administracion de usuarios.
Solo accesible para usuarios con rol admin.
Toda la logica de negocio esta en services/user_service.py
"""

from dash import html, Output, Input, State
import dash_bootstrap_components as dbc
from flask_login import current_user
from core.logging_config import get_logger
from services.user_service import create_user, get_all_users

logger = get_logger()

def admin_users_layout():
    """Devuelve el layout de la pantalla de administracion de usuarios."""
    if not current_user.is_authenticated:
        return html.Div("Debe iniciar sesion para acceder.", style={"color": "red"})
    if current_user.role != "admin":
        return html.Div("Acceso denegado. Solo el administrador puede ver esta pagina.", style={"color": "red"})

    users = get_all_users()

    table = dbc.Table.from_dataframe(
        data={
            "Usuario": [u["username"] for u in users],
            "Rol": [u["role"] for u in users],
            "Activo": [u["is_active"] for u in users],
        },
        striped=True,
        bordered=True,
        hover=True
    ) if users else html.Div("No hay usuarios registrados.")

    return dbc.Container([
        html.H3("Administracion de Usuarios"),
        dbc.Row([
            dbc.Col([
                dbc.Input(id="username", placeholder="Nombre de usuario"),
                dbc.Input(id="password", placeholder="Clave", type="password", className="mt-2"),
                dbc.Select(
                    id="role",
                    options=[
                        {"label": "Admin", "value": "admin"},
                        {"label": "Analyst", "value": "analyst"},
                    ],
                    value="analyst",
                    className="mt-2"
                ),
                dbc.Button("Agregar Usuario", id="btn-add-user", color="primary", className="mt-2"),
                html.Div(id="admin-message", className="mt-3"),
            ], width=4),
        ]),
        html.Hr(),
        html.Div(id="user-table", children=[table]),
    ])

def register_admin_callbacks(app):
    """Registra callbacks para la pantalla de administracion."""
    @app.callback(
        Output("admin-message", "children"),
        Output("user-table", "children"),
        Input("btn-add-user", "n_clicks"),
        State("username", "value"),
        State("password", "value"),
        State("role", "value"),
        prevent_initial_call=True
    )
    def on_add_user(n, username, password, role):
        if not current_user.is_authenticated or current_user.role != "admin":
            return "Acceso denegado", html.Div()

        msg = create_user(username, password, role)
        users = get_all_users()

        table = dbc.Table.from_dataframe(
            data={
                "Usuario": [u["username"] for u in users],
                "Rol": [u["role"] for u in users],
                "Activo": [u["is_active"] for u in users],
            },
            striped=True, bordered=True, hover=True
        )

        return msg, table