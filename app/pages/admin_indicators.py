import dash
from dash import dash_table, html

from app.components.help import help_link

from app.components.table_styles import CELL, DATA, FILTER, HEADER


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
        html.H3(["Indicadores del Sistema ", help_link("configuracion-indicadores")], className="mb-1"),
        html.P(
            "Indicadores técnicos disponibles como input para las señales. "
            "Se calculan automáticamente a partir del historial de precios "
            "y se almacenan en indicator_values.",
            className="text-muted mb-3",
            style={"fontSize": "0.83rem"},
        ),
        dash_table.DataTable(
            columns=[
                {"name": "Código",        "id": "code"},
                {"name": "Nombre",        "id": "name"},
                {"name": "Categoría",     "id": "category"},
                {"name": "Tipo",          "id": "type"},
                {"name": "Escala",        "id": "scale"},
                {"name": "Guarda histórico", "id": "keep_history"},
                {"name": "Descripción",   "id": "description"},
            ],
            data=data,
            style_table={"overflowX": "auto"},
            style_header=HEADER,
            style_data=DATA,
            style_cell={**CELL, "whiteSpace": "normal", "height": "auto"},
            style_filter=FILTER,
            style_cell_conditional=[
                {"if": {"column_id": "code"},        "fontFamily": "monospace",
                 "color": "#94a3b8", "width": "180px", "minWidth": "180px"},
                {"if": {"column_id": "category"},    "width": "160px", "minWidth": "160px"},
                {"if": {"column_id": "type"},        "width": "60px",  "minWidth": "60px"},
                {"if": {"column_id": "scale"},       "width": "110px", "minWidth": "110px"},
                {"if": {"column_id": "keep_history"}, "width": "110px", "minWidth": "110px"},
                {"if": {"column_id": "description"}, "minWidth": "300px"},
            ],
            style_data_conditional=[
                {"if": {"filter_query": '{keep_history} = "No"', "column_id": "keep_history"},
                 "color": "#f59e0b"},
            ],
            page_size=35,
            filter_action="native",
            sort_action="native",
        ),
    ])


dash.register_page(__name__, path="/admin/indicators", title="Indicadores del sistema", layout=layout)
