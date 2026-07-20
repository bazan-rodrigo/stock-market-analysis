import dash
import dash_bootstrap_components as dbc
from dash import dcc, html

from app.components.help import help_link


def layout(**kwargs):
    from flask_login import current_user
    if not current_user.is_authenticated or not current_user.is_admin:
        return html.Div()

    return html.Div([
        dcc.Interval(id="scheduler-interval", interval=10_000, n_intervals=0),

        html.H4(["Scheduler de precios ", help_link("scheduler")], className="mb-4"),

        dbc.Alert(id="scheduler-alert", is_open=False, dismissable=True, className="mb-3"),

        dbc.Row([
            # Estado
            dbc.Col(dbc.Card(dbc.CardBody([
                html.Div("Estado", className="text-muted small mb-1"),
                html.Div(id="scheduler-status-badge"),
                html.Div([
                    html.Span("Próxima ejecución: ", className="text-muted small"),
                    html.Span(id="scheduler-next-run", className="small"),
                ], className="mt-2"),
                html.Div([
                    html.Span("Horario configurado: ", className="text-muted small"),
                    html.Span(id="scheduler-current-time", className="small"),
                ], className="mt-1"),
            ])), md=4, className="mb-3"),

            # Controles
            dbc.Col(dbc.Card(dbc.CardBody([
                html.Div("Controles", className="text-muted small mb-2"),
                dbc.ButtonGroup([
                    dbc.Button("Iniciar", id="scheduler-btn-start",
                               color="success", size="sm"),
                    dbc.Button("Detener", id="scheduler-btn-stop",
                               color="danger", size="sm"),
                    dbc.Button("Ejecutar ahora", id="scheduler-btn-run-now",
                               color="warning", size="sm"),
                ], className="d-flex flex-wrap gap-2"),
            ])), md=4, className="mb-3"),

            # Configurar horario
            dbc.Col(dbc.Card(dbc.CardBody([
                html.Div("Cambiar horario (UTC)", className="text-muted small mb-2"),
                dbc.Row([
                    dbc.Col([
                        dbc.Label("Hora", className="small mb-0"),
                        dbc.Input(id="scheduler-input-hour", type="number",
                                  min=0, max=23, step=1,
                                  placeholder="0–23", size="sm"),
                    ]),
                    dbc.Col([
                        dbc.Label("Minuto", className="small mb-0"),
                        dbc.Input(id="scheduler-input-minute", type="number",
                                  min=0, max=59, step=1,
                                  placeholder="0–59", size="sm"),
                    ]),
                    dbc.Col([
                        dbc.Label("\u00a0", className="small d-block"),
                        dbc.Button("Aplicar", id="scheduler-btn-apply",
                                   color="primary", size="sm"),
                    ], width="auto"),
                ], className="g-2 align-items-end"),
            ])), md=4, className="mb-3"),
        ]),

        html.H4("Verificaci\u00f3n semanal de datos", className="mb-3 mt-4"),
        html.P(
            "Recalcula indicadores + fundamentales de TODOS los activos y "
            "actualiza asset_verification_flag (\u26a0\ufe0f en los selectores de "
            "An\u00e1lisis de Activo, RRG, Evoluci\u00f3n, Pares y Retornos). Job "
            "independiente del de arriba \u2014 nace deshabilitado.",
            className="text-muted small mb-3",
        ),

        dbc.Alert(id="weekly-verify-alert", is_open=False, dismissable=True, className="mb-3"),

        dbc.Row([
            # Estado
            dbc.Col(dbc.Card(dbc.CardBody([
                html.Div("Estado", className="text-muted small mb-1"),
                html.Div(id="weekly-verify-status-badge"),
                html.Div([
                    html.Span("Pr\u00f3xima ejecuci\u00f3n: ", className="text-muted small"),
                    html.Span(id="weekly-verify-next-run", className="small"),
                ], className="mt-2"),
                html.Div([
                    html.Span("Horario configurado: ", className="text-muted small"),
                    html.Span(id="weekly-verify-current-time", className="small"),
                ], className="mt-1"),
            ])), md=4, className="mb-3"),

            # Controles
            dbc.Col(dbc.Card(dbc.CardBody([
                html.Div("Controles", className="text-muted small mb-2"),
                dbc.ButtonGroup([
                    dbc.Button("Habilitar", id="weekly-verify-btn-enable",
                               color="success", size="sm"),
                    dbc.Button("Deshabilitar", id="weekly-verify-btn-disable",
                               color="danger", size="sm"),
                    dbc.Button("Ejecutar ahora", id="weekly-verify-btn-run-now",
                               color="warning", size="sm"),
                ], className="d-flex flex-wrap gap-2"),
            ])), md=4, className="mb-3"),

            # Configurar horario
            dbc.Col(dbc.Card(dbc.CardBody([
                html.Div("Cambiar horario (UTC)", className="text-muted small mb-2"),
                dbc.Row([
                    dbc.Col([
                        dbc.Label("D\u00eda", className="small mb-0"),
                        dcc.Dropdown(
                            id="weekly-verify-input-day",
                            options=[
                                {"label": "Lunes", "value": "mon"},
                                {"label": "Martes", "value": "tue"},
                                {"label": "Mi\u00e9rcoles", "value": "wed"},
                                {"label": "Jueves", "value": "thu"},
                                {"label": "Viernes", "value": "fri"},
                                {"label": "S\u00e1bado", "value": "sat"},
                                {"label": "Domingo", "value": "sun"},
                            ],
                            clearable=False, style={"fontSize": "0.85rem"},
                        ),
                    ], width=4),
                    dbc.Col([
                        dbc.Label("Hora", className="small mb-0"),
                        dbc.Input(id="weekly-verify-input-hour", type="number",
                                  min=0, max=23, step=1,
                                  placeholder="0\u201323", size="sm"),
                    ]),
                    dbc.Col([
                        dbc.Label("Minuto", className="small mb-0"),
                        dbc.Input(id="weekly-verify-input-minute", type="number",
                                  min=0, max=59, step=1,
                                  placeholder="0\u201359", size="sm"),
                    ]),
                ], className="g-2 mb-2"),
                dbc.Button("Aplicar", id="weekly-verify-btn-apply",
                          color="primary", size="sm"),
            ])), md=4, className="mb-3"),
        ]),
    ], style={"padding": "0 8px"})


dash.register_page(__name__, path="/admin/scheduler",
                   title="Scheduler de precios", layout=layout)
