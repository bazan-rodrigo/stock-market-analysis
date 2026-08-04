import dash
import dash_ag_grid as dag
import dash_bootstrap_components as dbc
from dash import dcc, html

from app.components.grids import (
    DEFAULT_COL_DEF, THEME_CLASS, grid_options, multi_selection, to_column_defs,
)
from app.components.help import page_header

from app.components.ui_constants import (
    BG_INPUT, CARD_STYLE, COLOR_INFO, STATUS_STYLE, TEXT_BODY
)

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


def params_con_escala(params_txt: str | None, min_txt, max_txt) -> str:
    """params de la señal con el min/max propuestos pisados. Lógica pura.

    Los valores llegan como texto desde la query string; si no son números se
    ignoran y quedan los de la señal (una URL editada a mano no debe romper el
    editor)."""
    import json

    propuestos = {}
    for campo, crudo in (("min", min_txt), ("max", max_txt)):
        if crudo is None or str(crudo).strip() == "":
            continue
        try:
            propuestos[campo] = float(crudo)
        except (TypeError, ValueError):
            continue
    if not propuestos:
        return params_txt or "{}"
    try:
        p = json.loads(params_txt or "{}")
    except (ValueError, TypeError):
        return params_txt or "{}"
    p.update(propuestos)
    return json.dumps(p, ensure_ascii=False)


def _preseleccion(kwargs: dict) -> dict:
    """Editor abierto con una señal cargada al llegar desde Calibración
    (`/admin/signals?editar=<key>&min=&max=`).

    Va en el LAYOUT y no en un callback sobre la URL: cuando la página se
    carga, el cambio de `url.search` **ya ocurrió** antes de que existieran los
    componentes del modal, así que un callback sobre él nunca llega a
    dispararse (con `prevent_initial_call` se pierde la primera llamada, que es
    la única que hay). Dash sí le pasa la query string al layout.

    Devuelve {} si no hay nada que preseleccionar; ante cualquier problema
    también, que es abrir la pantalla normal en vez de un modal roto.
    """
    key = (kwargs.get("editar") or "").strip()
    if not key:
        return {}
    try:
        import app.services.signal_service as svc
        from app.callbacks.signal_params_ui import (
            builder_from_params, empty_params_store,
        )
        from app.services.visibility import current_viewer

        sig = next((s for s in svc.get_visible_signals(*current_viewer())
                    if (s.key or "").lower() == key.lower()), None)
        if sig is None:
            return {}
        params_txt = params_con_escala(sig.params, kwargs.get("min"),
                                       kwargs.get("max"))
        pb = builder_from_params(sig.formula_type, params_txt)
        return {
            "id": sig.id, "key": sig.key, "name": sig.name,
            "indicator_key": sig.indicator_key,
            "formula_type": sig.formula_type,
            "description": sig.description or "",
            "is_public": bool(sig.is_public),
            "params": params_txt,
            "pb_store": pb if pb is not None else empty_params_store(),
            "advanced": pb is None,
        }
    except Exception:
        return {}


def layout(**kwargs):
    from flask_login import current_user
    # Abierto a analistas (ven públicas + propias, editan solo las propias).
    if not current_user.is_authenticated:
        return html.Div()
    is_admin = bool(current_user.is_admin)

    indicator_opts = _build_indicator_opts()
    pre = _preseleccion(kwargs)

    modal = dbc.Modal([
        dbc.ModalHeader(dbc.ModalTitle(
            id="sig-modal-title",
            children=("Editar señal — escala traída de Calibración "
                      "(todavía sin guardar)") if pre else None)),
        dbc.ModalBody([
            dbc.Row([
                dbc.Col([
                    dbc.Label("Clave (key)", style={"fontSize": "0.82rem"}),
                    dbc.Input(id="sig-f-key", placeholder="ej: tendencia_d",
                              value=pre.get("key"),
                              disabled=bool(pre),
                              style={"fontSize": "0.85rem"}),
                ], md=6),
                dbc.Col([
                    dbc.Label("Nombre", style={"fontSize": "0.82rem"}),
                    dbc.Input(id="sig-f-name", placeholder="Nombre legible",
                              value=pre.get("name"),
                              style={"fontSize": "0.85rem"}),
                ], md=6),
            ], className="mb-2"),

            dbc.Row([
                dbc.Col([
                    dbc.Label("Clave de indicador", style={"fontSize": "0.82rem"}),
                    dcc.Dropdown(
                        id="sig-f-indicator-key",
                        placeholder="Seleccionar o escribir...",
                        clearable=True,
                        searchable=True,
                        options=indicator_opts,
                        value=pre.get("indicator_key"),
                        style={"fontSize": "0.85rem"},
                    ),
                ]),
            ], className="mb-2"),

            dbc.Row([
                dbc.Col([
                    dbc.Label("Tipo de fórmula", style={"fontSize": "0.82rem"}),
                    dcc.Dropdown(id="sig-f-formula-type", options=_FORMULA_OPTS,
                                 value=pre.get("formula_type"),
                                 placeholder="Seleccionar...", clearable=False,
                                 style={"fontSize": "0.85rem"}),
                ]),
            ], className="mb-2"),

            html.Div(id="sig-formula-help"),

            dbc.Label("Descripción", style={"fontSize": "0.82rem"}),
            dbc.Textarea(id="sig-f-description", rows=2,
                         value=pre.get("description"),
                         placeholder="Descripción opcional",
                         style={"fontSize": "0.82rem", "resize": "vertical"}),

            dbc.Switch(id="sig-f-public", label="Pública (visible para todos los usuarios)",
                       value=pre.get("is_public", False), style={"fontSize": "0.82rem"},
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
                               label="Modo avanzado (editar JSON)",
                               value=pre.get("advanced", False),
                               style={"fontSize": "0.78rem"}, className="mt-1"),
                    html.Div(
                        dbc.Textarea(id="sig-f-params", rows=6,
                                     value=pre.get("params"),
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
    ], id="sig-modal", is_open=bool(pre), size="xl")

    return html.Div([
        dcc.Store(id="sig-editing-id",   data=pre.get("id")),
        dcc.Store(id="sig-pb-store",     data=pre.get("pb_store")),
        dcc.Store(id="sig-pb-opts",      data={}),
        # Distribución real del indicador elegido, para el fondo de la
        # vista previa. Se cachea acá y no se recalcula con cada tecla
        # del min/max: sin esto cada pulsación iría a la base.
        dcc.Store(id="sig-dist-store",   data=None),

        dbc.Card(dbc.CardBody([
            html.P([
                html.Strong("Señales: ", style={"color": "#e5e7eb"}),
                "fórmulas que transforman indicadores técnicos en scores "
                "normalizados de −100 a +100. Usá ",
                html.Strong('"Ejecutar pipeline"', style={"color": COLOR_INFO}),
                " para calcular señales → estrategias para la fecha seleccionada. "
                "Requiere que los indicadores estén actualizados.",
            ], className="mb-0", style={"fontSize": "0.78rem", "color": "#d1d5db"}),
        ]), className="mb-3",
           style=CARD_STYLE),

        dcc.Store(id="sig-selected-ids",  data=[]),
        dcc.Store(id="sig-all-ids",       data=[]),
        dcc.Download(id="sig-download"),

        dbc.Row([
            dbc.Col(page_header("Señales", "configuracion-senales", className="mb-0"), width="auto"),
            # Crear una señal es exclusivo de un administrador (el catálogo es
            # curado — signal_service.ADMIN_ONLY_MOTIVO). El botón se muestra
            # deshabilitado en vez de ocultarse: así el analista ve que la
            # función existe y por qué no la tiene, en vez de no encontrarla.
            dbc.Col(dbc.Button("+ Nueva", id="sig-btn-add", color="primary",
                               size="sm", disabled=not is_admin,
                               title=None if is_admin else
                               "Solo un administrador puede crear señales. "
                               "Podés proponerle la señal a un administrador."),
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
                    id="sig-upload", accept=".xlsx,.json", multiple=False,
                ),
                className="d-flex align-items-center",
            ),
            dbc.Col(dbc.Button("Catálogo", id="sig-btn-catalog",
                               color="secondary", size="sm", outline=True,
                               title="Descarga el catálogo de esta instalación "
                                     "(indicadores, categorías, sectores, "
                                     "señales existentes) para armar packs "
                                     "importables"),
                    className="d-flex align-items-center"),
        ] if is_admin else []), className="mb-2 align-items-center g-2"),

        html.Div([
            # Editar/Eliminar: también solo admin. Arrancan deshabilitados y
            # los habilita update_buttons, que exige rol admin además de la
            # selección (el gate de verdad está en el servicio).
            dbc.Button("Editar",   id="sig-btn-edit",   color="secondary",
                       size="sm", disabled=True, className="me-1",
                       title=None if is_admin else
                       "Solo un administrador puede editar señales."),
            dbc.Button("Eliminar", id="sig-btn-delete", color="danger",
                       size="sm", disabled=True, className="me-3",
                       title=None if is_admin else
                       "Solo un administrador puede eliminar señales."),
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
                                        "width": "150px", "backgroundColor": BG_INPUT,
                                        "border": "1px solid #555", "borderRadius": "4px"}),
        ] if is_admin else []), className="mb-2 d-flex align-items-center"),

        dcc.Loading(
            html.Div(id="sig-status", style=STATUS_STYLE),
            type="circle", color=TEXT_BODY,
        ),

        dbc.Alert(id="sig-alert", is_open=False, dismissable=True, className="mb-3"),
        html.Div(id="sig-import-results", className="mb-3"),
        dag.AgGrid(
            id="sig-datatable",
            columnDefs=to_column_defs([
                {"name": "Key",       "id": "key",           "width": 150},
                {"name": "Nombre",    "id": "name",          "width": 240},
                {"name": "Indicador", "id": "indicator_key", "width": 170},
                {"name": "Fórmula",   "id": "formula_type",  "width": 140},
                {"name": "Dueño",     "id": "owner",         "width": 130},
                {"name": "Pública",   "id": "publica",       "width": 100},
                # La descripción es donde vive el CRITERIO de la señal (que el
                # RSI puntúa la sobreventa, que tal indicador no cubre a todos
                # los activos). Estaba solo dentro del editor, así que para
                # leerla había que abrir señal por señal. Mismo formato que la
                # grilla de indicadores: flexible y con alto automático.
                {"field": "description", "headerName": "Descripción",
                 "flex": 1, "minWidth": 300, "wrapText": True,
                 "autoHeight": True},
            ]),
            rowData=[],
            className=THEME_CLASS,
            style={"height": "calc(100vh - 340px)", "width": "100%"},
            defaultColDef=DEFAULT_COL_DEF,
            dashGridOptions=grid_options(rowSelection=multi_selection()),
        ),

        modal,
    ], style={"padding": "0 8px"})


dash.register_page(__name__, path="/admin/signals",
                   title="Señales", layout=layout)
