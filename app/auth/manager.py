import logging

from flask_login import AnonymousUserMixin, LoginManager

from app.database import get_session
from app.models import User

logger = logging.getLogger(__name__)


class GuestUser(AnonymousUserMixin):
    """Usuario anónimo que aparece como autenticado cuando el acceso público está habilitado."""

    @property
    def is_authenticated(self):
        from app.services.app_config_service import is_public_access_enabled
        return is_public_access_enabled()

    @property
    def is_admin(self):
        from app.services.app_config_service import is_public_access_enabled
        return is_public_access_enabled()

    @property
    def username(self):
        return ""


login_manager = LoginManager()
login_manager.login_view = "/login"
login_manager.login_message = "Iniciá sesión para acceder."
login_manager.login_message_category = "warning"
login_manager.anonymous_user = GuestUser


@login_manager.user_loader
def load_user(user_id: str):
    try:
        s = get_session()
        return s.get(User, int(user_id))
    except Exception:
        logger.warning("No se pudo cargar el usuario %s (BD no disponible)", user_id)
        return None
