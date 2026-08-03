import dash
import dash_ag_grid as dag
from dash import html

from app.components.grids import DEFAULT_COL_DEF, THEME_CLASS, grid_options
from app.components.help import page_header
from app.components.ui_constants import COLOR_NEUTRAL, COLOR_WARNING


def layout(**kwargs):
    from flask_login import current_user
    if not current_user.is_authenticated or not current_user.is_admin:
        return html.Div("Acceso denegado", className="text-danger mt-4")

    from app.database import get_session
    from app.models.indicator_definition import IndicatorDefinition

    s = get_session()
    defs = s.query(IndicatorDefinition).order_by(
        IndicatorDefinition.category, IndicatorDefinition.code
    ).all()

    data = [
        {
            "code":         d.code,
            "name":         d.name,
            "category":     d.category,
            "type":         d.type,
            "scale":        d.scale or "—",
            "keep_history": "Sí" if d.keep_history else "No",
            "description":  d.description or "—",
        }
        for d in defs
    ]

    return html.Div([
        page_header("Indicadores del Sistema", "configuracion-indicadores", className="mb-1"),
        html.P(
            "Indicadores técnicos disponibles como input para las señales. "
            "Se calculan automáticamente a partir del historial de precios.",
            className="text-muted mb-3",
            style={"fontSize": "0.83rem"},
        ),
        dag.AgGrid(
            columnDefs=[
                {"field": "code", "headerName": "Código", "width": 190,
                 "cellStyle": {"fontFamily": "monospace", "color": COLOR_NEUTRAL}},
                {"field": "name", "headerName": "Nombre", "width": 230},
                {"field": "category", "headerName": "Categoría", "width": 170},
                {"field": "type", "headerName": "Tipo", "width": 90},
                {"field": "scale", "headerName": "Escala", "width": 120},
                # El ámbar avisa que ese indicador NO guarda histórico: se ve
                # solo el valor vigente, no la serie.
                {"field": "keep_history", "headerName": "Guarda histórico", "width": 150,
                 "cellStyle": {"styleConditions": [
                     {"condition": "params.value == 'No'",
                      "style": {"color": COLOR_WARNING}}]}},
                {"field": "description", "headerName": "Descripción", "flex": 1,
                 "minWidth": 300, "wrapText": True, "autoHeight": True},
            ],
            rowData=data,
            className=THEME_CLASS,
            style={"height": "calc(100vh - 300px)", "width": "100%"},
            defaultColDef=DEFAULT_COL_DEF,
            dashGridOptions=grid_options(),
        ),
    ])


dash.register_page(__name__, path="/admin/indicators", title="Indicadores del sistema", layout=layout)
