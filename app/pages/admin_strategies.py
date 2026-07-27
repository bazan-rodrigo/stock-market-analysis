import dash
import dash_ag_grid as dag
import dash_bootstrap_components as dbc
from dash import dcc, html

from app.components.grids import (
    DEFAULT_COL_DEF, THEME_CLASS, grid_options, multi_selection, to_column_defs,
)
from app.components.help import page_header

from app.components.ui_constants import BG_CODE, BG_INPUT, STATUS_STYLE, TEXT_BODY


def layout(**kwargs):
    from flask_login import current_user
    # Abierto a analistas (ven públicas + propias, editan solo las propias).
    if not current_user.is_authenticated:
        return html.Div()
    is_admin = bool(current_user.is_admin)

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

            dbc.Switch(id="str-f-public",
                       label="Pública (visible para todos los usuarios)",
                       value=False, style={"fontSize": "0.82rem"}),
            html.Small(
                "Privada: solo vos (y el admin) la ven. Una estrategia "
                "pública solo puede usar señales públicas.",
                className="text-muted d-block mb-2"),

            # ── Componentes ─────────────────────────────────────────────────
            dbc.Label("Componentes", style={"fontSize": "0.82rem", "fontWeight": "bold",
                                             "marginBottom": "4px"}),

            # Cabecera fija
            dbc.Row([
                dbc.Col(html.Small("Señal (key)", className="text-muted"), md=8),
                dbc.Col(html.Small("Peso",        className="text-muted"), md=3),
                dbc.Col(style={"width": "32px"}),
            ], className="g-1 mb-1"),

            html.Div(id="str-comp-rows"),

            dbc.Button("+ Componente", id="str-btn-add-comp",
                       color="link", size="sm",
                       style={"fontSize": "0.80rem", "paddingLeft": 0}),

            # ── Filtro de elegibilidad ──────────────────────────────────────
            html.Hr(className="my-2"),
            dbc.Label("Filtro de elegibilidad", style={"fontSize": "0.82rem",
                                                       "fontWeight": "bold",
                                                       "marginBottom": "2px"}),
            html.Small(
                "Solo los activos que cumplen estas condiciones participan del "
                "ranking. Sin condiciones = todos los activos.",
                className="text-muted d-block mb-2",
            ),
            html.Div(id="str-filter-tree"),

            # ── Previsualización de la fórmula (solo lectura) ───────────────
            html.Hr(className="my-2"),
            dbc.Label("Fórmula (previsualización)",
                      style={"fontSize": "0.82rem", "fontWeight": "bold",
                             "marginBottom": "2px"}),
            html.Small(
                "Cómo queda el score y el filtro según los componentes de "
                "arriba. Solo para revalidar la lógica.",
                className="text-muted d-block mb-1",
            ),
            dbc.Textarea(
                id="str-formula-preview", readOnly=True, rows=6,
                style={"fontSize": "0.78rem", "fontFamily": "monospace",
                       "resize": "vertical", "backgroundColor": BG_CODE,
                       "color": "#dcdcdc", "whiteSpace": "pre"},
            ),

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
        dcc.Store(id="str-filter-store", data=None),
        dcc.Store(id="str-filter-opts",  data={}),
        dcc.Download(id="str-download"),

        dbc.Row([
            dbc.Col(page_header("Estrategias", "configuracion-estrategias", className="mb-0"), width="auto"),
            dbc.Col(dbc.Button("+ Nueva", id="str-btn-add", color="primary", size="sm"),
                    className="d-flex align-items-center"),
        ] + ([
            # Import/export de packs: solo admin (lo importado respeta la
            # columna `publica` del archivo)
            dbc.Col(dbc.Button("Exportar", id="str-btn-export",
                               color="secondary", size="sm", outline=True),
                    className="d-flex align-items-center"),
            dbc.Col(
                dcc.Upload(
                    dbc.Button("Importar", color="secondary", size="sm", outline=True),
                    id="str-upload", accept=".xlsx,.json", multiple=False,
                ),
                className="d-flex align-items-center",
            ),
        ] if is_admin else []), className="mb-2 align-items-center g-2"),

        html.Div([
            dbc.Button("Editar",   id="str-btn-edit",   color="secondary",
                       size="sm", disabled=True, className="me-1"),
            dbc.Button("Eliminar", id="str-btn-delete", color="danger",
                       size="sm", disabled=True, className="me-3"),
            dbc.Button("Calcular resultados", id="str-btn-calc",
                       color="outline-info", size="sm", disabled=True, className="me-1"),
            dcc.DatePickerSingle(id="str-calc-date",
                                 display_format="YYYY-MM-DD",
                                 style={"fontSize": "0.82rem", "marginLeft": "8px",
                                        "width": "150px", "backgroundColor": BG_INPUT,
                                        "border": "1px solid #555", "borderRadius": "4px"}),
            dbc.Button("Calcular historia", id="str-btn-history",
                       color="outline-warning", size="sm", disabled=True,
                       className="ms-3",
                       title="Llena las fechas pasadas sin resultado de la "
                             "estrategia seleccionada (vacío = toda la "
                             "historia; puede tardar varios minutos)"),
            dbc.Input(id="str-history-days", type="number", value=None,
                      placeholder="todo", min=1, step=1,
                      style={"fontSize": "0.82rem", "width": "90px",
                             "marginLeft": "8px"}),
            html.Small("días", className="text-muted",
                       style={"marginLeft": "4px"}),
        ], className="mb-2 d-flex align-items-center"),

        dcc.Loading(
            html.Div(id="str-status", style=STATUS_STYLE),
            type="circle", color=TEXT_BODY,
        ),

        dbc.Alert(id="str-alert", is_open=False, dismissable=True, className="mb-3"),
        html.Div(id="str-import-results", className="mb-3"),
        html.Div(id="str-calc-preview",   className="mb-3"),
        dag.AgGrid(
            id="str-datatable",
            columnDefs=to_column_defs([
                    {"name": "Nombre",      "id": "name"},
                    {"name": "Comp.",       "id": "components"},
                    {"name": "Filtro",      "id": "filter"},
                    {"name": "Dueño",       "id": "owner"},
                    {"name": "Pública",     "id": "publica"},
                    {"name": "Descripción", "id": "description"},
                
            ]),
            rowData=[],
            className=THEME_CLASS,
            style={"height": "calc(100vh - 340px)", "width": "100%"},
            defaultColDef=DEFAULT_COL_DEF,
            dashGridOptions=grid_options(rowSelection=multi_selection()),
        ),

        modal,
    ], style={"padding": "0 8px"})


dash.register_page(__name__, path="/admin/strategies",
                   title="Estrategias", layout=layout)
