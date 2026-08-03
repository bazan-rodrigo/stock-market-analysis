"""Calibración de señales: dónde vive la masa de un indicador y qué recorta la
escala que le pusiste.

Existe porque el modo de fallar de una señal mal escalada es SILENCIOSO. Con
`clamp`, una escala más angosta que los datos deja a los activos pegados en
±100: la señal aporta el mismo número a todos y el ranking —que es
transversal— deja de ordenar por ella, sin que nada dé error. Una escala
demasiado ancha hace lo mismo apiñando todo cerca del cero.

Lo que la pantalla del editor no puede dar, y por eso esto es una pantalla
aparte: **comparar varias fechas**. Los indicadores que se reinician con el
calendario (retorno del mes, del trimestre, del año) ensanchan su dispersión a
lo largo del período, así que una escala que recorta el 10% a mitad de camino
puede recortar el 30% al final. Con una sola fecha ese defecto es invisible.

No escribe nada: se analiza acá y el número se lleva al editor de Señales, que
es el único lugar donde se guarda.
"""
import dash
import dash_ag_grid as dag
import dash_bootstrap_components as dbc
from dash import dcc, html

from app.components.grids import (
    DEFAULT_COL_DEF, THEME_CLASS, grid_options, to_column_defs,
)
from app.components.help import page_header
from app.components.ui_constants import (
    BG_INPUT, CARD_STYLE, COLOR_INFO, TEXT_BODY, TEXT_MUTED,
)

_INPUT_SM = {"fontSize": "0.82rem", "backgroundColor": BG_INPUT}


def _indicator_options() -> list[dict]:
    """Indicadores agrupados por categoría, igual que en el editor de señales.
    Si la base no está disponible se devuelve vacío en vez de tumbar la página."""
    try:
        from app.database import get_session
        from app.models.indicator_definition import IndicatorDefinition
        s = get_session()
        defs = s.query(IndicatorDefinition).order_by(
            IndicatorDefinition.category, IndicatorDefinition.code).all()
    except Exception:
        return []

    opts: list[dict] = []
    cat = None
    for i, d in enumerate(defs):
        if d.category != cat:
            cat = d.category
            opts.append({"label": f"── {d.category} ──", "value": f"__sep{i}",
                         "disabled": True})
        opts.append({"label": f"{d.code}  –  {d.name}", "value": d.code})
    return opts


def _atributo_options() -> list[dict]:
    from app.services import strategy_filter as sf

    etiquetas = {
        "sector": "Sector", "market": "Mercado", "industry": "Industria",
        "country": "País", "instrument_type": "Tipo de instrumento",
        "currency": "Moneda", "benchmark": "Benchmark",
        "synthetic": "Tipo de sintético",
    }
    return [{"label": etiquetas.get(k, k), "value": k}
            for k in sorted(sf.ATTRIBUTE_KEYS)]


def layout(**kwargs):
    from flask_login import current_user
    if not current_user.is_authenticated:
        return html.Div()

    return html.Div([
        dcc.Store(id="cal-datos"),

        dbc.Row([
            dbc.Col(page_header("Calibración de señales",
                                "calibracion-de-senales", className="mb-0"),
                    width="auto"),
        ], className="mb-2 align-items-center"),

        dbc.Card(dbc.CardBody([
            dbc.Row([
                dbc.Col([
                    html.Small("Indicador", className="text-muted d-block mb-1"),
                    dcc.Dropdown(id="cal-indicador", options=_indicator_options(),
                                 placeholder="Seleccionar…", clearable=False,
                                 searchable=True, style={"fontSize": "0.85rem"}),
                ], md=4),
                dbc.Col([
                    html.Small("Fechas (una por línea o separadas por coma)",
                               className="text-muted d-block mb-1"),
                    dbc.Input(id="cal-fechas", type="text",
                              placeholder="vacío = última fecha con precios",
                              style=_INPUT_SM),
                ], md=4),
                dbc.Col([
                    html.Small("Agrupar por", className="text-muted d-block mb-1"),
                    dcc.Dropdown(id="cal-agrupar", options=_atributo_options(),
                                 placeholder="(sin agrupar)", clearable=True,
                                 style={"fontSize": "0.85rem"}),
                ], md=2),
                dbc.Col([
                    dbc.Button("Analizar", id="cal-btn", color="primary",
                               size="sm", className="w-100"),
                ], md=2, className="d-flex align-items-end"),
            ], className="g-2 align-items-end"),

            html.Hr(className="my-2"),

            dbc.Row([
                dbc.Col([
                    html.Small("Escala tentativa — min", className="text-muted d-block mb-1"),
                    dbc.Input(id="cal-min", type="number", style=_INPUT_SM),
                ], width="auto"),
                dbc.Col([
                    html.Small("max", className="text-muted d-block mb-1"),
                    dbc.Input(id="cal-max", type="number", style=_INPUT_SM),
                ], width="auto"),
                dbc.Col([
                    dbc.Button("Traer la de la señal", id="cal-btn-cargar",
                               color="secondary", size="sm", outline=True),
                ], width="auto", className="d-flex align-items-end"),
                dbc.Col([
                    dbc.Button("Llevar al editor →", id="cal-btn-editor",
                               color="link", size="sm"),
                ], width="auto", className="d-flex align-items-end"),
                dbc.Col(html.Small(
                    "min puede ser mayor que max: así se invierte una señal.",
                    className="text-muted", style={"fontSize": "0.75rem"}),
                    className="d-flex align-items-end"),
            ], className="g-2"),
        ]), className="mb-3", style=CARD_STYLE),

        dbc.Alert(id="cal-aviso", is_open=False, color="warning",
                  className="py-2 small"),

        html.Div(id="cal-resumen", className="mb-2",
                 style={"fontSize": "0.82rem", "color": TEXT_BODY}),

        dcc.Loading([
            dbc.Row([
                dbc.Col(dcc.Graph(id="cal-graf-indicador",
                                  config={"displayModeBar": False},
                                  style={"height": "380px"}), md=7),
                dbc.Col(dcc.Graph(id="cal-graf-scores",
                                  config={"displayModeBar": False},
                                  style={"height": "380px"}), md=5),
            ], className="g-2"),
        ], type="circle", color=TEXT_BODY),

        html.Small("Percentiles y saturación por fecha",
                   className="d-block mt-3 mb-1", style={"color": TEXT_MUTED}),
        dag.AgGrid(
            id="cal-tabla-fechas",
            columnDefs=to_column_defs([
                {"name": "Fecha",       "id": "fecha",     "width": 130},
                {"name": "Con dato",    "id": "n",         "width": 100},
                {"name": "Cobertura %", "id": "cobertura", "width": 120},
                {"name": "p5",  "id": "p5",  "width": 100},
                {"name": "p25", "id": "p25", "width": 100},
                {"name": "p50", "id": "p50", "width": 100},
                {"name": "p75", "id": "p75", "width": 100},
                {"name": "p95", "id": "p95", "width": 100},
                {"name": "Satura %",    "id": "satura",    "width": 110},
                {"name": "— abajo",     "id": "sat_abajo", "width": 110},
                {"name": "— arriba",    "id": "sat_arriba", "width": 110},
            ]),
            rowData=[],
            className=THEME_CLASS,
            style={"height": "180px", "width": "100%"},
            defaultColDef=DEFAULT_COL_DEF,
            dashGridOptions=grid_options(),
        ),

        html.Div(id="cal-bloque-grupos", children=[
            html.Small("Por grupo", className="d-block mt-3 mb-1",
                       style={"color": TEXT_MUTED}),
            dag.AgGrid(
                id="cal-tabla-grupos",
                columnDefs=to_column_defs([
                    {"name": "Grupo",       "id": "grupo",     "width": 220},
                    {"name": "Activos",     "id": "activos",   "width": 110},
                    {"name": "Con dato",    "id": "n",         "width": 110},
                    {"name": "Cobertura %", "id": "cobertura", "width": 120},
                    {"name": "p25", "id": "p25", "width": 110},
                    {"name": "p50", "id": "p50", "width": 110},
                    {"name": "p75", "id": "p75", "width": 110},
                    {"name": "Satura %", "id": "satura", "width": 110},
                ]),
                rowData=[],
                className=THEME_CLASS,
                style={"height": "260px", "width": "100%"},
                defaultColDef=DEFAULT_COL_DEF,
                dashGridOptions=grid_options(),
            ),
        ], style={"display": "none"}),

        html.Small(
            "Nada de esto se guarda. El número se escribe en la pantalla de "
            "Señales, que es el único lugar donde se define una señal.",
            className="d-block mt-3", style={"color": COLOR_INFO,
                                             "fontSize": "0.78rem"}),

    ], style={"padding": "0 8px"})


dash.register_page(__name__, path="/admin/calibracion",
                   title="Calibración de señales", layout=layout)
