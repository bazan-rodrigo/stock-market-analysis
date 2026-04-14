from flask_login import LoginManager

from app.database import get_session
from app.models import User

login_manager = LoginManager()
login_manager.login_view = "/login"
login_manager.login_message = "Iniciá sesión para acceder."
login_manager.login_message_category = "warning"


@login_manager.user_loader
def load_user(user_id: str):
    s = get_session()
    return s.get(User, int(user_id))
