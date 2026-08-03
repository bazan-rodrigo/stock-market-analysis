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


def _ia_item(cap: dict) -> dbc.Col:
    """Una capacidad de la IA: qué hace, con una pregunta de ejemplo."""
    return dbc.Col(
        html.Div([
            html.Div([
                html.I(className=f"fa-solid {cap['icono']} text-info me-2"),
                html.Span(cap["titulo"], className="fw-semibold"),
            ], className="mb-1"),
            html.P(cap["texto"], className="text-muted small mb-1"),
            html.P(f"«{cap['ejemplo']}»", className="text-info fst-italic small mb-0"),
        ]),
        md=6, lg=4, className="mb-4",
    )


_HERO = html.Div([
    html.H1("Stock Market Analysis", className="display-4 fw-bold text-center"),
    html.P(
        "Combiná señales sobre indicadores en estrategias propias, validalas "
        "con backtesting y consultá todo con tu propia IA — sobre un ranking "
        "diario de todos tus activos.",
        className="lead text-center text-muted mx-auto mb-4",
        style={"maxWidth": "700px"},
    ),
    html.Div(
        dbc.Button("Iniciar sesión", href="/login", external_link=True,
                   color="primary", size="lg"),
        className="text-center",
    ),
    html.Img(
        src="/assets/brochure_hero.svg",
        alt="Curva de equity con bandas de cuantiles (ilustrativa)",
        className="img-fluid d-block mx-auto mt-4",
        style={"maxWidth": "720px", "width": "100%"},
    ),
], className="py-5")


# ── Diagrama del pipeline ────────────────────────────────────────────────────
# Estilos en assets/custom.css (sección "Brochure público").

_FLUJO = [
    ("fa-database",     "Datos de mercado", "precios, fundamentales, eventos"),
    ("fa-gauge-high",   "Indicadores",      "técnicos y fundamentales"),
    ("fa-bolt",         "Señales",          "fórmulas sobre indicadores"),
    ("fa-filter",       "Estrategias",      "filtro + score ponderado"),
    ("fa-ranking-star", "Ranking diario",   "todo el universo, ordenado"),
    ("fa-flask",        "Backtest",         "validación contra la historia"),
]


def _diagrama_pipeline() -> html.Div:
    hijos: list = []
    for i, (icono, titulo, detalle) in enumerate(_FLUJO):
        if i:
            hijos.append(html.I(
                className="fa-solid fa-arrow-right-long brochure-arrow"))
        hijos.append(html.Div([
            html.I(className=f"fa-solid {icono} text-info"),
            html.Div(titulo, className="brochure-node-titulo"),
            html.Div(detalle, className="brochure-node-detalle"),
        ], className="brochure-node"))
    return html.Div([
        html.Div(hijos, className="brochure-flow"),
        html.P("Todo pre-calculado una vez por día: las pantallas leen "
               "resultados, no computan al vuelo.",
               className="text-muted small text-center mt-3 mb-0"),
    ], className="mb-5")


_PILARES = dbc.Row([
    _pilar(
        "fa-bolt", "warning", "Un catálogo de señales curado",
        "Una señal traduce un indicador —técnico o fundamental— a un puntaje "
        "comparable de −100 a +100. El catálogo lo mantiene el administrador, "
        "así que todo el equipo trabaja sobre las mismas definiciones y un "
        "ranking significa lo mismo para todos.",
        [
            "Fórmulas por umbral, por rango o por mapeo de valores discretos, "
            "sobre cualquier indicador del catálogo.",
            "Cada señal muestra con qué criterio puntúa: su fórmula y sus "
            "cortes están a la vista antes de usarla, no es una caja negra.",
            "Cada señal guarda su historia completa, recalculada día a día.",
            "¿Falta una? Se la proponés al administrador — y tu IA te ayuda a "
            "fundamentarla con la distribución real del indicador.",
        ]),
    _pilar(
        "fa-filter", "info", "Armá tus propias estrategias",
        "Acá sí definís vos: combiná las señales del catálogo en una "
        "estrategia propia, donde un filtro decide qué activos son elegibles "
        "y un score los ordena.",
        [
            "Filtro de elegibilidad con árbol de condiciones AND/OR, sobre "
            "precios, indicadores y atributos del activo.",
            "Score ponderado de señales: elegís cuáles entran y con qué peso.",
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


# ── Conexión IA ──────────────────────────────────────────────────────────────
# La clave `familia` de cada item es la misma que declaran las herramientas de
# `app/ai/registry.py`, y `tests/test_contract_coverage.py` exige que las dos
# listas coincidan. Es el mismo puente que ata la sección del manual, por el
# mismo motivo y con una vuelta más: el manual se lo cuenta a quien YA entró;
# esta página es lo único que se lo cuenta a quien todavía no tiene usuario.
# Una capacidad que nadie sabe que existe no vende nada.
#
# Se declara como literal plano —sin llamadas ni constantes— para que el test
# la pueda leer del AST: importar esta página dispara `register_page` y
# necesitaría media aplicación levantada.
_IA_CAPACIDADES = [
    {
        "familia": "catalogo",
        "icono": "fa-book-open",
        "titulo": "Conoce tu catálogo",
        "texto": "Qué indicadores, señales y estrategias hay en tu "
                 "instalación, y con qué criterio puntúa cada señal — no solo "
                 "cómo se llama.",
        "ejemplo": "¿Qué señales tengo y qué mide cada una?",
    },
    {
        "familia": "indicadores",
        "icono": "fa-chart-simple",
        "titulo": "Discute tus cortes con números",
        "texto": "Cómo se reparte un indicador entre todos los activos: "
                 "percentiles, mínimo, máximo y cobertura. Le proponés una "
                 "escala y te dice cuántos activos quedarían saturados.",
        "ejemplo": "Si el rango va de −3 a 3, ¿cuántos activos saturan?",
    },
    {
        "familia": "ranking",
        "icono": "fa-ranking-star",
        "titulo": "Lee el ranking del día",
        "texto": "El ranking de una estrategia en cualquier fecha y la "
                 "evolución del puntaje de un activo, para ver quién viene "
                 "mejorando y quién se deteriora.",
        "ejemplo": "¿Qué cambió en el top 10 desde el mes pasado?",
    },
    {
        "familia": "backtest",
        "icono": "fa-flask",
        "titulo": "Prueba variantes sin crear nada",
        "texto": "Backtests que no quedan guardados, y una variante —otros "
                 "pesos, otros componentes— comparada contra la estrategia "
                 "original sobre la misma elegibilidad.",
        "ejemplo": "¿Y si le subo el peso al momentum?",
    },
    {
        "familia": "carteras",
        "icono": "fa-briefcase",
        "titulo": "Simula carteras hipotéticas",
        "texto": "Retorno, CAGR, volatilidad, Sharpe, Sortino y máxima caída "
                 "de tus carteras, y de combinaciones que todavía no existen.",
        "ejemplo": "¿Cómo habría andado esta lista en partes iguales?",
    },
    {
        "familia": "manual",
        "icono": "fa-circle-question",
        "titulo": "Explica este sistema",
        "texto": "Consulta el manual de la instalación antes de responder, "
                 "así te explica cómo calcula esta plataforma en vez de "
                 "improvisar teoría general.",
        "ejemplo": "¿Cómo se arma el puntaje de una estrategia?",
    },
]


_IA = html.Div([
    html.P(
        "Conectá Claude, ChatGPT o el asistente que ya uses y preguntale en "
        "lenguaje natural sobre tus propios datos. No es un chat genérico de "
        "finanzas: la IA le pide los números a esta plataforma —los mismos "
        "que ves en pantalla— y trabaja con ellos.",
        className="text-muted mx-auto mb-4", style={"maxWidth": "760px"},
    ),
    dbc.Row([_ia_item(c) for c in _IA_CAPACIDADES]),
    dbc.Card(
        dbc.CardBody([
            html.H5("Con tus reglas", className="mb-3"),
            html.Ul([
                html.Li([
                    html.Strong("Tu cuenta es tuya. "),
                    "La plataforma no ve ni guarda tu cuenta de IA, no te pide "
                    "la clave y no paga tus consultas: te conectás con un "
                    "token propio, que podés revocar al instante.",
                ], className="mb-2"),
                html.Li([
                    html.Strong("Ve lo que verías vos. "),
                    "El token respeta tus permisos: lo que es privado de otro "
                    "usuario, para la IA tampoco existe.",
                ], className="mb-2"),
                html.Li([
                    html.Strong("Solo lectura. "),
                    "No crea, no edita y no borra nada; lo que calcula no "
                    "queda guardado.",
                ], className="mb-2"),
                html.Li([
                    html.Strong("Sin promedios engañosos. "),
                    "Todo lo que calcula lo muestra también por tramos de "
                    "tiempo: una estrategia que anduvo bárbaro en un solo "
                    "tramo no es una buena estrategia. Y si te propone una "
                    "señal, te la describe para que la lleves vos — cargarla "
                    "es siempre decisión de una persona.",
                ], className="mb-0"),
            ], className="small mb-0"),
            html.P(
                "El acceso se activa con un token que generás vos desde la "
                "pantalla de Conexión IA; la dirección del conector te la da "
                "el administrador del sitio.",
                className="text-muted small mt-3 mb-0"),
        ]),
        className="mb-5",
    ),
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
        "de instrumento: podés filtrar y comparar por esos atributos, y el "
        "mapa de tendencia agrega cómo viene cada grupo."),
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
            "gestionan los datos, la configuración y el catálogo de señales; "
            "los analistas arman sus estrategias sobre ese catálogo, las "
            "validan y las siguen.",
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
    _diagrama_pipeline(),
    html.H3("El corazón del sistema", className="mb-4"),
    _PILARES,
    html.H3("Traé tu propia IA", className="mt-3 mb-3"),
    _IA,
    html.H3("El contexto sobre el que trabajás", className="mt-3 mb-4"),
    _CONTEXTO,
    _CIERRE,
], style=_ANCHO)


dash.register_page(__name__, path="/acerca",
                   title="Acerca de – Stock Market Analysis", layout=layout)
