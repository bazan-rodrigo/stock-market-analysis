import dash
import dash_ag_grid as dag
import dash_bootstrap_components as dbc
from dash import dcc, html

from app.components.grids import DEFAULT_COL_DEF, THEME_CLASS, grid_options
from app.components.help import page_header

from app.components.ui_constants import (
    CARD_STYLE, COLOR_NEUTRAL, TEXT_BODY
)

# Tope de filas traídas del servidor. La grilla virtualiza (dibuja solo lo
# visible), así que el tope ya no es para que el navegador no se trabe
# dibujando: es para no mandar un catálogo entero por la red ni cargarlo en
# memoria del cliente. El corte es por score, o sea por el ranking mismo.
_LIMIT_OPTS = [
    {"label": "Top 100",   "value": 100},
    {"label": "Top 500",   "value": 500},
    {"label": "Top 1000",  "value": 1000},
    {"label": "Top 2000",  "value": 2000},
    {"label": "Todos",     "value": 0},
]
_DEFAULT_LIMIT = 500


def layout(**kwargs):
    from flask_login import current_user
    if not current_user.is_authenticated:
        return html.Div()

    return html.Div([
        dcc.Store(id="ss-comp-meta",    data=[]),
        dcc.Store(id="ss-results-store", data=None),
        dcc.Store(id="ss-query-store",   data=None),
        dcc.Download(id="ss-download"),

        dbc.Row([
            dbc.Col(page_header("Screener de Señales", "screener-de-senales", className="mb-0"), width="auto"),
        ], className="mb-3 align-items-center"),

        # ── Filtros ──────────────────────────────────────────────────────────
        dbc.Card(dbc.CardBody([
            dbc.Row([
                dbc.Col([
                    dbc.Label("Estrategia", style={"fontSize": "0.82rem"}),
                    dcc.Dropdown(id="ss-strategy-sel",
                                 placeholder="Seleccionar estrategia...",
                                 style={"fontSize": "0.85rem"}),
                ], md=4),
                dbc.Col([
                    dbc.Label("Fecha", style={"fontSize": "0.82rem"}),
                    dcc.DatePickerSingle(id="ss-date",
                                        display_format="YYYY-MM-DD",
                                        style={"fontSize": "0.82rem"}),
                ], md=2, className="d-flex flex-column"),
                dbc.Col([
                    dbc.Label("Sector", style={"fontSize": "0.82rem"}),
                    dcc.Dropdown(id="ss-sector-filter", placeholder="Todos",
                                 style={"fontSize": "0.85rem"}),
                ], md=2),
                dbc.Col([
                    dbc.Label("Mercado", style={"fontSize": "0.82rem"}),
                    dcc.Dropdown(id="ss-market-filter", placeholder="Todos",
                                 style={"fontSize": "0.85rem"}),
                ], md=2),
                dbc.Col([
                    dbc.Label(" ", style={"fontSize": "0.82rem"}),
                    dbc.Button("Buscar", id="ss-btn-search", color="primary",
                               size="sm", style={"display": "block"}),
                ], md=1, className="d-flex flex-column"),
                dbc.Col([
                    dbc.Label(" ", style={"fontSize": "0.82rem"}),
                    dcc.Loading(
                        html.Div(id="ss-result-count",
                                 style={"fontSize": "0.80rem", "color": COLOR_NEUTRAL,
                                        "paddingTop": "6px"}),
                        type="circle", color=TEXT_BODY,
                    ),
                ], md=1),
            ], className="g-2 mb-2"),

            # ── Segunda fila: tope + exportar ────────────────────────────────
            # El "Ordenar por" se fue con la migración a grilla: ahora se ordena
            # clickeando cualquier cabecera, incluidas las columnas de señal
            # (que antes no se podían ordenar de ninguna manera).
            dbc.Row([
                dbc.Col(html.Div([
                    dbc.Label("Mostrar", style={"fontSize": "0.82rem"}),
                    dcc.Dropdown(id="ss-limit", options=_LIMIT_OPTS,
                                 value=_DEFAULT_LIMIT, clearable=False,
                                 style={"fontSize": "0.83rem"}),
                ], title="Cuántos activos del ranking se traen. Ordenar la "
                         "grilla reordena solo los traídos."), md=2),
                dbc.Col([
                    dbc.Label(" ", style={"fontSize": "0.82rem"}),
                    dbc.Button("Exportar Excel", id="ss-btn-export", color="secondary",
                               size="sm", outline=True, disabled=True,
                               style={"display": "block"},
                               title="Exporta el ranking completo, sin el tope de filas."),
                ], md=2, className="d-flex flex-column"),
            ], className="g-2"),
        ]), className="mb-3",
            style=CARD_STYLE),

        dag.AgGrid(
            id="ss-grid",
            columnDefs=[],
            rowData=[],
            className=THEME_CLASS,
            style={"height": "calc(100vh - 260px)", "width": "100%"},
            defaultColDef=DEFAULT_COL_DEF,
            # Sin paginación: la grilla virtualiza y el ranking se recorre
            # scrolleando. Las filas van más compactas que el default para que
            # entren más activos en pantalla, como en la tabla anterior.
            dashGridOptions=grid_options(rowHeight=28),
        ),

    ], style={"padding": "0 8px"})


dash.register_page(__name__, path="/senales",
                   title="Screener de Señales", layout=layout)
