"""
Brochure público — /acerca.

Página de presentación del sitio: qué hace el sistema y para quién es.
Es la única página Dash accesible SIN login (está en _PUBLIC_PATHS de
app/__init__.py): es el destino del link "¿Qué es este sistema?" de la
pantalla de login y del item "Acerca de" de la navbar.

El contenido es 100% estático a propósito — sin callbacks ni consultas a
la base — así la página funciona aunque la BD esté caída, igual que el
login. Los links a pantallas de la app van con recarga completa
(external_link): la navegación client-side de Dash se saltearía el
before_request que exige login.
"""
import dash
import dash_bootstrap_components as dbc
from dash import html

_ANCHO = {"maxWidth": "1000px"}


def _pilar(icono: str, color: str, titulo: str, parrafo: str,
           bullets: list[str]) -> dbc.Col:
    """Bloque de una de las cuatro capacidades centrales."""
    return dbc.Col(
        dbc.Card(
            dbc.CardBody([
                html.Div([
                    html.I(className=f"fa-solid {icono} fa-xl text-{color} me-3"),
                    html.H4(titulo, className="d-inline align-middle mb-0"),
                ], className="mb-3"),
                html.P(parrafo, className="mb-2"),
                html.Ul([html.Li(b, className="mb-1") for b in bullets],
                        className="text-muted small mb-0"),
            ]),
            className="h-100",
        ),
        lg=6, className="mb-4",
    )


def _contexto(icono: str, titulo: str, texto: str) -> dbc.Col:
    """Item chico de la sección de datos de contexto."""
    return dbc.Col(
        html.Div([
            html.Div(html.I(className=f"fa-solid {icono} fa-lg text-info"),
                     className="me-3 pt-1"),
            html.Div([
                html.H6(titulo, className="mb-1"),
                html.P(texto, className="text-muted small mb-0"),
            ]),
        ], className="d-flex"),
        md=6, className="mb-4",
    )


_HERO = html.Div([
    html.H1("Stock Market Analysis", className="display-4 fw-bold text-center"),
    html.P(
        "Diseñá señales sobre indicadores, combinalas en estrategias y "
        "validalas con backtesting — sobre un ranking diario de todos "
        "tus activos.",
        className="lead text-center text-muted mx-auto mb-4",
        style={"maxWidth": "700px"},
    ),
    html.Div(
        dbc.Button("Iniciar sesión", href="/login", external_link=True,
                   color="primary", size="lg"),
        className="text-center",
    ),
], className="py-5")


_PILARES = dbc.Row([
    _pilar(
        "fa-bolt", "warning", "Diseñá tus propias señales",
        "Convertí cualquier indicador —técnico o fundamental— en una señal "
        "con tu propia fórmula. Las reglas las definís vos, no vienen "
        "enlatadas.",
        [
            "Fórmulas por umbral, por rango o por mapeo de valores discretos, "
            "sobre cualquier indicador del catálogo.",
            "Señales sobre el activo o sobre su contexto: el sector, la "
            "industria, el país o el mercado al que pertenece.",
            "Cada señal guarda su historia completa, recalculada día a día.",
        ]),
    _pilar(
        "fa-filter", "info", "Armá estrategias",
        "Combiná tus señales en una estrategia: un filtro decide qué activos "
        "son elegibles y un score los ordena.",
        [
            "Filtro de elegibilidad con árbol de condiciones AND/OR.",
            "Score ponderado de señales, con alcance de activo o de grupo.",
            "Resultado: un ranking diario de todo el universo de activos, "
            "listo en el screener.",
        ]),
    _pilar(
        "fa-flask", "danger", "Validá con backtesting",
        "Antes de confiar en una estrategia, medila contra la historia desde "
        "cuatro ángulos complementarios.",
        [
            "Análisis por cuantiles del score, con intervalos de confianza "
            "y spread entre extremos.",
            "Backtest por reglas de entrada/salida sobre las señales.",
            "Simulación de cartera con costos y curva de equity.",
            "Comparación entre corridas y walk-forward para detectar "
            "sobreajuste.",
        ]),
    _pilar(
        "fa-chart-line", "success", "Hacé seguimiento",
        "Lo que decidiste queda registrado y se puede seguir en el tiempo, "
        "señal por señal y cartera por cartera.",
        [
            "Screener con las señales y rankings del día.",
            "Historial de señales y evolución de cada estrategia.",
            "Carteras reales (con registro de operaciones) y teóricas, "
            "vinculables a una estrategia.",
        ]),
])


_CONTEXTO = dbc.Row([
    _contexto(
        "fa-database", "Precios y fundamentales",
        "Precios diarios y datos de balances y ratios, actualizados "
        "automáticamente todos los días desde Yahoo Finance por el "
        "scheduler interno."),
    _contexto(
        "fa-calendar-days", "Eventos de mercado",
        "Registro de eventos que contextualizan los movimientos, con "
        "carga manual o importación masiva."),
    _contexto(
        "fa-coins", "Sintéticos y divisas",
        "Activos calculados (ratios e índices propios) y conversión "
        "automática de moneda para comparar todo en una misma divisa."),
    _contexto(
        "fa-magnifying-glass-chart", "Herramientas de análisis",
        "Mapa de tendencia del mercado, rotación relativa, análisis de "
        "pares, correlaciones y comparador de retornos."),
    _contexto(
        "fa-sitemap", "Grupos",
        "Cada activo pertenece a un sector, industria, país, mercado y tipo "
        "de instrumento; el sistema agrega tendencia por grupo y permite "
        "señales sobre esos agregados."),
    _contexto(
        "fa-book", "Manual integrado",
        "Toda la aplicación está documentada en un manual navegable dentro "
        "del propio sitio, con buscador y ayuda contextual en cada pantalla."),
])


_CIERRE = dbc.Card(
    dbc.CardBody([
        html.H4("Pensado para trabajar en serio", className="mb-3"),
        html.P(
            "Indicadores, señales y rankings se calculan una vez por día "
            "sobre todo el universo de activos: cada pantalla responde al "
            "instante porque no computa nada al vuelo. Los administradores "
            "gestionan datos y configuración; los analistas diseñan sus "
            "señales y estrategias, y las validan.",
            className="text-muted"),
        html.Div(
            dbc.Button("Iniciar sesión", href="/login", external_link=True,
                       color="primary"),
            className="text-center mt-2"),
        html.P("Si todavía no tenés usuario, pedíselo al administrador "
               "del sitio.",
               className="text-muted small text-center mt-3 mb-0"),
    ]),
    className="mb-5",
)


layout = dbc.Container([
    _HERO,
    html.H3("El corazón del sistema", className="mb-4"),
    _PILARES,
    html.H3("El contexto sobre el que trabajás", className="mt-3 mb-4"),
    _CONTEXTO,
    _CIERRE,
], style=_ANCHO)


dash.register_page(__name__, path="/acerca",
                   title="Acerca de – Stock Market Analysis", layout=layout)
