import dash
import dash_bootstrap_components as dbc
from dash import dcc, html

_SCOPE_OPTS = [
    {"label": "Activo directo",          "value": ""},
    {"label": "Grupo propio (own_group)", "value": "own_group"},
    {"label": "Grupo fijo (specific)",    "value": "specific_group"},
]
_GROUP_TYPE_OPTS = [
    {"label": "Sector",   "value": "sector"},
    {"label": "Mercado",  "value": "market"},
    {"label": "Industria","value": "industry"},
]

_th = {"fontSize": "0.76rem", "color": "#9ca3af", "fontWeight": "normal",
       "padding": "5px 8px", "borderBottom": "1px solid #374151"}
_td = {"fontSize": "0.80rem", "padding": "5px 8px", "borderBottom": "1px solid #1f2937"}


def layout(**kwargs):
    from flask_login import current_user
    if not current_user.is_authenticated or not current_user.is_admin:
        return html.Div()

    modal = dbc.Modal([
        dbc.ModalHeader(dbc.ModalTitle(id="str-modal-title")),
        dbc.ModalBody([
            dbc.Row([
                dbc.Col([
                    dbc.Label("Nombre", style={"fontSize": "0.82rem"}),
                    dbc.Input(id="str-f-name", placeholder="Nombre de la estrategia",
                              style={"fontSize": "0.85rem"}),
                ]),
            ], className="mb-2"),

            dbc.Row([
                dbc.Col([
                    dbc.Label("Descripción", style={"fontSize": "0.82rem"}),
                    dbc.Textarea(id="str-f-description", rows=2,
                                 placeholder="Descripción opcional",
                                 style={"fontSize": "0.82rem", "resize": "vertical"}),
                ]),
            ], className="mb-2"),

            # ── Componentes ─────────────────────────────────────────────────
            dbc.Label("Componentes", style={"fontSize": "0.82rem", "fontWeight": "bold",
                                             "marginBottom": "4px"}),

            # Cabecera fija
            dbc.Row([
                dbc.Col(html.Small("Señal (key)", className="text-muted"), md=4),
                dbc.Col(html.Small("Peso",        className="text-muted"), md=2),
                dbc.Col(html.Small("Alcance",     className="text-muted"), md=3),
                dbc.Col(html.Small("Tipo grupo",  className="text-muted"), md=2),
                dbc.Col(style={"width": "32px"}),
            ], className="g-1 mb-1"),

            html.Div(id="str-comp-rows"),

            dbc.Button("+ Componente", id="str-btn-add-comp",
                       color="link", size="sm",
                       style={"fontSize": "0.80rem", "paddingLeft": 0}),

            dbc.Alert(id="str-modal-error", is_open=False, color="danger",
                      className="mt-2 mb-0 small py-1"),
        ]),
        dbc.ModalFooter([
            dbc.Button("Guardar",  id="str-btn-save",   color="primary"),
            dbc.Button("Cancelar", id="str-btn-cancel", color="secondary", className="ms-2"),
        ]),
    ], id="str-modal", is_open=False, size="xl")

    return html.Div([
        dcc.Store(id="str-editing-id",   data=None),
        dcc.Store(id="str-selected-ids", data=[]),
        dcc.Store(id="str-all-ids",      data=[]),
        dcc.Store(id="str-uid-store",    data={"uids": [], "counter": 0, "initial_values": {}}),
        dcc.Store(id="str-signal-opts",  data=[]),
        dcc.Download(id="str-download"),

        dbc.Row([
            dbc.Col(html.H4("Estrategias", className="mb-0"), width="auto"),
            dbc.Col(dbc.Button("+ Nueva", id="str-btn-add", color="primary", size="sm"),
                    className="d-flex align-items-center"),
            dbc.Col(dbc.Button("Exportar", id="str-btn-export",
                               color="secondary", size="sm", outline=True),
                    className="d-flex align-items-center"),
            dbc.Col(
                dcc.Upload(
                    dbc.Button("Importar", color="secondary", size="sm", outline=True),
                    id="str-upload", accept=".xlsx", multiple=False,
                ),
                className="d-flex align-items-center",
            ),
        ], className="mb-2 align-items-center g-2"),

        html.Div([
            dbc.Button("Editar",   id="str-btn-edit",   color="secondary",
                       size="sm", disabled=True, className="me-1"),
            dbc.Button("Eliminar", id="str-btn-delete", color="danger",
                       size="sm", disabled=True, className="me-3"),
            dbc.Button("Calcular resultados", id="str-btn-calc",
                       color="outline-info", size="sm", disabled=True, className="me-1"),
            dcc.DatePickerSingle(id="str-calc-date",
                                 display_format="YYYY-MM-DD",
                                 style={"fontSize": "0.82rem", "marginLeft": "4px"}),
        ], className="mb-2 d-flex align-items-center"),

        dcc.Loading(
            html.Div(id="str-status",
                     style={"fontSize": "0.82rem", "color": "#94a3b8",
                            "minHeight": "24px", "padding": "2px 0"}),
            type="circle", color="#dee2e6",
        ),

        dbc.Alert(id="str-alert", is_open=False, dismissable=True, className="mb-3"),
        html.Div(id="str-import-results", className="mb-3"),
        html.Div(id="str-table-container"),

        modal,
    ], style={"padding": "0 8px"})


dash.register_page(__name__, path="/admin/strategies",
                   title="Estrategias", layout=layout)
