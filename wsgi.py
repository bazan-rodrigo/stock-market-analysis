"""Entry point para Apache + mod_wsgi en producción Linux."""
from app import create_app

_app, dash_app = create_app()

# mod_wsgi busca una variable llamada 'application'
application = dash_app.server
