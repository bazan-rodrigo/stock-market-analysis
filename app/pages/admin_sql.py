import dash
import dash_bootstrap_components as dbc
from dash import dcc, html

# Consulta inicial: monitor de queries en ejecución (útil para diagnosticar
# qué está corriendo contra la base en este momento)
_DEFAULT_QUERY = """\
SELECT id, user, db, time, state, info, command
FROM information_schema.processlist
WHERE info not like '%information_schema%'
ORDER BY time DESC;"""


def layout(**kwargs):
    from flask_login import current_user
    if not current_user.is_authenticated or not current_user.is_admin:
        return html.Div()

    return html.Div([
        dcc.Store(id="sql-session-id"),
        dcc.Download(id="sql-download"),

        html.H5("Consola SQL", className="mb-3"),

        # ── Editor ───────────────────────────────────────────────────────────
        dbc.Textarea(
            id="sql-input",
            value=_DEFAULT_QUERY,
            placeholder="SELECT * FROM assets LIMIT 10;",
            style={"fontFamily": "monospace", "minHeight": "160px"},
            className="mb-2",
        ),

        # ── Botones ───────────────────────────────────────────────────────────
        dbc.Row([
            dbc.Col([
                dbc.Button("Ejecutar",  id="sql-btn-exec",     color="primary",        size="sm", className="me-2"),
                dbc.Button("Commit",    id="sql-btn-commit",   color="success",        size="sm", className="me-2", disabled=True),
                dbc.Button("Rollback",  id="sql-btn-rollback", color="warning",        size="sm", className="me-2", disabled=True),
                dbc.Button("Exportar CSV", id="sql-btn-export", color="secondary",     size="sm", disabled=True),
            ], width="auto"),
            dbc.Col([
                html.Span(id="sql-status", className="text-muted",
                          style={"fontSize": "0.82rem", "fontFamily": "monospace"}),
            ], className="d-flex align-items-center"),
        ], className="mb-3 g-2"),

        # ── Resultado ─────────────────────────────────────────────────────────
        html.Div(id="sql-result-container"),

    ], style={"padding": "0 8px"})


dash.register_page(__name__, path="/admin/sql", title="Consola SQL", layout=layout)
