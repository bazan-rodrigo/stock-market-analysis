import dash
import dash_bootstrap_components as dbc
from dash import dcc, html

from app.components.ui_constants import (
    TH as _th, TD as _td,
    GROUP_TYPE_OPTS as _GROUP_TYPE_OPTS,
    FORMULA_HELP as _FORMULA_HELP,
    CARD_STYLE, STATUS_STYLE,
    formula_help_card as _help_card,
)

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
        dcc.Store(id="sig-editing-id",   data=None),

        dbc.Card(dbc.CardBody([
            html.P([
                html.Strong("Señales: ", style={"color": "#e5e7eb"}),
                "fórmulas que transforman indicadores técnicos (de screener_snapshot) en scores "
                "normalizados de −100 a +100. Usá ",
                html.Strong('"Ejecutar pipeline"', style={"color": "#38bdf8"}),
                " para calcular indicadores → señales → estrategias para la fecha seleccionada. "
                "Requiere que el screener_snapshot esté actualizado.",
            ], className="mb-0", style={"fontSize": "0.78rem", "color": "#d1d5db"}),
        ]), className="mb-3",
           style=CARD_STYLE),

        dcc.Store(id="sig-selected-ids",  data=[]),
        dcc.Store(id="sig-all-ids",       data=[]),
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
            dbc.Button("Ejecutar pipeline", id="sig-btn-recalc",
                       color="outline-info", size="sm"),
            dcc.DatePickerSingle(id="sig-recalc-date",
                                 display_format="YYYY-MM-DD",
                                 style={"fontSize": "0.82rem", "marginLeft": "8px",
                                        "width": "150px", "backgroundColor": "#2c2c2c",
                                        "border": "1px solid #555", "borderRadius": "4px"}),
        ], className="mb-2 d-flex align-items-center"),

        dcc.Loading(
            html.Div(id="sig-status", style=STATUS_STYLE),
            type="circle", color="#dee2e6",
        ),

        dbc.Alert(id="sig-alert", is_open=False, dismissable=True, className="mb-3"),
        html.Div(id="sig-import-results", className="mb-3"),
        html.Div(id="sig-table-container"),

        modal,
    ], style={"padding": "0 8px"})


dash.register_page(__name__, path="/admin/signals",
                   title="Señales", layout=layout)
