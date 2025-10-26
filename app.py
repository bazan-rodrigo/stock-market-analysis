# -*- coding: utf-8 -*-
"""
Archivo principal de la aplicacion Dash.
Incluye autenticacion de usuario (login/logout) y control de acceso.
"""

from flask import Flask, request, redirect, url_for
from flask_login import LoginManager, UserMixin, login_user, logout_user, current_user
import dash
from dash import html, dcc
import dash_bootstrap_components as dbc
from config.config import get_config
from sqlalchemy import select
from services.db import get_session
from models.db_models import User
from werkzeug.security import check_password_hash
from services.auth_service import authenticate_user, get_user_by_id

cfg = get_config()
server = Flask(__name__)
server.secret_key = cfg["SECRET_KEY"]

# Configuracion de Flask-Login
login_manager = LoginManager()
login_manager.init_app(server)
login_manager.login_view = "/login"

# Clase adaptadora de usuario (Flask-Login requiere heredar de UserMixin)
class UserLogin(UserMixin):
    def __init__(self, user):
        self.id = user.id
        self.username = user.username
        self.role = user.role

@login_manager.user_loader
def load_user(user_id):
    user = get_user_by_id(int(user_id))
    return UserLogin(user) if user else None

# Ruta de login basico
@server.route("/login", methods=["GET", "POST"])
def login_page():
    if request.method == "POST":
        username = request.form.get("username")
        password = request.form.get("password")

        user = authenticate_user(username, password)
        if user:
            login_user(UserLogin(user))
            return redirect("/")
        else:
            return "<h3>Login incorrecto</h3><a href='/login'>Volver</a>"

    return """
        <h2>Login</h2>
        <form method='POST'>
            Usuario: <input name='username' type='text'><br>
            Clave: <input name='password' type='password'><br>
            <button type='submit'>Entrar</button>
        </form>
    """

# Logout
@server.route("/logout")
def logout():
    logout_user()
    return redirect("/login")

# ----------------------------------------------------------
# DASH APP
# ----------------------------------------------------------
app = dash.Dash(
    __name__,
    server=server,
    suppress_callback_exceptions=True,
    external_stylesheets=[dbc.themes.BOOTSTRAP],
)

app.title = "Stock Market Analysis"

# ==========================================================
# LAYOUT GENERAL
# ==========================================================
app.layout = dbc.Container([
    dbc.NavbarSimple(brand="Stock Market Analysis", color="dark", dark=True,
        children=[
            dbc.NavItem(dbc.NavLink("Inicio", href="/")),
            dbc.NavItem(dbc.NavLink("Activos", href="/admin-assets")),
            dbc.NavItem(dbc.NavLink("Importar activos", href="/import-assets")),
            dbc.NavItem(dbc.NavLink("Errores de actualización", href="/failed-updates")),
            dbc.NavItem(dbc.NavLink("Usuarios (admin)", href="/admin-users")),
            dbc.NavItem(dbc.NavLink("Logout", href="/logout")),
        ]),
    dcc.Location(id="url", refresh=False),
    html.Div(id="page-content")
], fluid=True)

# ==========================================================
# CALLBACKS
# ==========================================================
from ui.callbacks import register_callbacks
register_callbacks(app)

# ==========================================================
# CONTROL DE ACCESO (opcional)
# ==========================================================
@app.server.before_request
def restrict_to_authenticated():
    """
    Middleware para evitar acceso a rutas Dash sin login.
    Permite acceder a /login y /_dash-component-suites.
    """
    if request.path.startswith("/_dash") or request.path.startswith("/login"):
        return  # Permitir recursos internos de Dash o login
    if not current_user.is_authenticated:
        return redirect("/login")

if __name__ == "__main__":
    app.run_server(host="0.0.0.0", port=8050, debug=True)
