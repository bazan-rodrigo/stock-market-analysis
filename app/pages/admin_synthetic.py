import dash
import dash_bootstrap_components as dbc
from dash import dcc, html

_FORMULA_TYPES = [
    {"label": "Ratio (cociente ponderado)",     "value": "ratio"},
    {"label": "Promedio ponderado de precios",  "value": "weighted_avg"},
    {"label": "Suma ponderada de precios",      "value": "weighted_sum"},
    {"label": "Índice base desde fecha",        "value": "index"},
]

_HELP = {
    "ratio": {
        "color": "#38bdf8",
        "title": "Ratio — cociente ponderado",
        "formula": "Precio = Σ(wᵢ × Pᵢ  |  Numerador) / Σ(wᵢ × Pᵢ  |  Denominador)",
        "desc": (
            "Divide la suma ponderada de los activos numeradores por la de los denominadores. "
            "El caso más simple (un numerador, un denominador, peso 1) calcula el tipo de cambio "
            "implícito entre dos versiones del mismo activo: por ejemplo, "
            "CCL = GGAL.BA / GGAL (precio en ARS dividido precio en USD)."
        ),
        "params": [
            ("Rol",  "Cada componente debe tener rol Numerador o Denominador."),
            ("Peso", "Factor multiplicador de cada precio antes de sumar. Por defecto 1."),
        ],
    },
    "weighted_avg": {
        "color": "#4ade80",
        "title": "Promedio ponderado de precios",
        "formula": "Precio = Σ(wᵢ × Pᵢ) / Σ(wᵢ)",
        "desc": (
            "Promedio ponderado de los precios de los activos seleccionados. "
            "Si todos los pesos son iguales se convierte en una media aritmética simple. "
            "Útil para construir un índice sectorial o una canasta con exposición controlada."
        ),
        "params": [
            ("Peso", "Participación relativa de cada activo. No es necesario que sumen 100; "
                     "la fórmula normaliza automáticamente."),
        ],
    },
    "weighted_sum": {
        "color": "#fb923c",
        "title": "Suma ponderada de precios",
        "formula": "Precio = Σ(wᵢ × Pᵢ)",
        "desc": (
            "Suma directa de los precios multiplicados por su peso, sin normalizar. "
            "Equivale a un índice price-weighted (como el Dow Jones). "
            "También sirve para modelar carteras donde el peso es la cantidad de acciones."
        ),
        "params": [
            ("Peso", "Cantidad o factor por el que se multiplica cada precio antes de sumar."),
        ],
    },
    "index": {
        "color": "#c084fc",
        "title": "Índice base desde fecha",
        "formula": "Precio = Valor_base × Σ(wᵢ × Pᵢ/P₀ᵢ) / Σ(wᵢ)",
        "desc": (
            "Mide la evolución relativa de una canasta de activos respecto a una fecha de partida. "
            "En la fecha base el índice vale exactamente Valor_base (por defecto 100). "
            "Cada activo contribuye según cuánto creció o cayó desde esa fecha. "
            "Útil para comparar el desempeño de un grupo de activos en una escala común."
        ),
        "params": [
            ("Valor base", "Valor del índice en la fecha de partida. Por defecto 100."),
            ("Fecha base", "Fecha desde la cual se mide la evolución. "
                           "Si el activo no cotizó ese día exacto se usa el precio anterior más cercano."),
            ("Peso",       "Importancia relativa de cada activo en el índice. "
                           "La fórmula normaliza automáticamente."),
        ],
    },
}


def _help_card(ft: str | None):
    if not ft or ft not in _HELP:
        return html.Div()
    h = _HELP[ft]
    c = h["color"]
    _li_style = {"fontSize": "0.76rem", "color": "#d1d5db", "marginBottom": "3px"}
    return dbc.Card(dbc.CardBody([
        html.Div([
            html.Strong(h["title"], style={"color": c, "fontSize": "0.85rem"}),
            html.Code(h["formula"],
                      style={"display": "block", "fontSize": "0.78rem",
                             "backgroundColor": "#111827", "padding": "4px 8px",
                             "borderRadius": "4px", "margin": "6px 0",
                             "color": c, "fontFamily": "monospace"}),
            html.P(h["desc"], style={"fontSize": "0.78rem", "color": "#d1d5db", "margin": "0 0 6px"}),
            html.Ul([
                html.Li([html.Strong(p, style={"color": "#e5e7eb"}), f": {d}"],
                        style=_li_style)
                for p, d in h["params"]
            ], style={"paddingLeft": "16px", "margin": 0}),
        ]),
    ]), style={"backgroundColor": "#1a2332", "border": f"1px solid {c}33",
               "borderLeft": f"3px solid {c}"}, className="mb-3")


_th = {"fontSize": "0.76rem", "color": "#9ca3af", "fontWeight": "normal",
       "padding": "5px 8px", "borderBottom": "1px solid #374151"}
_td_s = {"fontSize": "0.80rem", "padding": "5px 8px", "borderBottom": "1px solid #1f2937"}


def layout(**kwargs):
    from flask_login import current_user
    if not current_user.is_authenticated or not current_user.is_admin:
        return html.Div()

    modal = dbc.Modal([
        dbc.ModalHeader(dbc.ModalTitle(id="syn-modal-title")),
        dbc.ModalBody([
            # Tipo de fórmula
            dbc.Row([
                dbc.Col([
                    dbc.Label("Tipo de fórmula", style={"fontSize": "0.82rem", "fontWeight": "bold"}),
                    dcc.Dropdown(
                        id="syn-formula-type",
                        options=_FORMULA_TYPES,
                        placeholder="Seleccionar tipo...",
                        style={"fontSize": "0.85rem"},
                        clearable=False,
                    ),
                ]),
            ], className="mb-2"),

            # Card de ayuda (cambia con el tipo)
            html.Div(id="syn-formula-help"),

            # Activo destino
            dbc.Row([
                dbc.Col([
                    dbc.Label("Activo destino (fuente Calculado)", style={"fontSize": "0.82rem"}),
                    dcc.Dropdown(id="syn-f-asset", placeholder="Seleccionar...",
                                 style={"fontSize": "0.85rem"}),
                ]),
            ], className="mb-3"),

            # Parámetros de índice (solo visible para 'index')
            html.Div([
                dbc.Row([
                    dbc.Col([
                        dbc.Label("Valor base", style={"fontSize": "0.82rem"}),
                        dbc.Input(id="syn-base-value", type="number", value=100,
                                  min=0.001, step=1, style={"fontSize": "0.85rem"}),
                    ], md=4),
                    dbc.Col([
                        dbc.Label("Fecha base", style={"fontSize": "0.82rem"}),
                        dcc.DatePickerSingle(
                            id="syn-base-date",
                            display_format="YYYY-MM-DD",
                            style={"fontSize": "0.85rem"},
                        ),
                    ], md=8),
                ], className="mb-3"),
            ], id="syn-index-params", style={"display": "none"}),

            # Componentes
            dbc.Label("Componentes", style={"fontSize": "0.82rem", "fontWeight": "bold"}),
            html.Div(id="syn-comp-header", className="mb-1"),
            html.Div(id="syn-comp-rows"),
            dbc.Button("+ Agregar componente", id="syn-btn-add-comp",
                       color="link", size="sm",
                       style={"fontSize": "0.80rem", "paddingLeft": 0}),

            # Preview de fórmula
            html.Div(id="syn-formula-preview",
                     className="mt-2 p-2",
                     style={"backgroundColor": "#111827", "borderRadius": "4px",
                            "fontSize": "0.78rem", "fontFamily": "monospace",
                            "color": "#94a3b8", "minHeight": "24px"}),

            dbc.Alert(id="syn-modal-error", is_open=False, color="danger",
                      className="mt-2 mb-0 small py-1"),
        ]),
        dbc.ModalFooter([
            dbc.Button("Guardar", id="syn-btn-save", color="primary"),
            dbc.Button("Cancelar", id="syn-btn-cancel", color="secondary", className="ms-2"),
        ]),
    ], id="syn-modal", is_open=False, size="lg")

    return html.Div([
        dcc.Store(id="syn-editing-id",  data=None),
        dcc.Store(id="syn-uid-store",   data={"uids": [], "counter": 0, "initial_values": {}}),
        dcc.Store(id="syn-all-opts",    data=[]),   # opciones de activos cacheadas

        dbc.Row([
            dbc.Col(html.H4("Activos Sintéticos", className="mb-0"), width="auto"),
            dbc.Col(dbc.Button("+ Nuevo", id="syn-btn-add", color="primary", size="sm"),
                    className="d-flex align-items-center"),
        ], className="mb-3 align-items-center g-2"),

        dbc.Alert(id="syn-alert", is_open=False, dismissable=True, className="mb-3"),

        html.Div(id="syn-table-container"),

        dbc.Card(dbc.CardBody([
            html.P([
                html.Strong("Activos sintéticos: ", style={"color": "#e5e7eb"}),
                "activos cuyo precio se calcula a partir de otros activos sin conexión externa. "
                "El activo destino debe estar creado con la fuente de precios ",
                html.Strong('"Calculado"', style={"color": "#e5e7eb"}),
                ". Disponibles cuatro tipos de fórmula: Ratio, Promedio ponderado, "
                "Suma ponderada e Índice base.",
            ], className="mb-0", style={"fontSize": "0.78rem", "color": "#d1d5db"}),
        ]), className="mt-3",
           style={"backgroundColor": "#1f2937", "border": "1px solid #374151"}),

        modal,
    ], style={"padding": "0 8px"})


dash.register_page(__name__, path="/admin/synthetic",
                   title="Activos Sintéticos", layout=layout)
