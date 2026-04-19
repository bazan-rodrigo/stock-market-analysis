from dash import ALL, Input, Output, State, callback, ctx, html, no_update
import dash_bootstrap_components as dbc
import plotly.graph_objects as go

import app.services.evolution_service as svc
from app.services.asset_service import get_assets


# ── Poblar dropdowns ──────────────────────────────────────────────────────────

@callback(
    Output("evol-primary",    "options"),
    Output("evol-add-select", "options"),
    Input("evol-primary",     "id"),   # fires once on load
)
def load_options(_):
    assets = get_assets()
    opts = [{"label": f"{a.ticker} — {a.name}", "value": a.id} for a in assets]
    return opts, opts


# ── Seleccionar activo principal ──────────────────────────────────────────────

@callback(
    Output("evol-series", "data", allow_duplicate=True),
    Input("evol-primary",      "value"),
    Input("evol-show-related", "value"),
    State("evol-series",       "data"),
    prevent_initial_call=True,
)
def select_primary(asset_id, show_related, series):
    if asset_id is None:
        # Clear all primary/component/benchmark series; keep only "manual"
        return [s for s in series if s.get("group") == "manual"]

    related = svc.get_related_assets(asset_id)
    ticker, name = svc.get_asset_label(asset_id)

    new_series = [s for s in series if s.get("group") == "manual"]

    # Primary
    new_series.insert(0, {
        "asset_id": asset_id,
        "ticker":   ticker,
        "name":     name,
        "group":    "primary",
        "visible":  True,
        "color":    svc.assign_color(0),
    })

    if show_related:
        color_idx = 1
        if related["is_synthetic"]:
            for cid in related["component_ids"]:
                t, n = svc.get_asset_label(cid)
                new_series.append({
                    "asset_id": cid,
                    "ticker":   t,
                    "name":     n,
                    "group":    "component",
                    "visible":  True,
                    "color":    svc.assign_color(color_idx),
                })
                color_idx += 1

        if related["is_benchmark"]:
            for rid in related["referenced_ids"]:
                t, n = svc.get_asset_label(rid)
                new_series.append({
                    "asset_id": rid,
                    "ticker":   t,
                    "name":     n,
                    "group":    "benchmark_ref",
                    "visible":  True,
                    "color":    svc.assign_color(color_idx),
                })
                color_idx += 1

    # Re-assign colors for manual series
    manual_start = sum(1 for s in new_series if s["group"] != "manual")
    for i, s in enumerate(new_series):
        if s["group"] == "manual":
            s["color"] = svc.assign_color(manual_start + i)

    return new_series


# ── Toggle relacionados ───────────────────────────────────────────────────────

@callback(
    Output("evol-series", "data", allow_duplicate=True),
    Input("evol-show-related", "value"),
    State("evol-primary",      "value"),
    State("evol-series",       "data"),
    prevent_initial_call=True,
)
def toggle_related(show_related, primary_id, series):
    if primary_id is None:
        return no_update
    related_groups = {"component", "benchmark_ref"}
    for s in series:
        if s.get("group") in related_groups:
            s["visible"] = bool(show_related)
    return series


# ── Agregar serie manual ──────────────────────────────────────────────────────

@callback(
    Output("evol-series",       "data",     allow_duplicate=True),
    Output("evol-add-select",   "value"),
    Output("evol-alert",        "children", allow_duplicate=True),
    Output("evol-alert",        "is_open",  allow_duplicate=True),
    Input("evol-btn-add",       "n_clicks"),
    State("evol-add-select",    "value"),
    State("evol-series",        "data"),
    prevent_initial_call=True,
)
def add_manual(n_clicks, asset_id, series):
    if not n_clicks or asset_id is None:
        return no_update, no_update, no_update, no_update

    existing_ids = {s["asset_id"] for s in series}
    if asset_id in existing_ids:
        return no_update, no_update, "El activo ya está en la lista.", True

    ticker, name = svc.get_asset_label(asset_id)
    color_idx = len(series)
    series = series + [{
        "asset_id": asset_id,
        "ticker":   ticker,
        "name":     name,
        "group":    "manual",
        "visible":  True,
        "color":    svc.assign_color(color_idx),
    }]
    return series, None, no_update, False


# ── Eliminar serie ────────────────────────────────────────────────────────────

@callback(
    Output("evol-series", "data", allow_duplicate=True),
    Input({"type": "evol-remove", "index": ALL}, "n_clicks"),
    State("evol-series", "data"),
    prevent_initial_call=True,
)
def remove_series(n_clicks_list, series):
    if not any(n for n in n_clicks_list if n):
        return no_update
    triggered = ctx.triggered_id
    if triggered is None:
        return no_update
    remove_id = triggered["index"]
    return [s for s in series if s["asset_id"] != remove_id]


# ── Toggle visibilidad individual ─────────────────────────────────────────────

@callback(
    Output("evol-series", "data", allow_duplicate=True),
    Input({"type": "evol-toggle", "index": ALL}, "n_clicks"),
    State("evol-series", "data"),
    prevent_initial_call=True,
)
def toggle_individual(n_clicks_list, series):
    if not any(n for n in n_clicks_list if n):
        return no_update
    triggered = ctx.triggered_id
    if triggered is None:
        return no_update
    toggle_id = triggered["index"]
    for s in series:
        if s["asset_id"] == toggle_id:
            s["visible"] = not s["visible"]
            break
    return series


# ── Renderizar lista de series ────────────────────────────────────────────────

_GROUP_LABEL = {
    "primary":       "Principal",
    "component":     "Componente",
    "benchmark_ref": "Referenciado",
    "manual":        "Manual",
}


@callback(
    Output("evol-series-list", "children"),
    Input("evol-series", "data"),
)
def render_series_list(series):
    if not series:
        return html.P("Sin series.", className="text-muted", style={"fontSize": "0.8rem"})

    rows = []
    for s in series:
        aid      = s["asset_id"]
        visible  = s.get("visible", True)
        color    = s.get("color", "#888")
        group    = s.get("group", "manual")
        eye_icon = "fa-eye" if visible else "fa-eye-slash"
        opacity  = 1.0 if visible else 0.4

        rows.append(
            dbc.Row([
                dbc.Col(
                    html.Div(style={
                        "width": "12px", "height": "12px",
                        "backgroundColor": color,
                        "borderRadius": "2px",
                        "marginTop": "3px",
                        "opacity": opacity,
                    }),
                    width="auto",
                ),
                dbc.Col(
                    html.Div([
                        html.Span(s["ticker"], style={"fontWeight": "600", "fontSize": "0.82rem"}),
                        html.Span(f"  {_GROUP_LABEL.get(group, group)}",
                                  className="text-muted", style={"fontSize": "0.72rem"}),
                    ]),
                ),
                dbc.Col(
                    dbc.ButtonGroup([
                        dbc.Button(
                            html.I(className=f"fa {eye_icon}"),
                            id={"type": "evol-toggle", "index": aid},
                            color="link", size="sm", className="p-0 me-1",
                            style={"color": color if visible else "#666"},
                        ),
                        dbc.Button(
                            html.I(className="fa fa-times"),
                            id={"type": "evol-remove", "index": aid},
                            color="link", size="sm", className="p-0",
                            style={"color": "#dc3545"},
                        ),
                    ]),
                    width="auto",
                ),
            ], className="mb-1 align-items-center g-1")
        )

    return html.Div(rows, style={"maxHeight": "500px", "overflowY": "auto"})


# ── Renderizar gráfico ────────────────────────────────────────────────────────

@callback(
    Output("evol-graph",  "figure"),
    Output("evol-alert",  "children", allow_duplicate=True),
    Output("evol-alert",  "is_open",  allow_duplicate=True),
    Input("evol-series",  "data"),
    Input("evol-base-date", "date"),
    prevent_initial_call=True,
)
def render_chart(series, base_date):
    from datetime import date as _date

    visible = [s for s in series if s.get("visible", True)]
    if not visible:
        fig = go.Figure()
        _style_fig(fig)
        return fig, no_update, False

    asset_ids = [s["asset_id"] for s in visible]
    bd = None
    if base_date:
        try:
            bd = _date.fromisoformat(base_date[:10])
        except ValueError:
            pass

    price_data = svc.get_normalized_prices(asset_ids, base_date=bd)

    if not price_data:
        fig = go.Figure()
        _style_fig(fig)
        return fig, "No hay precios en común para las series seleccionadas.", True

    color_map = {s["asset_id"]: s.get("color", "#888") for s in visible}

    fig = go.Figure()
    for s in visible:
        aid = s["asset_id"]
        pd  = price_data.get(aid)
        if pd is None:
            continue
        fig.add_trace(go.Scatter(
            x=pd["dates"],
            y=pd["values"],
            mode="lines",
            name=pd["ticker"],
            line={"color": color_map.get(aid, "#888"), "width": 1.5},
            hovertemplate="%{x}<br>%{y:.2f}<extra>" + pd["ticker"] + "</extra>",
        ))

    fig.add_hline(y=100, line_dash="dot", line_color="#555", line_width=1)
    _style_fig(fig)
    return fig, no_update, False


def _style_fig(fig):
    fig.update_layout(
        paper_bgcolor="#1e2126",
        plot_bgcolor="#1e2126",
        font_color="#dee2e6",
        margin={"l": 50, "r": 20, "t": 20, "b": 40},
        legend={"orientation": "h", "yanchor": "bottom", "y": 1.01,
                "xanchor": "left", "x": 0},
        hovermode="x unified",
        xaxis={"gridcolor": "#2c3038", "showspikes": True},
        yaxis={"gridcolor": "#2c3038", "ticksuffix": ""},
    )
