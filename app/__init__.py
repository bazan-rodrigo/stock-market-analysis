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
from flask import redirect, render_template_string, request
from flask_login import current_user, login_user, logout_user

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
        external_scripts=[
            "https://unpkg.com/lightweight-charts@4/dist/lightweight-charts.standalone.production.js",
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
    _PUBLIC_PATHS = ("/login", "/do-login", "/")

    _LOGIN_TEMPLATE = """<!DOCTYPE html>
<html lang="es" data-bs-theme="dark">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Stock Market Analysis – Iniciar sesión</title>
  <link href="https://cdn.jsdelivr.net/npm/bootstrap@5.3.3/dist/css/bootstrap.min.css" rel="stylesheet">
  <style>
    body { background-color: #222; color: #dee2e6; }
    .card { background-color: #2d3338; border: 1px solid #495057; }
    .form-control, .form-control:focus {
      background-color: #1a1d20; color: #dee2e6; border-color: #495057;
    }
    .form-control::placeholder { color: #6c757d; }
  </style>
</head>
<body>
  <div class="container">
    <div class="row justify-content-center mt-5">
      <div class="col-md-4">
        <div class="card shadow p-4">
          <h4 class="text-center mb-4">Stock Market Analysis</h4>
          {% if error %}
          <div class="alert alert-danger py-2">{{ error }}</div>
          {% endif %}
          <form method="post" action="/do-login">
            <div class="mb-3">
              <label class="form-label">Usuario</label>
              <input type="text" name="username" class="form-control" autofocus required>
            </div>
            <div class="mb-3">
              <label class="form-label">Contraseña</label>
              <input type="password" name="password" class="form-control" required>
            </div>
            <button type="submit" class="btn btn-primary w-100">Iniciar sesión</button>
          </form>
        </div>
      </div>
    </div>
  </div>
</body>
</html>"""

    _ERROR_MSGS = {
        "empty":    "Ingresá usuario y contraseña.",
        "invalid":  "Usuario o contraseña incorrectos.",
        "inactive": "Usuario inactivo. Contactá al administrador.",
    }

    @server.route("/login", methods=["GET"])
    def login_page():
        if current_user.is_authenticated:
            return redirect("/chart")
        error = _ERROR_MSGS.get(request.args.get("error", ""), "")
        return render_template_string(_LOGIN_TEMPLATE, error=error)

    @server.route("/do-login", methods=["POST"])
    def do_login():
        from app.database import get_session as _db
        from app.models import User
        username = request.form.get("username", "").strip()
        password = request.form.get("password", "")
        if not username or not password:
            return redirect("/login?error=empty")
        s = _db()
        user = s.query(User).filter(User.username == username).first()
        if user is None or not user.check_password(password):
            return redirect("/login?error=invalid")
        if not user.is_active:
            return redirect("/login?error=inactive")
        login_user(user, remember=False)
        return redirect("/chart")

    @server.route("/")
    def index():
        if not current_user.is_authenticated:
            error = _ERROR_MSGS.get(request.args.get("error", ""), "")
            return render_template_string(_LOGIN_TEMPLATE, error=error)
        return redirect("/chart")

    @server.before_request
    def require_login():
        for prefix in _DASH_INTERNAL_PREFIXES:
            if request.path.startswith(prefix):
                return None
        if request.path in _PUBLIC_PATHS:
            return None
        if not current_user.is_authenticated:
            return redirect("/login")
        return None

    # -----------------------------------------------------------------
    # 5. Ruta de logout y health-check
    # -----------------------------------------------------------------
    @server.route("/logout")
    def logout():
        logout_user()
        return redirect("/login")

    @server.route("/health")
    def health():
        from flask import jsonify
        return jsonify({"status": "ok", "authenticated": current_user.is_authenticated})

    # -----------------------------------------------------------------
    # 6. Teardown de sesión de BD
    # -----------------------------------------------------------------
    from app.database import teardown_session
    server.teardown_appcontext(teardown_session)

    # -----------------------------------------------------------------
    # 7. Registrar páginas (importar módulos)
    # -----------------------------------------------------------------
    _PAGES = [
        "app.pages.screener",
        "app.pages.market_map",
        "app.pages.chart",
        "app.pages.assets_list",
        "app.pages.assets_import",
        "app.pages.prices",
        "app.pages.admin_users",
        "app.pages.admin_countries",
        "app.pages.admin_currencies",
        "app.pages.admin_markets",
        "app.pages.admin_instrument_types",
        "app.pages.admin_sectors",
        "app.pages.admin_industries",
        "app.pages.admin_price_sources",
        "app.pages.admin_events",
        "app.pages.admin_events_import",
        "app.pages.admin_catalog_mapper",
        "app.pages.admin_regime_config",
        "app.pages.admin_drawdown_config",
        "app.pages.admin_volatility_config",
        "app.pages.admin_sr_config",
        "app.pages.admin_cleanup",
        "app.pages.admin_sql",
        "app.pages.price_viewer",
        "app.pages.rrg",
        "app.pages.price_scatter",
        "app.pages.admin_synthetic",
        "app.pages.admin_currency_conversion",
        "app.pages.evolution",
        "app.pages.pair_analysis",
        "app.pages.admin_scheduler",
        "app.pages.admin_signals",
        "app.pages.admin_strategies",
        "app.pages.screener_signals",
        "app.pages.signal_history",
        "app.pages.signal_heatmap",
    ]

    import importlib
    logger.info("Cargando %d módulos de páginas...", len(_PAGES))
    for _mod in _PAGES:
        try:
            importlib.import_module(_mod)
            logger.debug("  OK página: %s", _mod)
        except Exception:
            logger.exception("  FALLO al cargar página: %s", _mod)
            raise
    logger.info("Páginas cargadas OK")

    # -----------------------------------------------------------------
    # 8. Registrar callbacks
    # -----------------------------------------------------------------
    _CALLBACKS = [
        "app.callbacks.reference_callbacks",
        "app.callbacks.asset_callbacks",
        "app.callbacks.import_callbacks",
        "app.callbacks.price_callbacks",
        "app.callbacks.chart_callbacks",
        "app.callbacks.screener_callbacks",
        "app.callbacks.market_map_callbacks",
        "app.callbacks.price_viewer_callbacks",
        "app.callbacks.admin_events_callbacks",
        "app.callbacks.events_import_callbacks",
        "app.callbacks.catalog_mapper_callbacks",
        "app.callbacks.regime_config_callbacks",
        "app.callbacks.drawdown_config_callbacks",
        "app.callbacks.volatility_config_callbacks",
        "app.callbacks.admin_sr_config_callbacks",
        "app.callbacks.admin_cleanup_callbacks",
        "app.callbacks.rrg_callbacks",
        "app.callbacks.scatter_callbacks",
        "app.callbacks.admin_synthetic_callbacks",
        "app.callbacks.admin_currency_conversion_callbacks",
        "app.callbacks.evolution_callbacks",
        "app.callbacks.pair_analysis_callbacks",
        "app.callbacks.admin_scheduler_callbacks",
        "app.callbacks.admin_sql_callbacks",
        "app.callbacks.admin_signals_callbacks",
        "app.callbacks.admin_strategies_callbacks",
        "app.callbacks.screener_signals_callbacks",
        "app.callbacks.signal_history_callbacks",
        "app.callbacks.signal_heatmap_callbacks",
    ]

    logger.info("Cargando %d módulos de callbacks...", len(_CALLBACKS))
    for _mod in _CALLBACKS:
        try:
            importlib.import_module(_mod)
            logger.debug("  OK callback: %s", _mod)
        except Exception:
            logger.exception("  FALLO al cargar callback: %s", _mod)
            raise
    logger.info("Callbacks cargados OK")

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

    # Redirige "/" a "/chart"
    from dash import Input, Output, callback as _callback, no_update as _no_update

    @_callback(Output("url", "pathname"), Input("url", "pathname"))
    def _redirect_root(pathname):
        if pathname == "/":
            return "/chart"
        return _no_update

    # -----------------------------------------------------------------
    # 10. Datos de arranque
    # -----------------------------------------------------------------
    from app.services.startup_service import ensure_builtin_data
    try:
        ensure_builtin_data()
    except Exception as exc:
        logger.warning("No se pudo inicializar datos de arranque: %s", exc)

    # -----------------------------------------------------------------
    # 11. APScheduler
    # -----------------------------------------------------------------
    from app.services.scheduler_service import start_if_enabled
    start_if_enabled()

    logger.info("Aplicación inicializada correctamente")
    return server, dash_app
