import dash
import dash_bootstrap_components as dbc
from dash import dash_table, html

from app.components.table_styles import CELL, DATA, FILTER, HEADER

_CONVENTIONS = [
    ("_d",       "timeframe diario"),
    ("_w",       "timeframe semanal"),
    ("_m",       "timeframe mensual"),
    ("dd_",      "drawdown"),
    ("vs_",      "distancia % al precio"),
    ("dist_",    "distancia en σ (desviaciones estándar)"),
    ("var_",     "variación porcentual"),
    ("atr_pct_", "percentil del ATR"),
    ("pivot_",   "nivel de soporte / resistencia pivot"),
    ("vol_",     "volatilidad"),
]

_INDICATORS = [
    # Régimen
    {"codigo": "regime_d", "nombre": "Régimen diario",        "categoria": "Régimen",               "escala": "Categórico",    "descripcion": "Clasificación de tendencia en timeframe diario basada en la MA más respetada"},
    {"codigo": "regime_w", "nombre": "Régimen semanal",       "categoria": "Régimen",               "escala": "Categórico",    "descripcion": "Clasificación de tendencia en timeframe semanal"},
    {"codigo": "regime_m", "nombre": "Régimen mensual",       "categoria": "Régimen",               "escala": "Categórico",    "descripcion": "Clasificación de tendencia en timeframe mensual"},
    # Volatilidad — régimen
    {"codigo": "vol_d",    "nombre": "Volatilidad diaria",    "categoria": "Volatilidad",           "escala": "Categórico",    "descripcion": "Régimen de volatilidad ATR en timeframe diario (ej: Alta | Larga)"},
    {"codigo": "vol_w",    "nombre": "Volatilidad semanal",   "categoria": "Volatilidad",           "escala": "Categórico",    "descripcion": "Régimen de volatilidad ATR en timeframe semanal"},
    {"codigo": "vol_m",    "nombre": "Volatilidad mensual",   "categoria": "Volatilidad",           "escala": "Categórico",    "descripcion": "Régimen de volatilidad ATR en timeframe mensual"},
    # Volatilidad — percentil ATR
    {"codigo": "atr_pct_d", "nombre": "Percentil ATR diario",  "categoria": "Volatilidad",          "escala": "0 – 100",       "descripcion": "Percentil del ATR actual respecto a la historia del activo (diario)"},
    {"codigo": "atr_pct_w", "nombre": "Percentil ATR semanal", "categoria": "Volatilidad",          "escala": "0 – 100",       "descripcion": "Percentil del ATR actual respecto a la historia del activo (semanal)"},
    {"codigo": "atr_pct_m", "nombre": "Percentil ATR mensual", "categoria": "Volatilidad",          "escala": "0 – 100",       "descripcion": "Percentil del ATR actual respecto a la historia del activo (mensual)"},
    # RSI
    {"codigo": "rsi",   "nombre": "RSI diario",   "categoria": "Momentum",                          "escala": "0 – 100",       "descripcion": "Relative Strength Index 14 períodos en timeframe diario"},
    {"codigo": "rsi_w", "nombre": "RSI semanal",  "categoria": "Momentum",                          "escala": "0 – 100",       "descripcion": "RSI 14 períodos en timeframe semanal"},
    {"codigo": "rsi_m", "nombre": "RSI mensual",  "categoria": "Momentum",                          "escala": "0 – 100",       "descripcion": "RSI 14 períodos en timeframe mensual"},
    # Distancia a SMA fija
    {"codigo": "vs_sma20",  "nombre": "Dist. % a SMA 20",  "categoria": "Tendencia SMA",            "escala": "%",             "descripcion": "Distancia porcentual del precio al promedio móvil simple de 20 ruedas"},
    {"codigo": "vs_sma50",  "nombre": "Dist. % a SMA 50",  "categoria": "Tendencia SMA",            "escala": "%",             "descripcion": "Distancia porcentual del precio al promedio móvil simple de 50 ruedas"},
    {"codigo": "vs_sma200", "nombre": "Dist. % a SMA 200", "categoria": "Tendencia SMA",            "escala": "%",             "descripcion": "Distancia porcentual del precio al promedio móvil simple de 200 ruedas"},
    # Distancia a SMA óptima
    {"codigo": "dist_sma_d", "nombre": "Dist. σ SMA óptima diaria",  "categoria": "Tendencia SMA",  "escala": "σ",             "descripcion": "Distancia en desviaciones estándar desde la MA más respetada en timeframe diario"},
    {"codigo": "dist_sma_w", "nombre": "Dist. σ SMA óptima semanal", "categoria": "Tendencia SMA",  "escala": "σ",             "descripcion": "Distancia en desviaciones estándar desde la MA más respetada en timeframe semanal"},
    {"codigo": "dist_sma_m", "nombre": "Dist. σ SMA óptima mensual", "categoria": "Tendencia SMA",  "escala": "σ",             "descripcion": "Distancia en desviaciones estándar desde la MA más respetada en timeframe mensual"},
    # Drawdown
    {"codigo": "dd_current", "nombre": "Drawdown actual",   "categoria": "Drawdown",                "escala": "% (negativo)",  "descripcion": "Caída porcentual desde el máximo reciente hasta el precio actual"},
    {"codigo": "dd_max1",    "nombre": "Drawdown máximo 1", "categoria": "Drawdown",                "escala": "% (negativo)",  "descripcion": "Mayor drawdown registrado en los eventos significativos del historial"},
    {"codigo": "dd_max2",    "nombre": "Drawdown máximo 2", "categoria": "Drawdown",                "escala": "% (negativo)",  "descripcion": "Segundo mayor drawdown registrado"},
    {"codigo": "dd_max3",    "nombre": "Drawdown máximo 3", "categoria": "Drawdown",                "escala": "% (negativo)",  "descripcion": "Tercer mayor drawdown registrado"},
    # Variaciones
    {"codigo": "var_daily",   "nombre": "Variación diaria",    "categoria": "Variación",            "escala": "%",             "descripcion": "Retorno del último día hábil"},
    {"codigo": "var_month",   "nombre": "Variación mensual",   "categoria": "Variación",            "escala": "%",             "descripcion": "Retorno en el último mes calendario"},
    {"codigo": "var_quarter", "nombre": "Variación trimestral","categoria": "Variación",            "escala": "%",             "descripcion": "Retorno en el último trimestre"},
    {"codigo": "var_year",    "nombre": "Variación anual",     "categoria": "Variación",            "escala": "%",             "descripcion": "Retorno en los últimos 12 meses"},
    {"codigo": "var_52w",     "nombre": "Variación 52 semanas","categoria": "Variación",            "escala": "%",             "descripcion": "Retorno en las últimas 52 semanas calendario"},
    # Soporte / Resistencia
    {"codigo": "pivot_resist_pct",  "nombre": "Dist. % a resistencia", "categoria": "Soporte / Resistencia", "escala": "%", "descripcion": "Distancia porcentual al nivel de resistencia pivot más cercano por encima del precio"},
    {"codigo": "pivot_support_pct", "nombre": "Dist. % a soporte",     "categoria": "Soporte / Resistencia", "escala": "%", "descripcion": "Distancia porcentual al nivel de soporte pivot más cercano por debajo del precio"},
]


def layout(**kwargs):
    from flask_login import current_user
    if not current_user.is_authenticated or not current_user.is_admin:
        return html.Div("Acceso denegado", className="text-danger mt-4")

    return html.Div([
        html.H3("Indicadores del Sistema", className="mb-1"),
        html.P(
            "Indicadores técnicos disponibles como input para las señales. "
            "Se calculan automáticamente a partir del historial de precios "
            "y se almacenan en screener_snapshot.",
            className="text-muted mb-3",
            style={"fontSize": "0.83rem"},
        ),
        dbc.Card(dbc.CardBody([
            html.Div([
                html.Span("Convenciones de código: ", style={"fontSize": "0.78rem",
                          "color": "#9ca3af", "fontWeight": "600", "marginRight": "12px"}),
                *[
                    html.Span([
                        html.Code(prefix, style={"fontSize": "0.76rem", "color": "#94a3b8",
                                                  "backgroundColor": "#111827",
                                                  "padding": "1px 5px", "borderRadius": "3px"}),
                        html.Span(f" = {meaning}", style={"fontSize": "0.76rem",
                                                           "color": "#6b7280"}),
                    ], style={"marginRight": "16px", "whiteSpace": "nowrap"})
                    for prefix, meaning in _CONVENTIONS
                ],
            ], style={"display": "flex", "flexWrap": "wrap", "gap": "4px 0",
                      "alignItems": "center"}),
        ]), style={"backgroundColor": "#1f2937", "border": "1px solid #374151"},
           className="mb-4"),
        dash_table.DataTable(
            columns=[
                {"name": "Código",      "id": "codigo"},
                {"name": "Nombre",      "id": "nombre"},
                {"name": "Categoría",   "id": "categoria"},
                {"name": "Escala",      "id": "escala"},
                {"name": "Descripción", "id": "descripcion"},
            ],
            data=_INDICATORS,
            style_table={"overflowX": "auto"},
            style_header=HEADER,
            style_data=DATA,
            style_cell={**CELL, "whiteSpace": "normal", "height": "auto"},
            style_filter=FILTER,
            style_cell_conditional=[
                {"if": {"column_id": "codigo"},      "fontFamily": "monospace",
                 "color": "#94a3b8", "width": "160px", "minWidth": "160px"},
                {"if": {"column_id": "categoria"},   "width": "160px", "minWidth": "160px"},
                {"if": {"column_id": "escala"},      "width": "110px", "minWidth": "110px"},
                {"if": {"column_id": "descripcion"}, "minWidth": "300px"},
            ],
            page_size=30,
            filter_action="native",
            sort_action="native",
        ),
    ])


dash.register_page(__name__, path="/admin/indicators", title="Indicadores del sistema", layout=layout)
