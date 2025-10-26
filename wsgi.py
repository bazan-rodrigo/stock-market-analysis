# -*- coding: utf-8 -*-
"""
Punto de entrada WSGI para el despliegue con Apache + mod_wsgi.
Expone la aplicacion Flask del servidor Dash.
"""

from app import create_app

# Variable requerida por mod_wsgi
application = create_app().server