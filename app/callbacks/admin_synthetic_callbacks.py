from dash import Input, Output, State, callback, ctx, html, no_update
import dash_bootstrap_components as dbc

import app.services.synthetic_service as svc

_th = {"fontSize": "0.78rem", "color": "#aaa", "fontWeight": "normal",
       "padding": "6px 8px", "borderBottom": "1px solid #374151"}
_td = {"fontSize": "0.82rem", "padding": "5px 8px", "borderBottom": "1px solid #1f2937"}


# ── Cargar dropdowns ──────────────────────────────────────────────────────────
@callback(
    Output("syn-f-asset",       "options"),
    Output("syn-f-numerator",   "options"),
    Output("syn-f-denominator", "options"),
    Input("syn-modal", "is_open"),
)
def load_dropdowns(is_open):
    if not is_open:
        return no_update, no_update, no_update
    syn_opts = svc.get_assets_options_for_synthetic()
    all_opts = svc.get_all_assets_options()
    return syn_opts, all_opts, all_opts


# ── Preview de fórmula ────────────────────────────────────────────────────────
@callback(
    Output("syn-formula-preview", "children"),
    Input("syn-f-asset",       "value"),
    Input("syn-f-numerator",   "value"),
    Input("syn-f-denominator", "value"),
    State("syn-f-asset",       "options"),
    State("syn-f-numerator",   "options"),
    State("syn-f-denominator", "options"),
)
def update_preview(asset_id, num_id, den_id, asset_opts, num_opts, den_opts):
    def label(val, opts):
        if not val or not opts:
            return "?"
        for o in opts:
            if o["value"] == val:
                return o["label"].split(" — ")[0]
        return "?"

    a = label(asset_id, asset_opts)
    n = label(num_id,   num_opts)
    d = label(den_id,   den_opts)
    return f"Fórmula: {a} = {n} / {d}"


# ── Tabla de configuraciones ──────────────────────────────────────────────────
@callback(
    Output("syn-table-container", "children"),
    Input("syn-alert", "is_open"),
    Input("syn-modal", "is_open"),
)
def load_table(_alert, _modal):
    configs = svc.get_all_configs()
    if not configs:
        return html.P("Sin activos sintéticos configurados.", className="text-muted mt-2",
                      style={"fontSize": "0.82rem"})

    rows = []
    for cfg in configs:
        a   = cfg.asset.ticker       if cfg.asset       else "—"
        n   = cfg.numerator.ticker   if cfg.numerator   else "—"
        d   = cfg.denominator.ticker if cfg.denominator else "—"
        name = cfg.asset.name if cfg.asset else ""
        rows.append(html.Tr([
            html.Td(f"{a}", style=_td),
            html.Td(name,  style={**_td, "color": "#9ca3af", "fontSize": "0.78rem"}),
            html.Td(f"{n} / {d}", style=_td),
            html.Td(
                dbc.ButtonGroup([
                    dbc.Button("Editar",    id={"type": "syn-edit",    "index": cfg.id},
                               color="link", size="sm", style={"fontSize": "0.75rem"}),
                    dbc.Button("Δ Calcular", id={"type": "syn-calc-delta", "index": cfg.id},
                               color="link", size="sm",
                               style={"fontSize": "0.75rem", "color": "#38bdf8"}),
                    dbc.Button("↺ Completo", id={"type": "syn-calc-full", "index": cfg.id},
                               color="link", size="sm",
                               style={"fontSize": "0.75rem", "color": "#fb923c"}),
                    dbc.Button("Eliminar",  id={"type": "syn-delete",  "index": cfg.id},
                               color="link", size="sm",
                               style={"fontSize": "0.75rem", "color": "#ef4444"}),
                ]),
                style=_td,
            ),
        ]))

    return html.Table([
        html.Thead(html.Tr([
            html.Th("Ticker",    style=_th),
            html.Th("Nombre",    style=_th),
            html.Th("Fórmula",   style=_th),
            html.Th("Acciones",  style=_th),
        ])),
        html.Tbody(rows),
    ], style={"width": "100%", "borderCollapse": "collapse"})


# ── Abrir / cerrar modal ──────────────────────────────────────────────────────
@callback(
    Output("syn-modal",       "is_open"),
    Output("syn-modal-title", "children"),
    Output("syn-f-asset",     "value"),
    Output("syn-f-numerator", "value"),
    Output("syn-f-denominator", "value"),
    Output("syn-editing-id",  "data"),
    Output("syn-modal-error", "is_open", allow_duplicate=True),
    Input("syn-btn-add",    "n_clicks"),
    Input("syn-btn-cancel", "n_clicks"),
    Input({"type": "syn-edit", "index": __import__('dash').ALL}, "n_clicks"),
    State("syn-editing-id", "data"),
    prevent_initial_call=True,
)
def toggle_modal(n_add, n_cancel, n_edit, editing_id):
    trigger = ctx.triggered_id

    if trigger == "syn-btn-cancel":
        return False, no_update, no_update, no_update, no_update, None, False

    if trigger == "syn-btn-add":
        return True, "Nuevo activo sintético", None, None, None, None, False

    if isinstance(trigger, dict) and trigger.get("type") == "syn-edit":
        cfg_id = trigger["index"]
        configs = svc.get_all_configs()
        cfg = next((c for c in configs if c.id == cfg_id), None)
        if cfg is None:
            return no_update, no_update, no_update, no_update, no_update, no_update, no_update
        return (True, "Editar activo sintético",
                cfg.asset_id, cfg.numerator_asset_id, cfg.denominator_asset_id,
                cfg.id, False)

    return no_update, no_update, no_update, no_update, no_update, no_update, no_update


# ── Guardar ───────────────────────────────────────────────────────────────────
@callback(
    Output("syn-alert",       "children"),
    Output("syn-alert",       "is_open"),
    Output("syn-alert",       "color"),
    Output("syn-modal",       "is_open",   allow_duplicate=True),
    Output("syn-modal-error", "children"),
    Output("syn-modal-error", "is_open"),
    Input("syn-btn-save",   "n_clicks"),
    State("syn-f-asset",      "value"),
    State("syn-f-numerator",  "value"),
    State("syn-f-denominator","value"),
    State("syn-editing-id",   "data"),
    prevent_initial_call=True,
)
def save_config(_, asset_id, num_id, den_id, editing_id):
    if not asset_id or not num_id or not den_id:
        return no_update, no_update, no_update, no_update, "Completá todos los campos.", True
    if num_id == den_id:
        return no_update, no_update, no_update, no_update, \
               "Numerador y denominador no pueden ser el mismo activo.", True
    try:
        svc.save_config(asset_id, num_id, den_id)
        return "Configuración guardada.", True, "success", False, "", False
    except Exception as exc:
        return no_update, no_update, no_update, no_update, str(exc), True


# ── Eliminar ──────────────────────────────────────────────────────────────────
@callback(
    Output("syn-alert", "children", allow_duplicate=True),
    Output("syn-alert", "is_open",  allow_duplicate=True),
    Output("syn-alert", "color",    allow_duplicate=True),
    Input({"type": "syn-delete", "index": __import__('dash').ALL}, "n_clicks"),
    prevent_initial_call=True,
)
def delete_config(n_clicks):
    trigger = ctx.triggered_id
    if not isinstance(trigger, dict) or not any(n_clicks):
        return no_update, no_update, no_update
    try:
        svc.delete_config(trigger["index"])
        return "Configuración eliminada.", True, "success"
    except Exception as exc:
        return str(exc), True, "danger"


# ── Calcular delta ────────────────────────────────────────────────────────────
@callback(
    Output("syn-alert", "children", allow_duplicate=True),
    Output("syn-alert", "is_open",  allow_duplicate=True),
    Output("syn-alert", "color",    allow_duplicate=True),
    Input({"type": "syn-calc-delta", "index": __import__('dash').ALL}, "n_clicks"),
    prevent_initial_call=True,
)
def calc_delta(n_clicks):
    trigger = ctx.triggered_id
    if not isinstance(trigger, dict) or not any(n_clicks):
        return no_update, no_update, no_update
    try:
        configs = svc.get_all_configs()
        cfg = next((c for c in configs if c.id == trigger["index"]), None)
        if cfg is None:
            return "Configuración no encontrada.", True, "danger"
        count = svc.compute_synthetic_prices(cfg.asset_id, full=False)
        return f"Delta calculado: {count} precios insertados.", True, "success"
    except Exception as exc:
        return str(exc), True, "danger"


# ── Calcular completo ─────────────────────────────────────────────────────────
@callback(
    Output("syn-alert", "children", allow_duplicate=True),
    Output("syn-alert", "is_open",  allow_duplicate=True),
    Output("syn-alert", "color",    allow_duplicate=True),
    Input({"type": "syn-calc-full", "index": __import__('dash').ALL}, "n_clicks"),
    prevent_initial_call=True,
)
def calc_full(n_clicks):
    trigger = ctx.triggered_id
    if not isinstance(trigger, dict) or not any(n_clicks):
        return no_update, no_update, no_update
    try:
        configs = svc.get_all_configs()
        cfg = next((c for c in configs if c.id == trigger["index"]), None)
        if cfg is None:
            return "Configuración no encontrada.", True, "danger"
        count = svc.compute_synthetic_prices(cfg.asset_id, full=True)
        return f"Recalculado completo: {count} precios insertados.", True, "success"
    except Exception as exc:
        return str(exc), True, "danger"
