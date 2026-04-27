import dash
import dash_bootstrap_components as dbc
from dash import dcc, html

_SOURCE_OPTS = [
    {"label": "Activo (asset)",   "value": "asset"},
    {"label": "Grupo (group)",    "value": "group"},
]
_FORMULA_OPTS = [
    {"label": "Mapa discreto (discrete_map)", "value": "discrete_map"},
    {"label": "Umbrales (threshold)",         "value": "threshold"},
    {"label": "Rango (range)",                "value": "range"},
    {"label": "Compuesta (composite)",        "value": "composite"},
]
_GROUP_TYPE_OPTS = [
    {"label": "Sector",   "value": "sector"},
    {"label": "Mercado",  "value": "market"},
    {"label": "Industria","value": "industry"},
]

_FORMULA_HELP = {
    "discrete_map": {
        "color": "#38bdf8",
        "title": "Mapa discreto",
        "desc": "Convierte un valor categórico (string) a un score usando un diccionario.",
        "example": '{"map": {"bullish_strong": 100, "bullish": 60, "lateral": 0, "bearish": -60}}',
    },
    "threshold": {
        "color": "#4ade80",
        "title": "Umbrales",
        "desc": (
            "Recorre umbrales en orden. Si el valor > límite retorna ese score. "
            "El último par [null, score] es el valor por defecto."
        ),
        "example": '{"thresholds": [[-5, 100], [-15, 50], [-30, 0], [null, -50]]}',
    },
    "range": {
        "color": "#fb923c",
        "title": "Rango lineal",
        "desc": "Mapea un valor numérico en [min, max] a [-100, 100] de forma lineal.",
        "example": '{"min": -3.0, "max": 3.0, "clamp": true}',
    },
    "composite": {
        "color": "#c084fc",
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

_th = {"fontSize": "0.76rem", "color": "#9ca3af", "fontWeight": "normal",
       "padding": "5px 8px", "borderBottom": "1px solid #374151"}
_td = {"fontSize": "0.80rem", "padding": "5px 8px", "borderBottom": "1px solid #1f2937"}


def _help_card(ft: str | None):
    if not ft or ft not in _FORMULA_HELP:
        return html.Div()
    h = _FORMULA_HELP[ft]
    c = h["color"]
    return dbc.Card(dbc.CardBody([
        html.Strong(h["title"], style={"color": c, "fontSize": "0.84rem"}),
        html.P(h["desc"], style={"fontSize": "0.77rem", "color": "#d1d5db", "margin": "4px 0"}),
        html.Code(h["example"],
                  style={"display": "block", "whiteSpace": "pre", "fontSize": "0.74rem",
                         "backgroundColor": "#111827", "padding": "6px 10px",
                         "borderRadius": "4px", "color": c, "fontFamily": "monospace"}),
    ]), style={"backgroundColor": "#1a2332", "border": f"1px solid {c}33",
               "borderLeft": f"3px solid {c}"}, className="mb-2")


def layout(**kwargs):
    from flask_login import current_user
    if not current_user.is_authenticated or not current_user.is_admin:
        return html.Div()

    modal = dbc.Modal([
        dbc.ModalHeader(dbc.ModalTitle(id="sig-modal-title")),
        dbc.ModalBody([
            dbc.Row([
                dbc.Col([
                    dbc.Label("Clave (key)", style={"fontSize": "0.82rem"}),
                    dbc.Input(id="sig-f-key", placeholder="ej: tendencia_d",
                              style={"fontSize": "0.85rem"}),
                ], md=6),
                dbc.Col([
                    dbc.Label("Nombre", style={"fontSize": "0.82rem"}),
                    dbc.Input(id="sig-f-name", placeholder="Nombre legible",
                              style={"fontSize": "0.85rem"}),
                ], md=6),
            ], className="mb-2"),

            dbc.Row([
                dbc.Col([
                    dbc.Label("Fuente", style={"fontSize": "0.82rem"}),
                    dcc.Dropdown(id="sig-f-source", options=_SOURCE_OPTS,
                                 placeholder="asset o group", clearable=False,
                                 style={"fontSize": "0.85rem"}),
                ], md=4),
                dbc.Col([
                    dbc.Label("Tipo de grupo", style={"fontSize": "0.82rem"}),
                    dcc.Dropdown(id="sig-f-group-type", options=_GROUP_TYPE_OPTS,
                                 placeholder="Solo si fuente=group",
                                 style={"fontSize": "0.85rem"}),
                ], md=4, id="sig-col-group-type"),
                dbc.Col([
                    dbc.Label("Clave de indicador", style={"fontSize": "0.82rem"}),
                    dbc.Input(id="sig-f-indicator-key",
                              placeholder="ej: regime_d, dd_current",
                              style={"fontSize": "0.85rem"}),
                ], md=4),
            ], className="mb-2"),

            dbc.Row([
                dbc.Col([
                    dbc.Label("Tipo de fórmula", style={"fontSize": "0.82rem"}),
                    dcc.Dropdown(id="sig-f-formula-type", options=_FORMULA_OPTS,
                                 placeholder="Seleccionar...", clearable=False,
                                 style={"fontSize": "0.85rem"}),
                ]),
            ], className="mb-2"),

            html.Div(id="sig-formula-help"),

            dbc.Label("Descripción", style={"fontSize": "0.82rem"}),
            dbc.Textarea(id="sig-f-description", rows=2,
                         placeholder="Descripción opcional",
                         style={"fontSize": "0.82rem", "resize": "vertical"}),

            dbc.Label("Parámetros (JSON)", style={"fontSize": "0.82rem", "marginTop": "8px"}),
            dbc.Textarea(id="sig-f-params", rows=6,
                         placeholder='{"map": {...}}',
                         style={"fontSize": "0.80rem", "fontFamily": "monospace",
                                "resize": "vertical"}),

            dbc.Alert(id="sig-modal-error", is_open=False, color="danger",
                      className="mt-2 mb-0 small py-1"),
        ]),
        dbc.ModalFooter([
            dbc.Button("Guardar",  id="sig-btn-save",   color="primary"),
            dbc.Button("Cancelar", id="sig-btn-cancel", color="secondary", className="ms-2"),
        ]),
    ], id="sig-modal", is_open=False, size="lg")

    return html.Div([
        dcc.Store(id="sig-editing-id", data=None),
        dcc.Store(id="sig-selected-ids", data=[]),
        dcc.Store(id="sig-all-ids", data=[]),
        dcc.Download(id="sig-download"),

        dbc.Row([
            dbc.Col(html.H4("Señales", className="mb-0"), width="auto"),
            dbc.Col(dbc.Button("+ Nueva", id="sig-btn-add", color="primary", size="sm"),
                    className="d-flex align-items-center"),
            dbc.Col(dbc.Button("Exportar", id="sig-btn-export",
                               color="secondary", size="sm", outline=True),
                    className="d-flex align-items-center"),
            dbc.Col(
                dcc.Upload(
                    dbc.Button("Importar", color="secondary", size="sm", outline=True),
                    id="sig-upload", accept=".xlsx", multiple=False,
                ),
                className="d-flex align-items-center",
            ),
        ], className="mb-2 align-items-center g-2"),

        html.Div([
            dbc.Button("Editar",   id="sig-btn-edit",   color="secondary",
                       size="sm", disabled=True, className="me-1"),
            dbc.Button("Eliminar", id="sig-btn-delete", color="danger",
                       size="sm", disabled=True, className="me-3"),
            dbc.Button("Recalcular señales (hoy)", id="sig-btn-recalc",
                       color="outline-info", size="sm"),
            dcc.DatePickerSingle(id="sig-recalc-date",
                                 display_format="YYYY-MM-DD",
                                 style={"fontSize": "0.82rem", "marginLeft": "8px"}),
        ], className="mb-2 d-flex align-items-center"),

        dcc.Loading(
            html.Div(id="sig-status",
                     style={"fontSize": "0.82rem", "color": "#94a3b8",
                            "minHeight": "24px", "padding": "2px 0"}),
            type="circle", color="#dee2e6",
        ),

        dbc.Alert(id="sig-alert", is_open=False, dismissable=True, className="mb-3"),
        html.Div(id="sig-import-results", className="mb-3"),
        html.Div(id="sig-table-container"),

        modal,
    ], style={"padding": "0 8px"})


dash.register_page(__name__, path="/admin/signals",
                   title="Señales", layout=layout)
