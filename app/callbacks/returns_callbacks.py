import plotly.graph_objects as go
from dash import Input, Output, State, callback, no_update
from flask_login import current_user

import app.services.reference_service as ref_svc
import app.services.returns_service as svc
from app.services.asset_service import get_assets
from app.services.evolution_service import (
    get_benchmark_assets_options,
    get_synthetic_assets_options,
)

_BG = "#111827"


# ── Poblar dropdowns al cargar ────────────────────────────────────────────────

@callback(
    Output("ret-individual", "options"),
    Output("ret-benchmark",  "options"),
    Output("ret-sintetico",  "options"),
    Input("ret-individual",  "id"),
)
def load_options(_):
    assets = get_assets()
    return (
        [{"label": f"{a.ticker} — {a.name}", "value": a.id} for a in assets],
        get_benchmark_assets_options(),
        get_synthetic_assets_options(),
    )


# ── Mostrar/ocultar DatePickers personalizados ────────────────────────────────

@callback(
    Output("ret-custom-dates", "style"),
    Input("ret-period", "value"),
)
def toggle_custom_dates(period):
    show = {"display": "flex", "alignItems": "center"}
    hide = {"display": "none"}
    return show if period == "rng" else hide


# ── Cambiar panel de activos según modo ───────────────────────────────────────

@callback(
    Output("ret-panel-individual", "style"),
    Output("ret-panel-grupo",      "style"),
    Output("ret-panel-benchmark",  "style"),
    Output("ret-panel-sintetico",  "style"),
    Input("ret-mode", "value"),
)
def switch_panel(mode):
    show, hide = {}, {"display": "none"}
    return (
        show if mode == "individual" else hide,
        show if mode == "grupo"      else hide,
        show if mode == "benchmark"  else hide,
        show if mode == "sintetico"  else hide,
    )


# ── Poblar valores de grupo según dimensión ───────────────────────────────────

@callback(
    Output("ret-group-val", "options"),
    Output("ret-group-val", "value"),
    Input("ret-group-dim",  "value"),
)
def load_group_values(dim):
    if not dim:
        return [], None
    _LOADERS = {
        "sector":   lambda: [{"label": x.name, "value": x.id} for x in ref_svc.get_sectors()],
        "industry": lambda: [{"label": x.name, "value": x.id} for x in ref_svc.get_industries()],
        "country":  lambda: [{"label": x.name, "value": x.id} for x in ref_svc.get_countries()],
        "market":   lambda: [{"label": x.name, "value": x.id} for x in ref_svc.get_markets()],
        "itype":    lambda: [{"label": x.name, "value": x.id} for x in ref_svc.get_instrument_types()],
    }
    opts = _LOADERS.get(dim, lambda: [])()
    return opts, None


# ── Calcular y renderizar el gráfico ─────────────────────────────────────────

@callback(
    Output("ret-chart",  "figure"),
    Output("ret-chart",  "style"),
    Output("ret-alert",  "children"),
    Output("ret-alert",  "is_open"),
    Output("ret-alert",  "color"),
    Input("ret-btn-calc",     "n_clicks"),
    State("ret-period",       "value"),
    State("ret-date-from",    "date"),
    State("ret-date-to",      "date"),
    State("ret-mode",         "value"),
    State("ret-individual",   "value"),
    State("ret-group-dim",    "value"),
    State("ret-group-val",    "value"),
    State("ret-benchmark",    "value"),
    State("ret-sintetico",    "value"),
    prevent_initial_call=True,
)
def calc_returns(_, period, date_from, date_to, mode,
                 individual_ids, group_dim, group_val, benchmark_ids, synthetic_ids):
    if not current_user.is_authenticated:
        return no_update, no_update, no_update, no_update, no_update

    _hide = {"height": "420px", "display": "none"}
    _show = {"height": "420px"}

    def _err(msg):
        return no_update, _hide, msg, True, "warning"

    # Resolver activos
    asset_ids = svc.resolve_asset_ids(
        mode, individual_ids, group_dim, group_val, benchmark_ids, synthetic_ids
    )
    if not asset_ids:
        return _err("No hay activos seleccionados para el modo elegido.")

    # Resolver período
    d_from, d_to = svc.period_to_dates(period, date_from, date_to)
    if d_from >= d_to:
        return _err("La fecha de inicio debe ser anterior a la fecha de fin.")

    # Calcular retornos
    results = svc.get_returns(asset_ids, d_from, d_to)
    if not results:
        return _err("No se encontraron precios para el período seleccionado.")

    tickers  = [r["ticker"]     for r in results]
    returns  = [r["return_pct"] for r in results]
    names    = [r["name"]       for r in results]
    d_starts = [r["date_start"] for r in results]
    d_ends   = [r["date_end"]   for r in results]
    c_starts = [r["close_start"] for r in results]
    c_ends   = [r["close_end"]   for r in results]

    colors = ["#4ade80" if v >= 0 else "#f87171" for v in returns]

    hover = [
        f"<b>{tickers[i]}</b> — {names[i]}<br>"
        f"Retorno: <b>{returns[i]:+.2f}%</b><br>"
        f"Desde: {d_starts[i]}  ({c_starts[i]:.2f})<br>"
        f"Hasta: {d_ends[i]}  ({c_ends[i]:.2f})"
        for i in range(len(results))
    ]

    text_labels = [f"{v:+.1f}%" for v in returns]

    fig = go.Figure(go.Bar(
        x=tickers,
        y=returns,
        marker_color=colors,
        text=text_labels,
        textposition="outside",
        textfont=dict(size=11, color="#dee2e6"),
        hovertemplate="%{customdata}<extra></extra>",
        customdata=hover,
        cliponaxis=False,
    ))

    # Línea de cero
    fig.add_hline(y=0, line_color="#4b5563", line_width=1)

    _period_lbl = {
        "1D": "1 Día", "1S": "1 Semana", "1M": "1 Mes",
        "3M": "3 Meses", "6M": "6 Meses", "YTD": "YTD", "1A": "1 Año",
        "rng": f"{d_from} → {d_to}",
    }
    title = f"Retorno {_period_lbl.get(period, period)}"

    # Rotar etiquetas si hay muchos activos
    tickangle = -45 if len(tickers) > 12 else 0
    # Ajustar margen superior para etiquetas fuera de barra
    ymax  = max(abs(v) for v in returns)
    ypad  = ymax * 0.18

    fig.update_layout(
        title=dict(text=title, font=dict(color="#f59e0b", size=16), x=0),
        plot_bgcolor=_BG,
        paper_bgcolor=_BG,
        font=dict(color="#dee2e6", size=11),
        margin=dict(l=50, r=20, t=50, b=60),
        xaxis=dict(
            tickfont=dict(size=10),
            gridcolor="#1f2937",
            tickangle=tickangle,
        ),
        yaxis=dict(
            ticksuffix="%",
            gridcolor="#1f2937",
            zerolinecolor="#4b5563",
            range=[min(0, min(returns)) - ypad, max(0, max(returns)) + ypad],
        ),
        bargap=0.25,
        showlegend=False,
    )

    n_sin_datos = len(asset_ids) - len(results)
    msg = ""
    if n_sin_datos:
        msg = f"{n_sin_datos} activo(s) sin datos para el período fueron excluidos."

    return fig, _show, msg, bool(msg), "info"
