"""
Fábrica de la aplicación Dash + Flask.
Orden de inicialización:
  1. Logging
  2. Dash app
  3. Flask-Login
  4. Protección de rutas (before_request)
  5. Ruta de logout
  6. Teardown de sesión de BD
  7. Registro de páginas (importando los módulos)
  8. Registro de callbacks (importando los módulos)
  9. Layout principal
 10. APScheduler
"""
import logging

import dash
import dash_bootstrap_components as dbc
from dash import dcc, html
from flask import redirect, request
from flask_login import current_user, logout_user

from app.logging_setup import configure_logging

logger = logging.getLogger(__name__)


def create_app():
    configure_logging()

    # -----------------------------------------------------------------
    # 1. Crear la app Dash
    # -----------------------------------------------------------------
    dash_app = dash.Dash(
        __name__,
        use_pages=True,
        pages_folder="",      # Sin auto-discovery; importamos manualmente
        suppress_callback_exceptions=True,
        external_stylesheets=[
            dbc.themes.DARKLY,
            dbc.icons.FONT_AWESOME,
        ],
        title="Stock Market Analysis",
    )
    server = dash_app.server

    # -----------------------------------------------------------------
    # 2. Configurar Flask
    # -----------------------------------------------------------------
    from app.config import Config
    server.secret_key = Config.SECRET_KEY

    # -----------------------------------------------------------------
    # 3. Flask-Login
    # -----------------------------------------------------------------
    from app.auth.manager import login_manager
    login_manager.init_app(server)

    # -----------------------------------------------------------------
    # 4. Protección de rutas con before_request
    # -----------------------------------------------------------------
    _DASH_INTERNAL_PREFIXES = (
        "/_dash-",
        "/_reload-hash",
        "/assets/",
    )
    _PUBLIC_PATHS = ("/login",)

    @server.route("/")
    def index():
        if not current_user.is_authenticated:
            return redirect("/login")
        return redirect("/screener")

    @server.before_request
    def require_login():
        # Permitir Dash internals y assets estáticos sin auth
        for prefix in _DASH_INTERNAL_PREFIXES:
            if request.path.startswith(prefix):
                return None
        if request.path in _PUBLIC_PATHS:
            return None
        if not current_user.is_authenticated:
            return redirect("/login")
        return None

    # -----------------------------------------------------------------
    # 5. Ruta de logout
    # -----------------------------------------------------------------
    @server.route("/logout")
    def logout():
        logout_user()
        return redirect("/login")

    # -----------------------------------------------------------------
    # 6. Teardown de sesión de BD
    # -----------------------------------------------------------------
    from app.database import teardown_session
    server.teardown_appcontext(teardown_session)

    # -----------------------------------------------------------------
    # 7. Registrar páginas (importar módulos)
    # -----------------------------------------------------------------
    import app.pages.login               # noqa: F401
    import app.pages.screener            # noqa: F401
    import app.pages.chart               # noqa: F401
    import app.pages.assets_list         # noqa: F401
    import app.pages.assets_import       # noqa: F401
    import app.pages.prices              # noqa: F401
    import app.pages.admin_users         # noqa: F401
    import app.pages.admin_countries     # noqa: F401
    import app.pages.admin_currencies    # noqa: F401
    import app.pages.admin_markets       # noqa: F401
    import app.pages.admin_instrument_types  # noqa: F401
    import app.pages.admin_sectors       # noqa: F401
    import app.pages.admin_industries    # noqa: F401
    import app.pages.admin_price_sources # noqa: F401

    # -----------------------------------------------------------------
    # 8. Registrar callbacks
    # -----------------------------------------------------------------
    import app.callbacks.auth_callbacks       # noqa: F401
    import app.callbacks.reference_callbacks  # noqa: F401
    import app.callbacks.asset_callbacks      # noqa: F401
    import app.callbacks.import_callbacks     # noqa: F401
    import app.callbacks.price_callbacks      # noqa: F401
    import app.callbacks.chart_callbacks      # noqa: F401
    import app.callbacks.screener_callbacks   # noqa: F401

    # -----------------------------------------------------------------
    # 9. Layout principal
    # -----------------------------------------------------------------
    def serve_layout():
        """
        Se llama en cada carga inicial de página.
        Muestra/oculta la navbar según el estado de autenticación.
        """
        if not current_user.is_authenticated:
            return html.Div([
                dcc.Location(id="url"),
                dash.page_container,
            ])

        from app.components.navbar import build_navbar
        return html.Div([
            dcc.Location(id="url"),
            build_navbar(),
            dbc.Container(dash.page_container, fluid=True),
        ])

    dash_app.layout = serve_layout

    # -----------------------------------------------------------------
    # 10. APScheduler
    # -----------------------------------------------------------------
    from app.services.scheduler_service import start_scheduler
    try:
        start_scheduler()
    except Exception as exc:
        logger.warning("No se pudo iniciar el scheduler: %s", exc)

    logger.info("Aplicación inicializada correctamente")
    return server, dash_app
