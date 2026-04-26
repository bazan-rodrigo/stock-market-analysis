from datetime import date as _date

from dash import ALL, Input, Output, State, callback, ctx, html, no_update
import dash_bootstrap_components as dbc
import plotly.graph_objects as go

import app.services.evolution_service as svc
import app.services.reference_service as ref_svc
from app.services.asset_service import get_assets


# ── Poblar dropdowns ──────────────────────────────────────────────────────────

@callback(
    Output("evol-add-select", "options"),
    Output("evol-bm-select",  "options"),
    Output("evol-syn-select", "options"),
    Output("evol-f-country",  "options"),
    Output("evol-f-currency", "options"),
    Output("evol-f-itype",    "options"),
    Output("evol-f-sector",   "options"),
    Output("evol-f-industry", "options"),
    Output("evol-f-market",   "options"),
    Input("evol-add-select",  "id"),
)
def load_options(_):
    assets     = get_assets()
    countries  = ref_svc.get_countries()
    currencies = ref_svc.get_currencies()
    itypes     = ref_svc.get_instrument_types()
    sectors    = ref_svc.get_sectors()
    industries = ref_svc.get_industries()
    markets    = ref_svc.get_markets()

    return (
        [{"label": f"{a.ticker} — {a.name}", "value": a.id} for a in assets],
        svc.get_benchmark_assets_options(),
        svc.get_synthetic_assets_options(),
        [{"label": c.name, "value": c.id} for c in countries],
        [{"label": c.name, "value": c.id} for c in currencies],
        [{"label": it.name, "value": it.id} for it in itypes],
        [{"label": s.name, "value": s.id} for s in sectors],
        [{"label": i.name, "value": i.id} for i in industries],
        [{"label": m.name, "value": m.id} for m in markets],
    )


# ── Mostrar panel según modo ──────────────────────────────────────────────────

@callback(
    Output("evol-panel-activo",    "style"),
    Output("evol-panel-benchmark", "style"),
    Output("evol-panel-sintetico", "style"),
    Output("evol-panel-grupos",    "style"),
    Input("evol-mode", "value"),
)
def switch_panel(mode):
    show, hide = {}, {"display": "none"}
    return (
        show if mode == "activo"    else hide,
        show if mode == "benchmark" else hide,
        show if mode == "sintetico" else hide,
        show if mode == "grupos"    else hide,
    )


# ── Agregar activo individual ─────────────────────────────────────────────────

@callback(
    Output("evol-pending-add",     "data",     allow_duplicate=True),
    Output("evol-rel-modal",       "is_open",  allow_duplicate=True),
    Output("evol-rel-modal-title", "children", allow_duplicate=True),
    Output("evol-rel-modal-body",  "children", allow_duplicate=True),
    Output("evol-series",          "data",     allow_duplicate=True),
    Output("evol-alert",           "children", allow_duplicate=True),
    Output("evol-alert",           "is_open",  allow_duplicate=True),
    Input("evol-btn-add",   "n_clicks"),
    State("evol-add-select", "value"),
    State("evol-series",     "data"),
    prevent_initial_call=True,
)
def add_individual(n_clicks, asset_id, series):
    if not n_clicks or asset_id is None:
        return no_update, no_update, no_update, no_update, no_update, no_update, no_update
    return _add_single_asset(asset_id, series)


# ── Agregar sintético ─────────────────────────────────────────────────────────

@callback(
    Output("evol-pending-add",     "data",     allow_duplicate=True),
    Output("evol-rel-modal",       "is_open",  allow_duplicate=True),
    Output("evol-rel-modal-title", "children", allow_duplicate=True),
    Output("evol-rel-modal-body",  "children", allow_duplicate=True),
    Output("evol-series",          "data",     allow_duplicate=True),
    Output("evol-alert",           "children", allow_duplicate=True),
    Output("evol-alert",           "is_open",  allow_duplicate=True),
    Input("evol-btn-add-syn", "n_clicks"),
    State("evol-syn-select",  "value"),
    State("evol-series",      "data"),
    prevent_initial_call=True,
)
def add_synthetic(n_clicks, asset_id, series):
    if not n_clicks or asset_id is None:
        return no_update, no_update, no_update, no_update, no_update, no_update, no_update
    return _add_single_asset(asset_id, series)


def _add_single_asset(asset_id, series):
    """Lógica compartida entre 'por activo' y 'por sintético'."""
    existing_ids = {s["asset_id"] for s in series}
    if asset_id in existing_ids:
        return no_update, no_update, no_update, no_update, no_update, \
               "El activo ya está en la lista.", True

    related = svc.get_related_assets(asset_id)
    ticker, name = svc.get_asset_label(asset_id)

    if related["is_synthetic"] or related["is_benchmark"]:
        if related["is_synthetic"]:
            rel_ids  = related["component_ids"]
            rel_type = "componentes de la fórmula sintética"
        else:
            rel_ids  = related["referenced_ids"]
            rel_type = "activos que usan este benchmark"

        rel_labels = []
        for rid in rel_ids[:10]:
            t, n = svc.get_asset_label(rid)
            rel_labels.append(html.Li(f"{t} — {n}", style={"fontSize": "0.82rem"}))
        if len(rel_ids) > 10:
            rel_labels.append(html.Li(f"... y {len(rel_ids)-10} más", className="text-muted"))

        body = html.Div([
            html.P(f"El activo {ticker} tiene {len(rel_ids)} {rel_type}:"),
            html.Ul(rel_labels, className="mb-0"),
        ])
        return asset_id, True, f"Agregar: {ticker}", body, no_update, no_update, False

    color_idx = len(series)
    new_series = series + [{
        "asset_id": asset_id, "ticker": ticker, "name": name,
        "group": "manual", "visible": True,
        "color": svc.assign_color(color_idx),
    }]
    return None, False, no_update, no_update, new_series, no_update, False


# ── Agregar por benchmark ─────────────────────────────────────────────────────

@callback(
    Output("evol-series", "data",     allow_duplicate=True),
    Output("evol-alert",  "children", allow_duplicate=True),
    Output("evol-alert",  "is_open",  allow_duplicate=True),
    Input("evol-btn-add-bm", "n_clicks"),
    State("evol-bm-select",  "value"),
    State("evol-series",     "data"),
    prevent_initial_call=True,
)
def add_by_benchmark(n_clicks, benchmark_id, series):
    if not n_clicks or not benchmark_id:
        return no_update, no_update, no_update

    assets = svc.get_assets_for_benchmark(benchmark_id)
    if not assets:
        return no_update, "No hay activos asociados a ese benchmark.", True

    existing   = {s["asset_id"] for s in series}
    color_base = len(series)
    added = []
    for a in assets:
        if a["asset_id"] in existing:
            continue
        added.append({
            "asset_id": a["asset_id"], "ticker": a["ticker"], "name": a["name"],
            "group": "group", "visible": True,
            "color": svc.assign_color(color_base + len(added)),
        })

    if not added:
        return no_update, "Todos los activos de ese benchmark ya están en la lista.", True

    return series + added, f"{len(added)} activo(s) agregado(s).", True


# ── Decisión del modal de relacionados ────────────────────────────────────────

@callback(
    Output("evol-series",      "data",    allow_duplicate=True),
    Output("evol-rel-modal",   "is_open", allow_duplicate=True),
    Output("evol-pending-add", "data",    allow_duplicate=True),
    Input("evol-rel-btn-yes",  "n_clicks"),
    Input("evol-rel-btn-no",   "n_clicks"),
    State("evol-pending-add",  "data"),
    State("evol-series",       "data"),
    prevent_initial_call=True,
)
def resolve_modal(yes, no_btn, asset_id, series):
    if not asset_id:
        return no_update, False, None

    trigger    = ctx.triggered_id
    existing   = {s["asset_id"] for s in series}
    color_base = len(series)

    ticker, name = svc.get_asset_label(asset_id)
    new_entries = [{
        "asset_id": asset_id, "ticker": ticker, "name": name,
        "group": "manual", "visible": True,
        "color": svc.assign_color(color_base),
    }]

    if trigger == "evol-rel-btn-yes":
        related = svc.get_related_assets(asset_id)
        rel_ids = related["component_ids"] or related["referenced_ids"]
        for i, rid in enumerate(rel_ids):
            if rid in existing:
                continue
            t, n = svc.get_asset_label(rid)
            new_entries.append({
                "asset_id": rid, "ticker": t, "name": n,
                "group": "related", "visible": True,
                "color": svc.assign_color(color_base + 1 + i),
            })

    return series + [e for e in new_entries if e["asset_id"] not in existing], False, None


# ── Agregar por grupo ─────────────────────────────────────────────────────────

@callback(
    Output("evol-series", "data",     allow_duplicate=True),
    Output("evol-alert",  "children", allow_duplicate=True),
    Output("evol-alert",  "is_open",  allow_duplicate=True),
    Input("evol-btn-add-group", "n_clicks"),
    State("evol-f-country",     "value"),
    State("evol-f-currency",    "value"),
    State("evol-f-itype",       "value"),
    State("evol-f-sector",      "value"),
    State("evol-f-industry",    "value"),
    State("evol-f-market",      "value"),
    State("evol-series",        "data"),
    prevent_initial_call=True,
)
def add_group(n_clicks, countries, currencies, itypes, sectors, industries, markets, series):
    if not n_clicks:
        return no_update, no_update, no_update

    if not any([countries, currencies, itypes, sectors, industries, markets]):
        return no_update, "Seleccioná al menos un filtro.", True

    assets = svc.get_assets_by_filters(
        country_ids=countries or None,
        currency_ids=currencies or None,
        instrument_type_ids=itypes or None,
        sector_ids=sectors or None,
        industry_ids=industries or None,
        market_ids=markets or None,
    )
    if not assets:
        return no_update, "No hay activos que coincidan con los filtros.", True

    existing   = {s["asset_id"] for s in series}
    color_base = len(series)
    added = []
    for a in assets:
        if a["asset_id"] in existing:
            continue
        added.append({
            "asset_id": a["asset_id"], "ticker": a["ticker"], "name": a["name"],
            "group": "group", "visible": True,
            "color": svc.assign_color(color_base + len(added)),
        })

    if not added:
        return no_update, "Todos los activos del grupo ya están en la lista.", True

    return series + added, f"{len(added)} activo(s) agregado(s).", True


# ── Limpiar todo ──────────────────────────────────────────────────────────────

@callback(
    Output("evol-series", "data", allow_duplicate=True),
    Input("evol-btn-clear", "n_clicks"),
    prevent_initial_call=True,
)
def clear_all(n_clicks):
    return [] if n_clicks else no_update


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
    return [s for s in series if s["asset_id"] != triggered["index"]]


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
    for s in series:
        if s["asset_id"] == triggered["index"]:
            s["visible"] = not s["visible"]
            break
    return series


# ── Renderizar lista de series (compacta, derecha) ────────────────────────────

_GROUP_LABEL = {"manual": "", "related": "rel", "group": "grp"}


@callback(
    Output("evol-series-list", "children"),
    Input("evol-series", "data"),
)
def render_series_list(series):
    if not series:
        return html.P("Sin series.", className="text-muted",
                      style={"fontSize": "0.78rem"})

    chips = []
    for s in series:
        aid     = s["asset_id"]
        visible = s.get("visible", True)
        color   = s.get("color", "#888")
        group   = s.get("group", "manual")
        opacity = 1.0 if visible else 0.35
        label   = s["ticker"] + (f" [{_GROUP_LABEL[group]}]" if _GROUP_LABEL.get(group) else "")

        chips.append(html.Div([
            html.Div(style={
                "width": "8px", "height": "8px", "flexShrink": "0",
                "backgroundColor": color, "borderRadius": "2px",
                "opacity": str(opacity),
            }),
            html.Span(label,
                      style={"opacity": str(opacity), "marginLeft": "4px",
                             "whiteSpace": "nowrap"},
                      title=s.get("name", "")),
            dbc.Button(
                html.I(className=f"fa {'fa-eye' if visible else 'fa-eye-slash'}"),
                id={"type": "evol-toggle", "index": aid},
                color="link", size="sm", className="p-0",
                style={"color": color if visible else "#555", "fontSize": "0.7rem",
                       "marginLeft": "4px", "lineHeight": "1"},
            ),
            dbc.Button(
                html.I(className="fa fa-times"),
                id={"type": "evol-remove", "index": aid},
                color="link", size="sm", className="p-0",
                style={"color": "#dc3545", "fontSize": "0.7rem",
                       "marginLeft": "2px", "lineHeight": "1"},
            ),
        ], style={
            "display": "inline-flex", "alignItems": "center",
            "border": "1px solid #374151", "borderRadius": "4px",
            "padding": "2px 6px", "backgroundColor": "#1f2937",
        }))

    return chips


# ── Renderizar gráfico ────────────────────────────────────────────────────────

@callback(
    Output("evol-graph",      "figure"),
    Output("evol-alert",      "children", allow_duplicate=True),
    Output("evol-alert",      "is_open",  allow_duplicate=True),
    Input("evol-series",      "data"),
    Input("evol-date-from",   "date"),
    Input("evol-date-to",     "date"),
    Input("evol-show-events", "value"),
    prevent_initial_call=True,
)
def render_chart(series, date_from, date_to, show_events):
    visible = [s for s in series if s.get("visible", True)]

    fig = go.Figure()
    _style_fig(fig)

    if not visible:
        return fig, no_update, False

    def _parse(d):
        try:
            return _date.fromisoformat(d[:10]) if d else None
        except ValueError:
            return None

    bd = _parse(date_from)
    ed = _parse(date_to)

    asset_ids  = [s["asset_id"] for s in visible]
    price_data = svc.get_normalized_prices(asset_ids, base_date=bd, end_date=ed)

    if not price_data:
        return fig, "No hay precios en común para las series seleccionadas.", True

    color_map = {s["asset_id"]: s.get("color", "#888") for s in visible}

    for s in visible:
        aid = s["asset_id"]
        pd  = price_data.get(aid)
        if pd is None:
            continue
        color = color_map.get(aid, "#888")
        n     = len(pd["dates"])

        fig.add_trace(go.Scatter(
            x=pd["dates"],
            y=pd["values"],
            mode="lines+text",
            name=pd["ticker"],
            line={"color": color, "width": 1.8},
            text=[""] * (n - 1) + [f"  {pd['ticker']}"],
            textposition="middle right",
            textfont={"size": 9, "color": color},
            hovertemplate="%{x}<br>%{y:.2f}<extra>" + pd["ticker"] + "</extra>",
            showlegend=False,
        ))

    fig.add_hline(y=100, line_dash="dot", line_color="#555", line_width=1)

    # Eventos de Mercado — solo los que se solapan con el rango visible
    if show_events:
        all_dates   = [d for v in price_data.values() for d in v["dates"]]
        chart_start = min(all_dates) if all_dates else None
        chart_end   = max(all_dates) if all_dates else None
        for ev in svc.get_events_for_assets(asset_ids):
            if chart_start and ev["end"] < chart_start:
                continue
            if chart_end and ev["start"] > chart_end:
                continue
            fig.add_vrect(
                x0=ev["start"], x1=ev["end"],
                fillcolor=ev["color"], opacity=0.12,
                layer="below", line_width=0,
                annotation_text=ev["name"],
                annotation_position="top left",
                annotation_font_size=8,
                annotation_font_color=ev["color"],
            )

    base_str = str(bd) if bd else (
        min(v["base_date"] for v in price_data.values()) if price_data else "")
    title = f"Evolución relativa (base 100 — {base_str})" if price_data else ""

    fig.update_layout(
        title={"text": title, "font": {"size": 12}, "x": 0.5, "xanchor": "center"},
        margin={"l": 50, "r": 120, "t": 40, "b": 40},
    )

    return fig, no_update, False


def _style_fig(fig):
    fig.update_layout(
        paper_bgcolor="#1e2126",
        plot_bgcolor="#1e2126",
        font_color="#dee2e6",
        margin={"l": 50, "r": 120, "t": 40, "b": 40},
        hovermode="x unified",
        showlegend=False,
        xaxis={"gridcolor": "#2c3038", "showspikes": True},
        yaxis={"gridcolor": "#2c3038"},
    )
