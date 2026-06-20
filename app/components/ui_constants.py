"""Constantes de UI compartidas entre páginas del módulo de señales y estrategias."""

# ── Colores semánticos ────────────────────────────────────────────────────────
COLOR_POSITIVE = "#4ade80"   # verde   — score positivo / bullish
COLOR_NEGATIVE = "#f87171"   # rojo    — score negativo / bearish
COLOR_NEUTRAL  = "#94a3b8"   # gris    — sin tendencia clara
COLOR_INFO     = "#38bdf8"   # azul    — discrete_map, info
COLOR_RANGE    = "#fb923c"   # naranja — fórmula range
COLOR_PURPLE   = "#c084fc"   # violeta — fórmula composite

# ── Fondos y bordes ───────────────────────────────────────────────────────────
BG_CARD      = "#1f2937"    # fondo de cards de filtros / contenedores principales
BG_DEEP      = "#111827"    # fondo de code blocks
BG_HELP_CARD = "#1a2332"    # fondo de help cards contextuales
BORDER_CARD  = "#374151"    # borde de cards
BORDER_ROW   = "#1f2937"    # separador entre filas de tabla

# ── Font sizes ────────────────────────────────────────────────────────────────
FS_LABEL = "0.82rem"
FS_INPUT = "0.85rem"
FS_CODE  = "0.74rem"
FS_SMALL = "0.78rem"

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
        "desc": "Convierte un valor categórico (string) a un score usando un diccionario.",
        "example": '{"map": {"bullish_strong": 100, "bullish": 60, "lateral": 0, "bearish": -60}}',
    },
    "threshold": {
        "color": COLOR_POSITIVE,
        "title": "Umbrales",
        "desc": (
            "Recorre umbrales en orden. Si el valor > límite retorna ese score. "
            "El último par [null, score] es el valor por defecto."
        ),
        "example": '{"thresholds": [[-5, 100], [-15, 50], [-30, 0], [null, -50]]}',
    },
    "range": {
        "color": COLOR_RANGE,
        "title": "Rango lineal",
        "desc": "Mapea un valor numérico en [min, max] a [-100, 100] de forma lineal.",
        "example": '{"min": -3.0, "max": 3.0, "clamp": true}',
    },
    "composite": {
        "color": COLOR_PURPLE,
        "title": "Compuesta",
        "desc": "Promedio ponderado de scores de otras señales. Puede anidar hasta 3 niveles.",
        "example": (
            '{"components": [\n'
            '  {"signal_key": "tendencia_d", "weight": 1},\n'
            '  {"signal_key": "tendencia_w", "weight": 1}\n'
            ']}'
        ),
    },
}


def formula_help_card(ft: str | None):
    """Card de ayuda contextual para el tipo de fórmula seleccionado en admin_signals."""
    from dash import html
    import dash_bootstrap_components as dbc

    if not ft or ft not in FORMULA_HELP:
        return html.Div()
    h = FORMULA_HELP[ft]
    c = h["color"]
    return dbc.Card(dbc.CardBody([
        html.Strong(h["title"], style={"color": c, "fontSize": "0.84rem"}),
        html.P(h["desc"], style={"fontSize": "0.77rem", "color": "#d1d5db", "margin": "4px 0"}),
        html.Code(
            h["example"],
            style={
                "display": "block", "whiteSpace": "pre", "fontSize": FS_CODE,
                "backgroundColor": BG_DEEP, "padding": "6px 10px",
                "borderRadius": "4px", "color": c, "fontFamily": "monospace",
            },
        ),
    ]), style={"backgroundColor": BG_HELP_CARD, "border": f"1px solid {c}33",
               "borderLeft": f"3px solid {c}"}, className="mb-2")
