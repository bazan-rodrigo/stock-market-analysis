import dash
import dash_bootstrap_components as dbc
from dash import dash_table, dcc, html

from app.components.help import help_link

from app.components.table_styles import CELL, DATA, FILTER, HEADER, SELECTED_ROW
from app.components.ui_constants import (
    GROUP_TYPE_OPTS as _GROUP_TYPE_OPTS,
    CARD_STYLE, STATUS_STYLE,
)

_SOURCE_OPTS = [
    {"label": "Activo (asset)",   "value": "asset"},
    {"label": "Grupo (group)",    "value": "group"},
]
_FORMULA_OPTS = [
    {"label": "Mapa discreto (discrete_map)", "value": "discrete_map"},
    {"label": "Umbrales (threshold)",         "value": "threshold"},
    {"label": "Rango (range)",                "value": "range"},
]


def _build_indicator_opts() -> list[dict]:
    """Carga opciones de indicadores desde indicator_definitions, agrupadas por categoría."""
    try:
        from app.database import get_session
        from app.models.indicator_definition import IndicatorDefinition
        s = get_session()
        defs = s.query(IndicatorDefinition).order_by(
            IndicatorDefinition.category, IndicatorDefinition.code
        ).all()
    except Exception:
        return []

    opts: list[dict] = []
    current_cat = None
    sep_idx = 0
    for d in defs:
        if d.category != current_cat:
            current_cat = d.category
            sep_idx += 1
            opts.append({"label": f"── {d.category} ──", "value": f"__sep{sep_idx}", "disabled": True})
        opts.append({"label": f"{d.code}  –  {d.name}", "value": d.code})
    return opts


def layout(**kwargs):
    from flask_login import current_user
    # Abierto a analistas (ven públicas + propias, editan solo las propias).
    # El GuestUser con acceso público habilitado entra como admin — misma
    # convención que el resto de las pantallas admin (ver auth/manager.py)
    if not current_user.is_authenticated:
        return html.Div()
    is_admin = bool(current_user.is_admin)

    indicator_opts = _build_indicator_opts()

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
                    dcc.Dropdown(
                        id="sig-f-indicator-key",
                        placeholder="Seleccionar o escribir...",
                        clearable=True,
                        searchable=True,
                        options=indicator_opts,
                        style={"fontSize": "0.85rem"},
                    ),
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

            dbc.Switch(id="sig-f-public", label="Pública (visible para todos los usuarios)",
                       value=False, style={"fontSize": "0.82rem"},
                       className="mt-2"),
            html.Small(
                "Privada: solo vos (y el admin) la ven. Una señal pública "
                "solo puede referenciar señales públicas; no se puede "
                "despublicar si otros la usan.",
                className="text-muted d-block"),

            dbc.Label("Parámetros", style={"fontSize": "0.82rem", "marginTop": "8px"}),
            dbc.Row([
                dbc.Col([
                    html.Div(id="sig-params-builder", className="mb-1"),
                    dbc.Switch(id="sig-params-advanced",
                               label="Modo avanzado (editar JSON)", value=False,
                               style={"fontSize": "0.78rem"}, className="mt-1"),
                    html.Div(
                        dbc.Textarea(id="sig-f-params", rows=6,
                                     placeholder='{"map": {...}}',
                                     style={"fontSize": "0.80rem",
                                            "fontFamily": "monospace",
                                            "resize": "vertical"}),
                        id="sig-params-json-wrap", style={"display": "none"},
                    ),
                ], md=7),
                dbc.Col([
                    html.Small("Vista previa", className="text-muted d-block mb-1"),
                    dcc.Graph(id="sig-preview-graph",
                              config={"displayModeBar": False},
                              style={"height": "240px"}),
                ], md=5),
            ], className="g-3"),

            dbc.Alert(id="sig-modal-error", is_open=False, color="danger",
                      className="mt-2 mb-0 small py-1"),
        ]),
        dbc.ModalFooter([
            dbc.Button("Guardar",  id="sig-btn-save",   color="primary"),
            dbc.Button("Cancelar", id="sig-btn-cancel", color="secondary", className="ms-2"),
        ]),
    ], id="sig-modal", is_open=False, size="xl")

    return html.Div([
        dcc.Store(id="sig-editing-id",   data=None),
        dcc.Store(id="sig-pb-store",     data=None),
        dcc.Store(id="sig-pb-opts",      data={}),

        dbc.Card(dbc.CardBody([
            html.P([
                html.Strong("Señales: ", style={"color": "#e5e7eb"}),
                "fórmulas que transforman indicadores técnicos (de indicator_values) en scores "
                "normalizados de −100 a +100. Usá ",
                html.Strong('"Ejecutar pipeline"', style={"color": "#38bdf8"}),
                " para calcular señales → estrategias para la fecha seleccionada. "
                "Requiere que los indicadores estén actualizados.",
            ], className="mb-0", style={"fontSize": "0.78rem", "color": "#d1d5db"}),
        ]), className="mb-3",
           style=CARD_STYLE),

        dcc.Store(id="sig-selected-ids",  data=[]),
        dcc.Store(id="sig-all-ids",       data=[]),
        dcc.Download(id="sig-download"),

        dbc.Row([
            dbc.Col(html.H4(["Señales ", help_link("configuracion-senales")], className="mb-0"), width="auto"),
            dbc.Col(dbc.Button("+ Nueva", id="sig-btn-add", color="primary", size="sm"),
                    className="d-flex align-items-center"),
        ] + ([
            # Import/export de packs: solo admin (lo importado respeta la
            # columna `publica` del archivo)
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
        ] if is_admin else []), className="mb-2 align-items-center g-2"),

        html.Div([
            dbc.Button("Editar",   id="sig-btn-edit",   color="secondary",
                       size="sm", disabled=True, className="me-1"),
            dbc.Button("Eliminar", id="sig-btn-delete", color="danger",
                       size="sm", disabled=True, className="me-3"),
            dbc.Button("Calcular historia", id="sig-btn-history",
                       color="outline-warning", size="sm", disabled=True,
                       title="Llena las fechas pasadas sin valor de la señal "
                             "seleccionada (vacío = toda la historia; puede "
                             "tardar varios minutos)"),
            dbc.Input(id="sig-history-days", type="number", value=None,
                      placeholder="todo", min=1, step=1,
                      style={"fontSize": "0.82rem", "width": "90px",
                             "marginLeft": "8px"}),
            html.Small("días", className="text-muted",
                       style={"marginLeft": "4px", "marginRight": "12px"}),
        ] + ([
            dbc.Button("Ejecutar pipeline", id="sig-btn-recalc",
                       color="outline-info", size="sm"),
            dcc.DatePickerSingle(id="sig-recalc-date",
                                 display_format="YYYY-MM-DD",
                                 style={"fontSize": "0.82rem", "marginLeft": "8px",
                                        "width": "150px", "backgroundColor": "#2c2c2c",
                                        "border": "1px solid #555", "borderRadius": "4px"}),
        ] if is_admin else []), className="mb-2 d-flex align-items-center"),

        dcc.Loading(
            html.Div(id="sig-status", style=STATUS_STYLE),
            type="circle", color="#dee2e6",
        ),

        dbc.Alert(id="sig-alert", is_open=False, dismissable=True, className="mb-3"),
        html.Div(id="sig-import-results", className="mb-3"),
        dash_table.DataTable(
            id="sig-datatable",
            columns=[
                {"name": "Key",       "id": "key"},
                {"name": "Nombre",    "id": "name"},
                {"name": "Fuente",    "id": "source"},
                {"name": "Indicador", "id": "indicator_key"},
                {"name": "Fórmula",   "id": "formula_type"},
                {"name": "Dueño",     "id": "owner"},
                {"name": "Pública",   "id": "publica"},
            ],
            data=[],
            row_selectable="multi",
            selected_rows=[],
            style_table={"overflowX": "auto"},
            style_header=HEADER,
            style_data=DATA,
            style_cell=CELL,
            style_filter=FILTER,
            style_data_conditional=SELECTED_ROW + [
                {"if": {"filter_query": '{source} = "asset"'}, "color": "#38bdf8"},
                {"if": {"filter_query": '{source} = "group"'}, "color": "#4ade80"},
            ],
            page_size=30,
            sort_action="native",
            filter_action="native",
        ),

        modal,
    ], style={"padding": "0 8px"})


dash.register_page(__name__, path="/admin/signals",
                   title="Señales", layout=layout)
