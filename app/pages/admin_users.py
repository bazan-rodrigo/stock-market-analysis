import dash
import dash_bootstrap_components as dbc
from dash import html

from app.components.abm import make_abm_layout

_COLUMNS = [
    {"name": "ID", "id": "id"},
    {"name": "Usuario", "id": "username"},
    {"name": "Rol", "id": "role"},
    {"name": "Activo", "id": "active"},
    {"name": "Creado", "id": "created_at"},
]

_FORM = [
    dbc.Row([
        dbc.Col([dbc.Label("Usuario"), dbc.Input(id="users-f-username", placeholder="usuario")]),
        dbc.Col([dbc.Label("Rol"), dbc.Select(id="users-f-role", options=[
            {"label": "Admin", "value": "admin"},
            {"label": "Analista", "value": "analyst"},
        ])]),
    ], className="mb-3"),
    dbc.Row([
        dbc.Col([
            dbc.Label("Contraseña (dejar vacío para no cambiar)"),
            dbc.Input(id="users-f-password", type="password", placeholder="Nueva contraseña"),
        ]),
        dbc.Col([
            dbc.Label("Activo"),
            dbc.Switch(id="users-f-active", value=True, label="Sí"),
        ]),
    ]),
]


def layout(**kwargs):
    from flask_login import current_user
    if not current_user.is_authenticated or not current_user.is_admin:
        return html.Div("Acceso denegado", className="text-danger mt-4")
    return make_abm_layout("users", "Usuarios", _COLUMNS, _FORM)


dash.register_page(__name__, path="/admin/users", title="Usuarios", layout=layout)
