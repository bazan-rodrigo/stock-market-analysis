from dash import Input, Output, State, callback, no_update
from flask_login import login_user, current_user

from app.database import get_session
from app.models import User


@callback(
    Output("login-redirect", "href"),
    Output("login-alert", "children"),
    Output("login-alert", "is_open"),
    Input("login-btn", "n_clicks"),
    Input("login-username", "n_submit"),
    Input("login-password", "n_submit"),
    State("login-username", "value"),
    State("login-password", "value"),
    prevent_initial_call=True,
)
def handle_login(n_clicks, user_submit, pass_submit, username, password):
    if not username or not password:
        return no_update, "Ingresá usuario y contraseña.", True

    s = get_session()
    user = s.query(User).filter(User.username == username.strip()).first()

    if user is None or not user.check_password(password):
        return no_update, "Usuario o contraseña incorrectos.", True

    if not user.is_active:
        return no_update, "Usuario inactivo. Contactá al administrador.", True

    login_user(user, remember=False)
    return "/screener", no_update, False
