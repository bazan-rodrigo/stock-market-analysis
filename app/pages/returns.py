import dash
import dash_bootstrap_components as dbc
from dash import dcc, html

from app.components.help import help_link

_BG = "#111827"

# Los textos dicen días CORRIDOS porque es lo que resta el cálculo
# (returns_service._range). Decían "5 días hábiles" / "~21 días hábiles":
# aproximaban bien el efecto, pero prometían un conteo de ruedas que el
# código no hace — y con feriados largos la ventana efectiva se corre.
_PERIODS = [
    ("1D",  "Retorno desde el cierre anterior"),
    ("1S",  "Retorno de los últimos 7 días corridos"),
    ("1M",  "Retorno de los últimos 30 días corridos"),
    ("3M",  "Retorno de los últimos 91 días corridos"),
    ("6M",  "Retorno de los últimos 182 días corridos"),
    ("YTD", "Desde el 1° de enero hasta hoy"),
    ("1A",  "Retorno de los últimos 365 días corridos"),
    ("rng", "Rango personalizado"),
]

_MODES = [
    ("individual", "Individual"),
    ("grupo",      "Grupo"),
    ("benchmark",  "Benchmark"),
    ("sintetico",  "Sintético"),
]

_DIMS = [
    ("sector",   "Sector"),
    ("industry", "Industria"),
    ("country",  "País"),
    ("market",   "Mercado"),
    ("itype",    "Tipo de Instrumento"),
]


def _radio(rid, opts, value, **kwargs):
    return dbc.RadioItems(
        id=rid,
        options=opts,
        value=value,
        input_class_name="btn-check",
        label_class_name="btn btn-outline-secondary btn-sm",
        label_checked_class_name="active",
        class_name="btn-group btn-group-sm",
        **kwargs,
    )


def layout(**kwargs):
    from flask_login import current_user
    if not current_user.is_authenticated:
        return html.Div()

    period_opts = [
        {"label": html.Span(val, id=f"rp-lbl-{val}"), "value": val}
        for val, _ in _PERIODS
    ]
    period_tooltips = [
        dbc.Tooltip(tip, target=f"rp-lbl-{val}", placement="top")
        for val, tip in _PERIODS
    ]
    mode_opts = [{"label": lbl, "value": val} for val, lbl in _MODES]
    dim_opts  = [{"label": lbl, "value": val} for val, lbl in _DIMS]

    _card = {"backgroundColor": "#1f2937", "border": "1px solid #374151", "borderRadius": "8px"}
    _sel  = {"backgroundColor": "#2c2c2c", "color": "#dee2e6", "borderColor": "#555",
              "fontSize": "0.82rem"}

    return html.Div([
        dbc.Row([
            dbc.Col(html.H4(["Comparador de Retornos ", help_link("comparador-de-retornos")], className="mb-0"), width="auto"),
            dbc.Col(
                html.Small("Comparación de retorno porcentual para un lapso de tiempo.",
                           className="text-muted", style={"fontSize": "0.75rem"}),
                className="d-flex align-items-center",
            ),
        ], className="mb-3 align-items-center"),

        # ── Período ──────────────────────────────────────────────────────────
        dbc.Card(dbc.CardBody([
            html.Div("Período", className="text-muted mb-2",
                     style={"fontSize": "0.72rem", "textTransform": "uppercase",
                            "letterSpacing": "0.05em"}),
            dbc.Row([
                dbc.Col(
                    html.Div(_radio("ret-period", period_opts, "1M"),
                             className="ind-group", style={"padding": "1px 2px"}),
                    width="auto",
                ),
                dbc.Col(
                    html.Div([
                        dcc.DatePickerSingle(
                            id="ret-date-from",
                            display_format="DD/MM/YYYY",
                            placeholder="Desde",
                            style={"fontSize": "0.8rem"},
                        ),
                        html.Span("→", className="mx-2 text-muted"),
                        dcc.DatePickerSingle(
                            id="ret-date-to",
                            display_format="DD/MM/YYYY",
                            placeholder="Hasta",
                            style={"fontSize": "0.8rem"},
                        ),
                    ], id="ret-custom-dates", style={"display": "none"},
                       className="d-flex align-items-center"),
                    width="auto",
                ),
            ], className="g-2 align-items-center flex-wrap"),
            *period_tooltips,
        ]), style=_card, className="mb-2"),

        # ── Activos ──────────────────────────────────────────────────────────
        dbc.Card(dbc.CardBody([
            html.Div("Activos", className="text-muted mb-2",
                     style={"fontSize": "0.72rem", "textTransform": "uppercase",
                            "letterSpacing": "0.05em"}),
            dbc.Row([
                dbc.Col(
                    html.Div(_radio("ret-mode", mode_opts, "individual"),
                             className="ind-group", style={"padding": "1px 2px"}),
                    width="auto",
                ),
            ], className="g-2 mb-2"),

            # Individual
            html.Div([
                dcc.Dropdown(
                    id="ret-individual",
                    options=[], multi=True, searchable=True,
                    placeholder="Buscar activos...",
                    style=_sel,
                ),
            ], id="ret-panel-individual"),

            # Grupo
            html.Div([
                dbc.Row([
                    dbc.Col(
                        dcc.Dropdown(
                            id="ret-group-dim",
                            options=dim_opts,
                            value="sector",
                            clearable=False,
                            style=_sel,
                        ),
                        width=3,
                    ),
                    dbc.Col(
                        dcc.Dropdown(
                            id="ret-group-val",
                            options=[], placeholder="Seleccioná un valor...",
                            style=_sel,
                        ),
                        width=5,
                    ),
                ], className="g-2"),
            ], id="ret-panel-grupo", style={"display": "none"}),

            # Benchmark
            html.Div([
                dcc.Dropdown(
                    id="ret-benchmark",
                    options=[], multi=True,
                    placeholder="Seleccioná benchmark(s)...",
                    style=_sel,
                ),
            ], id="ret-panel-benchmark", style={"display": "none"}),

            # Sintético
            html.Div([
                dcc.Dropdown(
                    id="ret-sintetico",
                    options=[], multi=True,
                    placeholder="Seleccioná sintético(s)...",
                    style=_sel,
                ),
            ], id="ret-panel-sintetico", style={"display": "none"}),

        ]), style=_card, className="mb-2"),

        # ── Botón ────────────────────────────────────────────────────────────
        dbc.Row([
            dbc.Col(
                dbc.Button("Calcular retornos", id="ret-btn-calc",
                           color="primary", size="sm", className="px-4"),
                width="auto",
            ),
        ], className="mb-3"),

        dbc.Alert(id="ret-alert", is_open=False, dismissable=True, className="mb-2"),

        # ── Gráfico ──────────────────────────────────────────────────────────
        dcc.Loading(
            dcc.Graph(
                id="ret-chart",
                config={"displayModeBar": False},
                style={"height": "420px", "display": "none"},
            ),
            type="circle",
            color="#dee2e6",
        ),

    ], style={"padding": "0 8px"})


dash.register_page(__name__, path="/retornos", title="Comparador de Retornos", layout=layout)
