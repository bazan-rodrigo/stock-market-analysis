import dash
import dash_bootstrap_components as dbc
from dash import dcc, html


def layout(**kwargs):
    from flask_login import current_user
    if not current_user.is_authenticated or not current_user.is_admin:
        return html.Div()

    return html.Div([
        dcc.Interval(id="scheduler-interval", interval=10_000, n_intervals=0),

        html.H4("Scheduler de precios", className="mb-4"),

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
    ], style={"padding": "0 8px"})


dash.register_page(__name__, path="/admin/scheduler",
                   title="Scheduler de precios", layout=layout)
