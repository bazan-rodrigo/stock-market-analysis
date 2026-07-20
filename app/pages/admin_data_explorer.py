import dash
import dash_bootstrap_components as dbc
from dash import dcc, html

from app.components.help import help_link

from app.services.data_explorer_service import DATASETS

# group_type → getter del catálogo de grupos (los 5 tipos del sistema)
GROUP_TYPE_OPTS = [
    {"label": "Sector",            "value": "sector"},
    {"label": "Mercado",           "value": "market"},
    {"label": "Industria",         "value": "industry"},
    {"label": "País",              "value": "country"},
    {"label": "Tipo de instrumento", "value": "instrument_type"},
]

_DATASET_OPTS = [{"label": v["label"], "value": k} for k, v in DATASETS.items()]


def _combo(wrap_id, label, dropdown):
    return dbc.Col(html.Div([
        dbc.Label(label, style={"fontSize": "0.78rem", "marginBottom": "2px"}),
        dropdown,
    ], id=wrap_id, style={"display": "none"}), width="auto")


def layout(**kwargs):
    from flask_login import current_user
    if not current_user.is_authenticated or not current_user.is_admin:
        return html.Div()

    # Opciones estáticas (se consultan al abrir la página, como el resto de las
    # pantallas admin que pueblan combos en layout)
    from app.services.asset_service import get_assets
    from app.services.signal_service import get_all_signals
    from app.services.strategy_service import get_all_strategies
    from app.database import get_session
    from app.models.indicator_definition import IndicatorDefinition

    s = get_session()
    asset_opts = [{"label": f"{a.ticker} — {a.name}", "value": a.id}
                  for a in get_assets()]
    # Solo indicadores con historia: son los que tienen tabla ind_{code}
    ind_defs = (s.query(IndicatorDefinition.code, IndicatorDefinition.name)
                .filter(IndicatorDefinition.keep_history.is_(True))
                .order_by(IndicatorDefinition.name).all())
    indicator_opts = [{"label": f"{name} ({code})", "value": code}
                      for code, name in ind_defs]
    signal_opts = [{"label": f"{sig.key} — {sig.name}", "value": sig.id}
                   for sig in get_all_signals()]
    strategy_opts = [{"label": st.name, "value": st.id}
                     for st in get_all_strategies()]

    _ddstyle = {"fontSize": "0.8rem", "minWidth": "220px"}

    return html.Div([
        dcc.Store(id="de-data-store"),   # {columns, records, table} para el CSV
        dcc.Download(id="de-download"),

        html.H5(["Explorador de datos ", help_link("explorador-de-datos")], className="mb-1"),
        html.Small(
            "Lectura cruda de las tablas internas (indicadores, fundamentales, "
            "señales, scores). Solo lectura — para inspección sin SQL.",
            className="text-muted d-block mb-3"),

        dbc.Row([
            dbc.Col(html.Div([
                dbc.Label("Conjunto de datos",
                          style={"fontSize": "0.78rem", "marginBottom": "2px"}),
                dcc.Dropdown(id="de-dataset", options=_DATASET_OPTS,
                             placeholder="Elegí qué ver...", clearable=False,
                             style={"fontSize": "0.8rem", "minWidth": "260px"}),
            ]), width="auto"),

            _combo("de-wrap-indicator", "Indicador",
                   dcc.Dropdown(id="de-indicator", options=indicator_opts,
                                placeholder="Indicador...", style=_ddstyle,
                                searchable=True)),
            _combo("de-wrap-signal", "Señal",
                   dcc.Dropdown(id="de-signal", options=signal_opts,
                                placeholder="Señal...", style=_ddstyle,
                                searchable=True)),
            _combo("de-wrap-strategy", "Estrategia",
                   dcc.Dropdown(id="de-strategy", options=strategy_opts,
                                placeholder="Estrategia...", style=_ddstyle,
                                searchable=True)),
            _combo("de-wrap-group-type", "Tipo de grupo",
                   dcc.Dropdown(id="de-group-type", options=GROUP_TYPE_OPTS,
                                placeholder="Tipo...", style=_ddstyle)),
            _combo("de-wrap-group", "Grupo",
                   dcc.Dropdown(id="de-group", options=[],
                                placeholder="Grupo...", style=_ddstyle,
                                searchable=True)),
            _combo("de-wrap-asset", "Activo",
                   dcc.Dropdown(id="de-asset", options=asset_opts,
                                placeholder="Activo...", style=_ddstyle,
                                searchable=True)),
        ], className="g-2 align-items-end mb-3"),

        dbc.Row([
            dbc.Col(html.Span(id="de-result-info", className="text-muted",
                              style={"fontSize": "0.82rem",
                                     "fontFamily": "monospace"}),
                    className="d-flex align-items-center"),
            dbc.Col(dbc.Button("Exportar CSV", id="de-btn-export",
                               color="secondary", size="sm", outline=True,
                               disabled=True),
                    width="auto"),
        ], className="mb-2 g-2 align-items-center"),

        dcc.Loading(html.Div(id="de-result-container"),
                    type="circle", color="#dee2e6"),

    ], style={"padding": "0 8px"})


dash.register_page(__name__, path="/admin/data-explorer",
                   title="Explorador de datos", layout=layout)
