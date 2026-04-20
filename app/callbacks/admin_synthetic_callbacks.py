import base64

from dash import ALL, Input, Output, State, callback, ctx, dcc, html, no_update
import dash_bootstrap_components as dbc

import app.services.synthetic_service as svc
from app.pages.admin_synthetic import _help_card, _th, _td_s

_ROLE_OPTS = [
    {"label": "Numerador",   "value": "numerator"},
    {"label": "Denominador", "value": "denominator"},
]


# ── Cachear opciones de activos ───────────────────────────────────────────────
@callback(
    Output("syn-all-opts", "data"),
    Input("syn-modal", "is_open"),
)
def cache_asset_opts(is_open):
    if not is_open:
        return no_update
    return svc.get_all_assets_options()


@callback(
    Output("syn-f-asset", "options"),
    Input("syn-modal", "is_open"),
)
def load_synthetic_opts(is_open):
    if not is_open:
        return no_update
    return svc.get_assets_options_for_synthetic()


# ── Card de ayuda + parámetros de índice ─────────────────────────────────────
@callback(
    Output("syn-formula-help",  "children"),
    Output("syn-index-params",  "style"),
    Input("syn-formula-type",   "value"),
)
def update_help(ft):
    show_index = {"display": "block"} if ft == "index" else {"display": "none"}
    return _help_card(ft), show_index


# ── Tabla principal ───────────────────────────────────────────────────────────
@callback(
    Output("syn-table-container", "children"),
    Input("syn-alert",  "is_open"),
    Input("syn-modal",  "is_open"),
)
def load_table(_a, _m):
    formulas = svc.get_all_formulas()
    if not formulas:
        return html.P("Sin activos sintéticos configurados.",
                      className="text-muted mt-2", style={"fontSize": "0.82rem"})

    _TYPE_LABELS = {
        "ratio":        "Ratio",
        "weighted_avg": "Prom. ponderado",
        "weighted_sum": "Suma ponderada",
        "index":        "Índice base",
    }
    rows = []
    for f in formulas:
        rows.append(html.Tr([
            html.Td(f.asset.ticker if f.asset else "—", style=_td_s),
            html.Td(f.asset.name   if f.asset else "—",
                    style={**_td_s, "color": "#9ca3af", "fontSize": "0.76rem"}),
            html.Td(_TYPE_LABELS.get(f.formula_type, f.formula_type), style=_td_s),
            html.Td(svc.formula_preview_str(f),
                    style={**_td_s, "fontFamily": "monospace", "fontSize": "0.74rem",
                           "color": "#94a3b8", "maxWidth": "280px",
                           "overflow": "hidden", "textOverflow": "ellipsis",
                           "whiteSpace": "nowrap"}),
            html.Td(dbc.ButtonGroup([
                dbc.Button("Editar",     id={"type": "syn-edit",  "index": f.id},
                           color="link", size="sm", style={"fontSize": "0.74rem"}),
                dbc.Button("Δ Calcular", id={"type": "syn-delta", "index": f.id},
                           color="link", size="sm",
                           style={"fontSize": "0.74rem", "color": "#38bdf8"}),
                dbc.Button("↺ Completo", id={"type": "syn-full",  "index": f.id},
                           color="link", size="sm",
                           style={"fontSize": "0.74rem", "color": "#fb923c"}),
                dbc.Button("Eliminar",   id={"type": "syn-delete","index": f.id},
                           color="link", size="sm",
                           style={"fontSize": "0.74rem", "color": "#ef4444"}),
            ]), style=_td_s),
        ]))

    return html.Table([
        html.Thead(html.Tr([
            html.Th("Ticker",   style=_th),
            html.Th("Nombre",   style=_th),
            html.Th("Tipo",     style=_th),
            html.Th("Fórmula",  style=_th),
            html.Th("Acciones", style=_th),
        ])),
        html.Tbody(rows),
    ], style={"width": "100%", "borderCollapse": "collapse"})


# ── Abrir / cerrar modal ──────────────────────────────────────────────────────
@callback(
    Output("syn-modal",        "is_open"),
    Output("syn-modal-title",  "children"),
    Output("syn-formula-type", "value"),
    Output("syn-f-asset",      "value"),
    Output("syn-base-value",   "value"),
    Output("syn-base-date",    "date"),
    Output("syn-editing-id",   "data"),
    Output("syn-uid-store",    "data"),
    Output("syn-modal-error",  "is_open", allow_duplicate=True),
    Input("syn-btn-add",    "n_clicks"),
    Input("syn-btn-cancel", "n_clicks"),
    Input({"type": "syn-edit", "index": ALL}, "n_clicks"),
    State("syn-editing-id", "data"),
    prevent_initial_call=True,
)
def toggle_modal(n_add, n_cancel, n_edit, editing_id):
    trigger = ctx.triggered_id
    _empty_store = {"uids": [], "counter": 0, "initial_values": {}}

    if trigger == "syn-btn-cancel":
        return False, no_update, no_update, no_update, no_update, no_update, None, _empty_store, False

    if trigger == "syn-btn-add":
        return True, "Nueva fórmula sintética", None, None, 100, None, None, _empty_store, False

    if isinstance(trigger, dict) and trigger.get("type") == "syn-edit":
        f = next((x for x in svc.get_all_formulas() if x.id == trigger["index"]), None)
        if f is None:
            return no_update, no_update, no_update, no_update, no_update, no_update, \
                   no_update, no_update, no_update

        # Reconstruir uid-store con componentes existentes
        uids, ivs = [], {}
        for idx, c in enumerate(f.components):
            uids.append(idx)
            ivs[str(idx)] = {
                "asset_id": c.asset_id,
                "role":     c.role,
                "weight":   c.weight,
            }
        store = {"uids": uids, "counter": len(uids), "initial_values": ivs}
        bd = str(f.base_date) if f.base_date else None
        return (True, "Editar fórmula sintética",
                f.formula_type, f.asset_id, f.base_value or 100, bd,
                f.id, store, False)

    return no_update, no_update, no_update, no_update, no_update, no_update, \
           no_update, no_update, no_update


# ── Render componentes ────────────────────────────────────────────────────────
@callback(
    Output("syn-comp-header", "children"),
    Output("syn-comp-rows",   "children"),
    Input("syn-uid-store",    "data"),
    Input("syn-formula-type", "value"),
    State("syn-all-opts",     "data"),
)
def render_components(uid_store, ft, all_opts):
    uids = uid_store.get("uids", [])
    ivs  = uid_store.get("initial_values", {})
    is_ratio = (ft == "ratio")
    opts = all_opts or []

    # Cabecera de columnas
    w_col = {"width": "80px", "minWidth": "80px"}
    header = dbc.Row([
        dbc.Col(html.Small("Activo", className="text-muted"), md=True),
        dbc.Col(html.Small("Rol",    className="text-muted"),
                md=3, style={} if is_ratio else {"display": "none"}),
        dbc.Col(html.Small("Peso",   className="text-muted"), style=w_col),
        dbc.Col(style={"width": "32px", "minWidth": "32px"}),
    ], className="g-1 mb-1")

    rows = []
    for uid in uids:
        iv = ivs.get(str(uid), {})
        role_col = dbc.Col(
            dcc.Dropdown(
                id={"type": "syn-comp-role", "index": uid},
                options=_ROLE_OPTS,
                value=iv.get("role", "numerator" if is_ratio else "component"),
                clearable=False,
                style={"fontSize": "0.80rem"},
            ),
            md=3, style={} if is_ratio else {"display": "none"},
        )
        rows.append(dbc.Row([
            dbc.Col(
                dcc.Dropdown(
                    id={"type": "syn-comp-asset", "index": uid},
                    options=opts,
                    value=iv.get("asset_id"),
                    placeholder="Activo...",
                    style={"fontSize": "0.80rem"},
                ),
                md=True,
            ),
            role_col,
            dbc.Col(
                dbc.Input(
                    id={"type": "syn-comp-weight", "index": uid},
                    type="number",
                    value=iv.get("weight", 1.0),
                    min=0, step=0.01,
                    style={"fontSize": "0.80rem"},
                ),
                style=w_col,
            ),
            dbc.Col(
                dbc.Button("×", id={"type": "syn-remove-comp", "index": uid},
                           color="link", size="sm",
                           style={"color": "#ef4444", "padding": "0 6px",
                                  "lineHeight": 1, "fontSize": "1rem"}),
                style={"width": "32px", "minWidth": "32px"},
            ),
        ], className="g-1 mb-1 align-items-center"))

    return header, rows


# ── Añadir / quitar componente (sincroniza valores actuales al store) ─────────
@callback(
    Output("syn-uid-store", "data", allow_duplicate=True),
    Input("syn-btn-add-comp",                              "n_clicks"),
    Input({"type": "syn-remove-comp", "index": ALL},      "n_clicks"),
    State("syn-uid-store",                                 "data"),
    State({"type": "syn-comp-asset",  "index": ALL},      "value"),
    State({"type": "syn-comp-role",   "index": ALL},      "value"),
    State({"type": "syn-comp-weight", "index": ALL},      "value"),
    prevent_initial_call=True,
)
def update_comp_store(add_clicks, remove_clicks, store, assets, roles, weights):
    trigger  = ctx.triggered_id
    uids     = store.get("uids", [])
    counter  = store.get("counter", 0)

    # Sincronizar valores actuales del DOM al store
    ivs = {}
    for i, uid in enumerate(uids):
        ivs[str(uid)] = {
            "asset_id": assets[i] if i < len(assets) else None,
            "role":     roles[i]  if i < len(roles)  else "component",
            "weight":   weights[i] if i < len(weights) else 1.0,
        }

    if trigger == "syn-btn-add-comp":
        ivs[str(counter)] = {"asset_id": None, "role": "component", "weight": 1.0}
        uids = uids + [counter]
        counter += 1

    elif isinstance(trigger, dict) and trigger.get("type") == "syn-remove-comp":
        rem = trigger["index"]
        uids = [u for u in uids if u != rem]
        ivs.pop(str(rem), None)

    return {"uids": uids, "counter": counter, "initial_values": ivs}


# ── Preview de fórmula en texto ───────────────────────────────────────────────
@callback(
    Output("syn-formula-preview", "children"),
    Input("syn-uid-store",                             "data"),
    Input("syn-formula-type",                          "value"),
    Input("syn-f-asset",                               "value"),
    Input("syn-base-value",                            "value"),
    Input("syn-base-date",                             "date"),
    State({"type": "syn-comp-asset",  "index": ALL},  "value"),
    State({"type": "syn-comp-role",   "index": ALL},  "value"),
    State({"type": "syn-comp-weight", "index": ALL},  "value"),
    State("syn-all-opts",                              "data"),
    State("syn-f-asset",                               "options"),
)
def update_preview(uid_store, ft, dest_id, base_val, base_date,
                   assets, roles, weights, all_opts, dest_opts):
    if not ft:
        return "— seleccioná un tipo de fórmula —"

    def ticker(aid, opts):
        if not aid or not opts:
            return "?"
        for o in opts:
            if o["value"] == aid:
                return o["label"].split(" — ")[0]
        return "?"

    uids = uid_store.get("uids", [])
    dest = ticker(dest_id, dest_opts or [])

    parts_n, parts_d, parts_c = [], [], []
    for i, uid in enumerate(uids):
        aid = assets[i] if i < len(assets) else None
        role = roles[i] if i < len(roles) else "component"
        w = float(weights[i]) if (i < len(weights) and weights[i] is not None) else 1.0
        t = ticker(aid, all_opts)
        label = f"{w:g}×{t}" if w != 1 else t
        if role == "numerator":
            parts_n.append(label)
        elif role == "denominator":
            parts_d.append(label)
        else:
            parts_c.append((w, label))

    if ft == "ratio":
        n_str = " + ".join(parts_n) or "?"
        d_str = " + ".join(parts_d) or "?"
        return f"{dest} = ({n_str}) / ({d_str})"

    if ft == "weighted_avg":
        total_w = sum(w for w, _ in parts_c) or 1
        c_str = " + ".join(lbl for _, lbl in parts_c) or "?"
        return f"{dest} = ({c_str}) / {total_w:g}"

    if ft == "weighted_sum":
        c_str = " + ".join(lbl for _, lbl in parts_c) or "?"
        return f"{dest} = {c_str}"

    if ft == "index":
        total_w = sum(w for w, _ in parts_c) or 1
        c_str = " + ".join(f"{lbl}/P₀" for _, lbl in parts_c) or "?"
        bv = base_val or 100
        bd = base_date or "?"
        return f"{dest} = {bv:g} × ({c_str}) / {total_w:g}   [base: {bd}]"

    return "—"


# ── Guardar ───────────────────────────────────────────────────────────────────
@callback(
    Output("syn-alert",       "children"),
    Output("syn-alert",       "is_open"),
    Output("syn-alert",       "color"),
    Output("syn-modal",       "is_open",   allow_duplicate=True),
    Output("syn-modal-error", "children"),
    Output("syn-modal-error", "is_open"),
    Input("syn-btn-save",  "n_clicks"),
    State("syn-uid-store",                             "data"),
    State({"type": "syn-comp-asset",  "index": ALL},  "value"),
    State({"type": "syn-comp-role",   "index": ALL},  "value"),
    State({"type": "syn-comp-weight", "index": ALL},  "value"),
    State("syn-formula-type", "value"),
    State("syn-f-asset",      "value"),
    State("syn-base-value",   "value"),
    State("syn-base-date",    "date"),
    State("syn-editing-id",   "data"),
    prevent_initial_call=True,
)
def save(_, uid_store, assets, roles, weights, ft, dest_id,
         base_val, base_date, editing_id):
    no_err = (no_update, no_update, no_update, no_update, "", False)

    if not ft:
        return *no_err[:4], "Seleccioná un tipo de fórmula.", True
    if not dest_id:
        return *no_err[:4], "Seleccioná el activo destino.", True

    uids = uid_store.get("uids", [])
    if not uids:
        return *no_err[:4], "Agregá al menos un componente.", True

    if ft == "index" and not base_date:
        return *no_err[:4], "La fecha base es obligatoria para el tipo Índice.", True

    components = []
    for i, uid in enumerate(uids):
        aid = assets[i] if i < len(assets) else None
        if not aid:
            return *no_err[:4], f"Seleccioná el activo del componente {i + 1}.", True
        role = (roles[i] if i < len(roles) else None) or "component"
        w    = float(weights[i]) if (i < len(weights) and weights[i] is not None) else 1.0
        components.append({"asset_id": aid, "role": role, "weight": w})

    from datetime import date as _date
    bd = _date.fromisoformat(base_date) if base_date else None

    try:
        svc.save_formula(
            asset_id=dest_id,
            formula_type=ft,
            components=components,
            base_value=float(base_val) if base_val else None,
            base_date=bd,
            formula_id=editing_id,
        )
        return "Fórmula guardada.", True, "success", False, "", False
    except Exception as exc:
        return no_update, no_update, no_update, no_update, str(exc), True


# ── Eliminar ──────────────────────────────────────────────────────────────────
@callback(
    Output("syn-alert", "children", allow_duplicate=True),
    Output("syn-alert", "is_open",  allow_duplicate=True),
    Output("syn-alert", "color",    allow_duplicate=True),
    Input({"type": "syn-delete", "index": ALL}, "n_clicks"),
    prevent_initial_call=True,
)
def delete(n_clicks):
    trigger = ctx.triggered_id
    if not isinstance(trigger, dict) or not any(n_clicks):
        return no_update, no_update, no_update
    try:
        svc.delete_formula(trigger["index"])
        return "Fórmula eliminada.", True, "success"
    except Exception as exc:
        return str(exc), True, "danger"


# ── Calcular delta ────────────────────────────────────────────────────────────
@callback(
    Output("syn-alert", "children", allow_duplicate=True),
    Output("syn-alert", "is_open",  allow_duplicate=True),
    Output("syn-alert", "color",    allow_duplicate=True),
    Input({"type": "syn-delta", "index": ALL}, "n_clicks"),
    prevent_initial_call=True,
)
def calc_delta(n_clicks):
    trigger = ctx.triggered_id
    if not isinstance(trigger, dict) or not any(n_clicks):
        return no_update, no_update, no_update
    try:
        f = next((x for x in svc.get_all_formulas() if x.id == trigger["index"]), None)
        if f is None:
            return "Fórmula no encontrada.", True, "danger"
        count = svc.compute_synthetic_prices(f.asset_id, full=False)
        return f"Delta calculado: {count} precios insertados.", True, "success"
    except Exception as exc:
        return str(exc), True, "danger"


# ── Exportar fórmulas ────────────────────────────────────────────────────────

@callback(
    Output("syn-download", "data"),
    Input("syn-btn-export", "n_clicks"),
    prevent_initial_call=True,
)
def export_formulas(n_clicks):
    if not n_clicks:
        return no_update
    content = svc.export_formulas_excel()
    return dcc.send_bytes(content, "formulas_sinteticas.xlsx")


# ── Importar fórmulas ─────────────────────────────────────────────────────────

@callback(
    Output("syn-import-results", "children"),
    Output("syn-alert",          "children",  allow_duplicate=True),
    Output("syn-alert",          "is_open",   allow_duplicate=True),
    Output("syn-alert",          "color",     allow_duplicate=True),
    Input("syn-upload",          "contents"),
    State("syn-upload",          "filename"),
    prevent_initial_call=True,
)
def import_formulas(contents, filename):
    if contents is None:
        return no_update, no_update, no_update, no_update

    try:
        _header, encoded = contents.split(",", 1)
        file_bytes = base64.b64decode(encoded)
        results = svc.import_formulas_excel(file_bytes)
    except Exception as exc:
        return no_update, str(exc), True, "danger"

    imported = [r for r in results if r["status"] == "imported"]
    errors   = [r for r in results if r["status"] == "error"]

    _STATUS_COLOR = {"imported": "#4ade80", "error": "#f87171"}
    rows = [
        html.Tr([
            html.Td(r["ticker"], style=_td_s),
            html.Td(r["status"].capitalize(),
                    style={**_td_s, "color": _STATUS_COLOR.get(r["status"], "#9ca3af")}),
            html.Td(r["detail"], style={**_td_s, "fontSize": "0.75rem", "color": "#9ca3af"}),
        ])
        for r in results
    ]
    table = html.Table([
        html.Thead(html.Tr([
            html.Th("Ticker",  style=_th),
            html.Th("Estado",  style=_th),
            html.Th("Detalle", style=_th),
        ])),
        html.Tbody(rows),
    ], style={"width": "100%", "borderCollapse": "collapse"})

    msg   = f"Importación: {len(imported)} exitosa(s), {len(errors)} error(es)."
    color = "success" if not errors else ("warning" if imported else "danger")
    return table, msg, True, color


# ── Calcular completo ─────────────────────────────────────────────────────────
@callback(
    Output("syn-alert", "children", allow_duplicate=True),
    Output("syn-alert", "is_open",  allow_duplicate=True),
    Output("syn-alert", "color",    allow_duplicate=True),
    Input({"type": "syn-full", "index": ALL}, "n_clicks"),
    prevent_initial_call=True,
)
def calc_full(n_clicks):
    trigger = ctx.triggered_id
    if not isinstance(trigger, dict) or not any(n_clicks):
        return no_update, no_update, no_update
    try:
        f = next((x for x in svc.get_all_formulas() if x.id == trigger["index"]), None)
        if f is None:
            return "Fórmula no encontrada.", True, "danger"
        count = svc.compute_synthetic_prices(f.asset_id, full=True)
        return f"Recalculado completo: {count} precios insertados.", True, "success"
    except Exception as exc:
        return str(exc), True, "danger"
