import logging

from flask_login import LoginManager

from app.database import get_session
from app.models import User

logger = logging.getLogger(__name__)

# Sin anonymous_user custom: el modo invitado (GuestUser con acceso público
# que operaba como admin) se ELIMINÓ a pedido del usuario (jul-2026) — siempre
# hay que loguearse con un usuario real. El anónimo default de Flask-Login
# tiene is_authenticated=False, así que before_request (app/__init__.py)
# redirige toda ruta no pública al login.
login_manager = LoginManager()
login_manager.login_view = "/login"
login_manager.login_message = "Iniciá sesión para acceder."
login_manager.login_message_category = "warning"


@login_manager.user_loader
def load_user(user_id: str):
    try:
        s = get_session()
        return s.get(User, int(user_id))
    except Exception:
        logger.warning("No se pudo cargar el usuario %s (BD no disponible)", user_id)
        return None
