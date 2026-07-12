"""Constantes de UI compartidas entre páginas del módulo de señales y estrategias."""

# ── Colores semánticos ────────────────────────────────────────────────────────
COLOR_POSITIVE = "#4caf50"   # verde   — score positivo / bullish  (Material Green 500)
COLOR_NEGATIVE = "#ef5350"   # rojo    — score negativo / bearish  (Material Red 400)
COLOR_NEUTRAL  = "#94a3b8"   # gris    — sin tendencia clara
COLOR_WARNING  = "#facc15"   # amarillo — advertencia
COLOR_INFO     = "#38bdf8"   # azul    — discrete_map, info
COLOR_RANGE    = "#fb923c"   # naranja — fórmula range
COLOR_PURPLE   = "#c084fc"   # violeta — fórmula composite

# ── Fondos y bordes ───────────────────────────────────────────────────────────
BG_CARD      = "#1f2937"    # fondo de cards de filtros / contenedores principales
BG_DEEP      = "#111827"    # fondo de code blocks y gráficos
BG_CHART     = "#111827"    # alias semántico de BG_DEEP para fondos de gráficos Plotly
BG_HELP_CARD = "#1a2332"    # fondo de help cards contextuales
BORDER_CARD  = "#374151"    # borde de cards
BORDER_ROW   = "#1f2937"    # separador entre filas de tabla

# ── Tema Plotly oscuro (compartido entre todos los gráficos Plotly) ───────────
PLOTLY_DARK = dict(
    paper_bgcolor=BG_CHART,
    plot_bgcolor=BG_CHART,
    font=dict(color="#dee2e6"),
)
PLOTLY_AXIS = dict(gridcolor="#2d3038", linecolor="#495057", zerolinecolor="#2d3038")

# ── Paleta de colores para gráficos de líneas (multi-serie) ──────────────────
CHART_PALETTE = [
    "#60a5fa", "#34d399", "#fbbf24", "#f87171", "#a78bfa",
    "#fb923c", "#38bdf8", "#4ade80", "#e879f9", "#facc15",
    "#818cf8", "#2dd4bf", "#f97316", "#ec4899", "#84cc16",
]

# ── Font sizes ────────────────────────────────────────────────────────────────
FS_LABEL = "0.82rem"
FS_CODE  = "0.74rem"

# ── Estilos de tabla HTML (html.Table / html.Th / html.Td) ───────────────────
TH = {
    "fontSize": "0.76rem",
    "color": "#9ca3af",
    "fontWeight": "normal",
    "padding": "5px 8px",
    "borderBottom": f"1px solid {BORDER_CARD}",
}
# Variante para tablas con muchas columnas donde el texto del header no debe romper línea
TH_NOWRAP = {**TH, "whiteSpace": "nowrap"}

TD = {
    "fontSize": "0.80rem",
    "padding": "5px 8px",
    "borderBottom": f"1px solid {BORDER_ROW}",
}

# ── Estilos de componentes reutilizables ──────────────────────────────────────
CARD_STYLE = {"backgroundColor": BG_CARD, "border": f"1px solid {BORDER_CARD}"}

STATUS_STYLE = {
    "fontSize": FS_LABEL,
    "color": COLOR_NEUTRAL,
    "minHeight": "24px",
    "padding": "2px 0",
}

# ── Opciones de dropdown compartidas ─────────────────────────────────────────
GROUP_TYPE_OPTS = [
    {"label": "Sector",    "value": "sector"},
    {"label": "Mercado",   "value": "market"},
    {"label": "Industria", "value": "industry"},
]

# ── Definición de fórmulas de señal y sus help cards ─────────────────────────
FORMULA_HELP = {
    "discrete_map": {
        "color": COLOR_INFO,
        "title": "Mapa discreto",
        "desc": (
            "Para indicadores con categorías (tendencia, volatilidad). Asignás "
            "a mano el score de cada categoría posible del indicador: p.ej. "
            "tendencia alcista fuerte → 100, lateral → 0, bajista → −60. "
            "Si el activo cae en una categoría sin score asignado, la señal "
            "no puntúa ese día."
        ),
        "example": '{"map": {"bullish_strong": 100, "bullish": 60, "lateral": 0, "bearish": -60}}',
    },
    "threshold": {
        "color": COLOR_POSITIVE,
        "title": "Umbrales (escalones)",
        "desc": (
            "Para indicadores numéricos, cuando querés puntajes por tramos en "
            "vez de una escala continua. Se evalúa de arriba hacia abajo: el "
            "primer umbral que el valor supera define el score. P.ej. con "
            "drawdown: mayor a −5% → 100; mayor a −15% → 50; mayor a −30% → 0; "
            "cualquier valor peor cae en «en otro caso» → −50. Todo valor "
            "posible recibe exactamente un score."
        ),
        "example": '{"thresholds": [[-5, 100], [-15, 50], [-30, 0], [null, -50]]}',
    },
    "range": {
        "color": COLOR_RANGE,
        "title": "Rango lineal",
        "desc": (
            "Para indicadores numéricos, cuando querés una escala continua: el "
            "score crece proporcionalmente con el valor. Definís dos puntos: "
            "el valor que vale −100 (Min) y el que vale +100 (Max); todo lo "
            "intermedio se interpola en línea recta (el punto medio da 0). "
            "P.ej. Min=−3, Max=3 para una distancia en desvíos estándar. Con "
            "«recortar» activado, valores fuera del rango quedan en ±100."
        ),
        "example": '{"min": -3.0, "max": 3.0, "clamp": true}',
    },
    "composite": {
        "color": COLOR_PURPLE,
        "title": "Compuesta",
        "desc": (
            "No lee ningún indicador: combina los scores de otras señales ya "
            "existentes en un promedio ponderado. P.ej. tendencia diaria "
            "(peso 2) + tendencia semanal (peso 1) → una señal de tendencia "
            "global que pesa más lo diario. Si a un activo le falta alguna "
            "señal componente ese día, se promedia con las restantes."
        ),
        "example": (
            '{"components": [\n'
            '  {"signal_key": "tendencia_d", "weight": 1},\n'
            '  {"signal_key": "tendencia_w", "weight": 1}\n'
            ']}'
        ),
    },
}


def formula_help_card(ft: str | None, show_example: bool = True):
    """Card de ayuda contextual para el tipo de fórmula seleccionado en
    admin_signals. show_example=False oculta el JSON de ejemplo (el editor
    estructurado lo hace innecesario; solo aporta en modo avanzado)."""
    from dash import html
    import dash_bootstrap_components as dbc

    if not ft or ft not in FORMULA_HELP:
        return html.Div()
    h = FORMULA_HELP[ft]
    c = h["color"]
    body = [
        html.Strong(h["title"], style={"color": c, "fontSize": "0.84rem"}),
        html.P(h["desc"], style={"fontSize": "0.77rem", "color": "#d1d5db", "margin": "4px 0"}),
    ]
    if show_example:
        body.append(html.Code(
            h["example"],
            style={
                "display": "block", "whiteSpace": "pre", "fontSize": FS_CODE,
                "backgroundColor": BG_DEEP, "padding": "6px 10px",
                "borderRadius": "4px", "color": c, "fontFamily": "monospace",
            },
        ))
    return dbc.Card(dbc.CardBody(body),
                    style={"backgroundColor": BG_HELP_CARD, "border": f"1px solid {c}33",
                           "borderLeft": f"3px solid {c}"}, className="mb-2")
