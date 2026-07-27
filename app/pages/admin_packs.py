"""Pantalla de packs: subir, revisar y aplicar en un solo lugar.

Por qué existe teniendo Señales e Importar en cada ABM: un pack es una UNIDAD
(las señales y la estrategia que las usa), pero los ABMs importan cada tipo por
separado, así que el mismo archivo había que subirlo dos veces y en el orden
correcto. Y sobre todo: ahí el import escribe y después cuenta qué pasó. Acá
primero se ve el informe —qué crea, qué pisa, qué avisos hay— y recién después
se decide.

Los botones de Importar/Exportar de Señales y Estrategias siguen existiendo:
sirven para el export/import masivo de todas las definiciones, que es otro
caso de uso.
"""
import dash
import dash_ag_grid as dag
import dash_bootstrap_components as dbc
from dash import dcc, html

from app.components.grids import (
    DEFAULT_COL_DEF, THEME_CLASS, grid_options, import_status_conditions, text_col,
)
from app.components.help import page_header
from app.components.ui_constants import TEXT_BODY, TEXT_MUTED

_COLUMNS = [
    text_col("tipo",   "Tipo",    width=110),
    text_col("nombre", "Nombre",  width=240),
    text_col("accion", "Acción",  width=110),
    text_col("dueno",  "Dueño actual", width=130, muted=True),
    text_col("detail", "Detalle", width=420, muted=True),
    text_col("status", "Resultado", width=200),
]


def layout(**kwargs):
    from flask_login import current_user
    if not current_user.is_authenticated or not current_user.is_admin:
        return html.Div("Acceso denegado", className="text-danger mt-4")

    return html.Div([
        page_header("Packs de señales y estrategias",
                    "packs-de-senales-y-estrategias", className="mb-3"),

        dbc.Row([
            dbc.Col(dbc.Card(dbc.CardBody([
                html.H5("1. Catálogo", className="mb-2"),
                html.P(
                    "Quien escriba el pack necesita saber qué indicadores y qué "
                    "sectores existen en esta instalación. Descargá el catálogo "
                    "y entregáselo junto con la especificación del formato.",
                    className="small text-muted",
                ),
                dbc.Button("Descargar catálogo", id="pk-btn-catalog",
                           color="secondary", size="sm", outline=True),
                dcc.Download(id="pk-download"),
            ])), md=4),

            dbc.Col(dbc.Card(dbc.CardBody([
                html.H5("2. Subir el pack", className="mb-2"),
                html.P(
                    "Un archivo .json con las señales y la estrategia juntas. "
                    "Se revisa contra esta base sin escribir nada.",
                    className="small text-muted",
                ),
                dcc.Upload(
                    id="pk-upload",
                    children=dbc.Button("Seleccionar archivo .json",
                                        color="primary", size="sm"),
                    accept=".json", multiple=False,
                ),
                html.Div(id="pk-filename", className="text-muted mt-2 small"),
                dcc.Store(id="pk-file-store"),
            ])), md=8),
        ], className="mb-3"),

        dcc.Loading(
            dbc.Card(dbc.CardBody([
                html.Div([
                    html.H5("3. Informe", className="d-inline-block me-3 mb-0"),
                    dbc.Button("Importar", id="pk-btn-import", color="success",
                               size="sm", disabled=True, className="me-2"),
                    dbc.Button("Limpiar", id="pk-btn-clear", color="link", size="sm"),
                ], className="d-flex align-items-center mb-2"),

                dbc.Alert(id="pk-alert", is_open=False, className="py-2 small"),
                html.Div(id="pk-diagnostics"),

                dag.AgGrid(
                    id="pk-table",
                    columnDefs=_COLUMNS,
                    rowData=[],
                    className=THEME_CLASS,
                    style={"height": "340px", "width": "100%"},
                    defaultColDef=DEFAULT_COL_DEF,
                    # El color sale de un campo aparte con los códigos que el
                    # sistema ya usa (imported/error/skipped); la columna
                    # visible lleva el detalle en castellano.
                    getRowStyle={"styleConditions": import_status_conditions("estado")},
                    dashGridOptions=grid_options(),
                ),

                html.Small(
                    "Importar no calcula nada: para llenar la historia de la "
                    "estrategia nueva, andá al Centro de Datos → Señales y "
                    "Estrategias → Ejecutar, con el alcance en esa estrategia.",
                    style={"color": TEXT_MUTED}, className="d-block mt-2",
                ),
            ])),
            type="circle", color=TEXT_BODY,
        ),
    ])


dash.register_page(
    __name__,
    path="/admin/packs",
    title="Packs",
    layout=layout,
)
