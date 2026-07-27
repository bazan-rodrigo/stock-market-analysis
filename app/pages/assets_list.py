import dash
import dash_ag_grid as dag
import dash_bootstrap_components as dbc
from dash import dcc, html

from app.components.grids import (
    DEFAULT_COL_DEF, THEME_CLASS, grid_options, multi_selection, text_col,
)
from app.components.help import page_header

_BULK_FIELDS = [
    {"label": "Benchmark",               "value": "benchmark_id"},
    {"label": "Mercado",                 "value": "market_id"},
    {"label": "País",                    "value": "country_id"},
    {"label": "Tipo de instrumento",     "value": "instrument_type_id"},
    {"label": "Moneda",                  "value": "currency_id"},
    {"label": "Sector",                  "value": "sector_id"},
    {"label": "Industria",               "value": "industry_id"},
    {"label": "Fuente de fundamentales", "value": "fundamental_source_id"},
]

_COLUMNS = [
    text_col("ticker",               "Ticker",    width=110, pinned="left"),
    text_col("name",                 "Nombre",    width=220),
    text_col("country_name",         "País",      width=110),
    text_col("market_name",          "Mercado",   width=160),
    text_col("instrument_type_name", "Tipo",      width=110),
    text_col("currency_name",        "Moneda",    width=100),
    text_col("sector_name",          "Sector",    width=130),
    text_col("benchmark_ticker",     "Benchmark", width=110),
    text_col("source_name",          "Fuente precios", width=120),
    text_col("fund_source_name",     "Fuente fund.",   width=120),
]


def _build_asset_form():
    return dbc.Form([
        dbc.Row([
            dbc.Col([dbc.Label("Ticker *"), dbc.Input(id="assets-f-ticker", placeholder="AAPL")]),
            dbc.Col([dbc.Label("Fuente de precios *"), dbc.Select(id="assets-f-price_source_id", options=[])]),
        ], className="mb-3"),
        dbc.Row([
            dbc.Col([dbc.Label("Nombre"), dbc.Input(id="assets-f-name", placeholder="Apple Inc.")]),
            dbc.Col([dbc.Label("Moneda"), dbc.Select(id="assets-f-currency_id", options=[])]),
        ], className="mb-3"),
        dbc.Row([
            dbc.Col([dbc.Label("País"), dbc.Select(id="assets-f-country_id", options=[])]),
            dbc.Col([dbc.Label("Mercado"), dbc.Select(id="assets-f-market_id", options=[])]),
        ], className="mb-3"),
        dbc.Row([
            dbc.Col([dbc.Label("Tipo de instrumento"), dbc.Select(id="assets-f-instrument_type_id", options=[])]),
            dbc.Col([dbc.Label("Sector"), dbc.Select(id="assets-f-sector_id", options=[])]),
        ], className="mb-3"),
        dbc.Row([
            dbc.Col([dbc.Label("Industria"), dbc.Select(id="assets-f-industry_id", options=[])]),
            dbc.Col([
                dbc.Label("Benchmark"),
                dcc.Dropdown(id="assets-f-benchmark_id", placeholder="Sin benchmark (opcional)",
                             clearable=True, style={"fontSize": "0.9rem"}),
            ]),
        ], className="mb-3"),
        dbc.Row([
            dbc.Col([
                dbc.Label("Fuente de fundamentales"),
                dbc.Select(id="assets-f-fundamental_source_id", options=[],
                           placeholder="Sin fuente (opcional)"),
            ], md=6),
        ], className="mb-3"),
        dbc.Alert(id="assets-form-error", is_open=False, color="danger", className="mt-2"),
        dbc.Alert(id="assets-autocomplete-alert", is_open=False, color="info", className="mt-2"),
    ])


def layout(**kwargs):
    from flask_login import current_user
    if not current_user.is_authenticated:
        return html.Div()
    is_admin = current_user.is_admin

    admin_buttons = []
    if is_admin:
        admin_buttons = [
            dbc.Button("+ Nuevo activo", id="assets-btn-add", color="primary", size="sm", className="me-2"),
            dbc.Button("Editar", id="assets-btn-edit", color="secondary", size="sm", disabled=True, className="me-2"),
            dbc.Button("Eliminar", id="assets-btn-delete", color="danger", size="sm", disabled=True, className="me-2"),
        ]

    return html.Div([
        dcc.Store(id="assets-editing-id", data=None),
        html.Div([
            page_header("Activos", "gestion-de-activos", className="d-inline-block me-3"),
            *admin_buttons,
            dbc.Button("Sel. todos", id="assets-btn-select-all", color="outline-secondary", size="sm", className="me-1"),
            dbc.Button("Desel. todos", id="assets-btn-deselect-all", color="outline-secondary", size="sm"),
        ], className="d-flex align-items-center mb-3"),
        dbc.Alert(id="assets-alert", is_open=False, dismissable=True),
        # ── Barra de acción masiva (visible cuando hay 1+ filas seleccionadas) ──
        dbc.Collapse(
            dbc.Card(dbc.CardBody([
                dbc.Row([
                    dbc.Col([
                        dbc.Label("Campo", className="small fw-semibold mb-0"),
                        dbc.Select(id="assets-bulk-field", options=_BULK_FIELDS, size="sm"),
                    ], width="auto"),
                    dbc.Col([
                        dbc.Label("Nuevo valor", className="small fw-semibold mb-0"),
                        dcc.Dropdown(
                            id="assets-bulk-value",
                            placeholder="Seleccioná...",
                            clearable=True,
                            style={"fontSize": "0.85rem", "minWidth": "220px"},
                        ),
                    ], width="auto"),
                    dbc.Col([
                        dbc.Label("\u00a0", className="small d-block"),
                        dbc.Button("Aplicar a seleccionados", id="assets-bulk-apply",
                                   color="warning", size="sm"),
                        dbc.Button("Limpiar campo", id="assets-bulk-clear",
                                   color="outline-secondary", size="sm", className="ms-2"),
                    ], width="auto"),
                    dbc.Col([
                        dbc.Label("\u00a0", className="small d-block"),
                        html.Span(id="assets-bulk-count", className="text-muted small"),
                    ], width="auto", className="d-flex align-items-end pb-1"),
                ], className="g-2 align-items-end"),
                dbc.Alert(id="assets-bulk-alert", is_open=False, dismissable=True,
                          className="mt-2 mb-0 py-1 small"),
            ], className="py-2 px-3"), className="mb-2"),
            id="assets-bulk-collapse",
            is_open=False,
        ),
        dag.AgGrid(
            id="assets-table",
            columnDefs=_COLUMNS,
            rowData=[],
            className=THEME_CLASS,
            style={"height": "calc(100vh - 300px)", "width": "100%"},
            defaultColDef=DEFAULT_COL_DEF,
            # Identidad de fila por id: sin esto, la selección se pierde cada
            # vez que el callback reescribe las filas (después de un alta, un
            # borrado o una edición masiva).
            getRowId="params.data.id",
            dashGridOptions=grid_options(rowSelection=multi_selection()),
        ),
        dbc.Modal([
            dbc.ModalHeader(dbc.ModalTitle(id="assets-modal-title")),
            dbc.ModalBody(_build_asset_form()),
            dbc.ModalFooter([
                dbc.Button("Autocompletar desde fuente", id="assets-btn-autocomplete", color="info", size="sm", className="me-auto"),
                dbc.Button("Guardar", id="assets-btn-save", color="primary"),
                dbc.Button("Cancelar", id="assets-btn-cancel", color="secondary", className="ms-2"),
            ]),
        ], id="assets-modal", is_open=False, size="lg"),
        dbc.Modal([
            dbc.ModalHeader(dbc.ModalTitle("Confirmar eliminación")),
            dbc.ModalBody(id="assets-confirm-body", children="¿Eliminás este activo y toda su historia de precios?"),
            dbc.ModalFooter([
                dbc.Button("Sí, eliminar", id="assets-btn-confirm-delete", color="danger"),
                dbc.Button("Cancelar", id="assets-btn-cancel-delete", color="secondary", className="ms-2"),
            ]),
        ], id="assets-confirm-modal", is_open=False),
    ])


dash.register_page(__name__, path="/assets", title="Activos", layout=layout)
