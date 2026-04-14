import dash
from dash import dcc

dash.register_page(__name__, path="/", title="Inicio")


def layout(**kwargs):
    # Redirige al screener como página principal
    return dcc.Location(id="home-redirect", href="/screener", refresh=True)
