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
    Output("syn-formula-help", "children"),
    Output("syn-index-params", "style"),
    Input("syn-formula-type",  "value"),
)
def update_help(ft):
    show_index = {"display": "block"} if ft == "index" else {"display": "none"}
    return _help_card(ft), show_index


# ── Tabla principal ───────────────────────────────────────────────────────────

@callback(
    Output("syn-table-container",  "children"),
    Output("syn-btn-edit-sel",     "disabled"),
    Output("syn-btn-calc-sel",     "disabled"),
    Output("syn-btn-full-sel",     "disabled"),
    Output("syn-btn-delete-sel",   "disabled"),
    Output("syn-formula-ids",      "data"),
    Input("syn-alert",             "is_open"),
    Input("syn-modal",             "is_open"),
    Input("syn-selected-ids",      "data"),
)
def load_table(_a, _m, selected_ids):
    selected_ids = selected_ids or []
    formulas = svc.get_all_formulas()
    formula_ids = [f.id for f in formulas]

    n_sel = len(selected_ids)
    btn_edit    = (n_sel != 1)
    btn_calc    = (n_sel == 0)
    btn_full    = (n_sel == 0)
    btn_delete  = (n_sel == 0)

    if not formulas:
        empty = html.P("Sin activos sintéticos configurados.",
                       className="text-muted mt-2", style={"fontSize": "0.82rem"})
        return empty, btn_edit, btn_calc, btn_full, btn_delete, formula_ids

    _TYPE_LABELS = {
        "ratio":        "Ratio",
        "weighted_avg": "Prom. ponderado",
        "weighted_sum": "Suma ponderada",
        "index":        "Índice base",
    }
    rows = []
    for f in formulas:
        is_sel = f.id in selected_ids
        rows.append(html.Tr([
            html.Td(
                dbc.Button(
                    html.I(className="fa fa-check-square" if is_sel else "fa fa-square-o"),
                    id={"type": "syn-check", "index": f.id},
                    color="link", size="sm",
                    style={"color": "#38bdf8" if is_sel else "#6b7280",
                           "padding": "2px 4px", "lineHeight": 1},
                ),
                style={**_td_s, "width": "32px", "padding": "2px"},
            ),
            html.Td(f.asset.ticker if f.asset else "—", style=_td_s),
            html.Td(f.asset.name   if f.asset else "—",
                    style={**_td_s, "color": "#9ca3af", "fontSize": "0.76rem"}),
            html.Td(_TYPE_LABELS.get(f.formula_type, f.formula_type), style=_td_s),
            html.Td(svc.formula_preview_str(f),
                    style={**_td_s, "fontFamily": "monospace", "fontSize": "0.74rem",
                           "color": "#94a3b8", "maxWidth": "280px",
                           "overflow": "hidden", "textOverflow": "ellipsis",
                           "whiteSpace": "nowrap"}),
        ]))

    table = html.Table([
        html.Thead(html.Tr([
            html.Th("",         style={**_th, "width": "32px", "padding": "5px 2px"}),
            html.Th("Ticker",   style=_th),
            html.Th("Nombre",   style=_th),
            html.Th("Tipo",     style=_th),
            html.Th("Fórmula",  style=_th),
        ])),
        html.Tbody(rows),
    ], style={"width": "100%", "borderCollapse": "collapse"})

    return table, btn_edit, btn_calc, btn_full, btn_delete, formula_ids


# ── Selección de filas ────────────────────────────────────────────────────────

@callback(
    Output("syn-selected-ids", "data", allow_duplicate=True),
    Input({"type": "syn-check", "index": ALL}, "n_clicks"),
    State("syn-selected-ids", "data"),
    prevent_initial_call=True,
)
def toggle_checkbox(check_clicks, selected_ids):
    if not any(n for n in check_clicks if n):
        return no_update
    trigger = ctx.triggered_id
    if not isinstance(trigger, dict):
        return no_update
    fid = trigger["index"]
    selected = list(selected_ids or [])
    if fid in selected:
        selected.remove(fid)
    else:
        selected.append(fid)
    return selected


@callback(
    Output("syn-selected-ids", "data", allow_duplicate=True),
    Input("syn-btn-select-all", "n_clicks"),
    State("syn-formula-ids",    "data"),
    prevent_initial_call=True,
)
def select_all(_, formula_ids):
    return formula_ids or []


@callback(
    Output("syn-selected-ids", "data", allow_duplicate=True),
    Input("syn-btn-deselect-all", "n_clicks"),
    prevent_initial_call=True,
)
def deselect_all(_):
    return []


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
    Input("syn-btn-add",       "n_clicks"),
    Input("syn-btn-cancel",    "n_clicks"),
    Input("syn-btn-edit-sel",  "n_clicks"),
    State("syn-selected-ids",  "data"),
    State("syn-editing-id",    "data"),
    prevent_initial_call=True,
)
def toggle_modal(n_add, n_cancel, n_edit_sel, selected_ids, editing_id):
    trigger = ctx.triggered_id
    _empty = {"uids": [], "counter": 0, "initial_values": {}}
    _noup9 = (no_update,) * 9

    if trigger == "syn-btn-cancel":
        return False, no_update, no_update, no_update, no_update, no_update, None, _empty, False

    if trigger == "syn-btn-add":
        return True, "Nueva fórmula sintética", None, None, 100, None, None, _empty, False

    if trigger == "syn-btn-edit-sel":
        if not selected_ids or len(selected_ids) != 1:
            return *_noup9,
        f = next((x for x in svc.get_all_formulas() if x.id == selected_ids[0]), None)
        if f is None:
            return *_noup9,
        uids, ivs = [], {}
        for idx, c in enumerate(f.components):
            uids.append(idx)
            ivs[str(idx)] = {"asset_id": c.asset_id, "role": c.role, "weight": c.weight}
        store = {"uids": uids, "counter": len(uids), "initial_values": ivs}
        bd = str(f.base_date) if f.base_date else None
        return (True, "Editar fórmula sintética",
                f.formula_type, f.asset_id, f.base_value or 100, bd,
                f.id, store, False)

    return *_noup9,


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


# ── Añadir / quitar componente ────────────────────────────────────────────────

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
    trigger = ctx.triggered_id
    uids    = store.get("uids", [])
    counter = store.get("counter", 0)

    # Sincronizar valores actuales al store antes de añadir/quitar
    ivs = {}
    for i, uid in enumerate(uids):
        ivs[str(uid)] = {
            "asset_id": assets[i]  if i < len(assets)  else None,
            "role":     roles[i]   if i < len(roles)   else "component",
            "weight":   weights[i] if i < len(weights) else 1.0,
        }

    if trigger == "syn-btn-add-comp":
        ivs[str(counter)] = {"asset_id": None, "role": "component", "weight": 1.0}
        uids = uids + [counter]
        counter += 1

    elif isinstance(trigger, dict) and trigger.get("type") == "syn-remove-comp":
        if not any(n for n in remove_clicks if n):
            return no_update
        rem = trigger["index"]
        uids = [u for u in uids if u != rem]
        ivs.pop(str(rem), None)

    return {"uids": uids, "counter": counter, "initial_values": ivs}


# ── Preview de fórmula en tiempo real ────────────────────────────────────────

@callback(
    Output("syn-formula-preview",                          "children"),
    Input("syn-uid-store",                                 "data"),
    Input("syn-formula-type",                              "value"),
    Input("syn-f-asset",                                   "value"),
    Input("syn-base-value",                                "value"),
    Input("syn-base-date",                                 "date"),
    Input({"type": "syn-comp-asset",  "index": ALL},      "value"),
    Input({"type": "syn-comp-role",   "index": ALL},      "value"),
    Input({"type": "syn-comp-weight", "index": ALL},      "value"),
    State("syn-all-opts",                                  "data"),
    State("syn-f-asset",                                   "options"),
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
        aid  = assets[i]  if i < len(assets)  else None
        role = roles[i]   if i < len(roles)   else "component"
        w    = float(weights[i]) if (i < len(weights) and weights[i] is not None) else 1.0
        t    = ticker(aid, all_opts)
        label = f"{w:g}×{t}" if w != 1 else t
        if role == "numerator":
            parts_n.append(label)
        elif role == "denominator":
            parts_d.append(label)
        else:
            parts_c.append((w, label))

    if ft == "ratio":
        return f"{dest} = ({' + '.join(parts_n) or '?'}) / ({' + '.join(parts_d) or '?'})"
    if ft == "weighted_avg":
        total_w = sum(w for w, _ in parts_c) or 1
        c_str = " + ".join(lbl for _, lbl in parts_c) or "?"
        return f"{dest} = ({c_str}) / {total_w:g}"
    if ft == "weighted_sum":
        return f"{dest} = {(' + '.join(lbl for _, lbl in parts_c)) or '?'}"
    if ft == "index":
        total_w = sum(w for w, _ in parts_c) or 1
        c_str = " + ".join(f"{lbl}/P₀" for _, lbl in parts_c) or "?"
        bv = base_val or 100
        bd = base_date or "?"
        return f"{dest} = {bv:g} × ({c_str}) / {total_w:g}   [base: {bd}]"
    return "—"


# ── Guardar ───────────────────────────────────────────────────────────────────

@callback(
    Output("syn-alert",        "children"),
    Output("syn-alert",        "is_open"),
    Output("syn-alert",        "color"),
    Output("syn-modal",        "is_open",  allow_duplicate=True),
    Output("syn-modal-error",  "children"),
    Output("syn-modal-error",  "is_open"),
    Output("syn-selected-ids", "data",    allow_duplicate=True),
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
    _no_close = (no_update, no_update, no_update, no_update, "", False, no_update)

    if not ft:
        return *_no_close[:4], "Seleccioná un tipo de fórmula.", True, no_update
    if not dest_id:
        return *_no_close[:4], "Seleccioná el activo destino.", True, no_update

    # Evitar pisar una fórmula existente al crear nueva
    if not editing_id:
        existing = svc.get_formula_by_asset(dest_id)
        if existing:
            return *_no_close[:4], (
                "Este activo ya tiene una fórmula configurada. "
                "Seleccionalo en la tabla y usá Editar para modificarla."
            ), True, no_update

    uids = uid_store.get("uids", [])
    if not uids:
        return *_no_close[:4], "Agregá al menos un componente.", True, no_update
    if ft == "index" and not base_date:
        return *_no_close[:4], "La fecha base es obligatoria para el tipo Índice.", True, no_update

    components = []
    for i, uid in enumerate(uids):
        aid = assets[i] if i < len(assets) else None
        if not aid:
            return *_no_close[:4], f"Seleccioná el activo del componente {i + 1}.", True, no_update
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
        return "Fórmula guardada.", True, "success", False, "", False, []
    except Exception as exc:
        return no_update, no_update, no_update, no_update, str(exc), True, no_update


# ── Eliminar seleccionados ────────────────────────────────────────────────────

@callback(
    Output("syn-alert",        "children",  allow_duplicate=True),
    Output("syn-alert",        "is_open",   allow_duplicate=True),
    Output("syn-alert",        "color",     allow_duplicate=True),
    Output("syn-selected-ids", "data",      allow_duplicate=True),
    Input("syn-btn-delete-sel", "n_clicks"),
    State("syn-selected-ids",   "data"),
    prevent_initial_call=True,
)
def delete_selected(_, selected_ids):
    if not selected_ids:
        return no_update, no_update, no_update, no_update
    errors = []
    for fid in selected_ids:
        try:
            svc.delete_formula(fid)
        except Exception as exc:
            errors.append(str(exc))
    if errors:
        return "; ".join(errors), True, "danger", []
    n = len(selected_ids)
    return f"{n} fórmula(s) eliminada(s).", True, "success", []


# ── Calcular delta (seleccionados) ────────────────────────────────────────────

@callback(
    Output("syn-alert",       "children",  allow_duplicate=True),
    Output("syn-alert",       "is_open",   allow_duplicate=True),
    Output("syn-alert",       "color",     allow_duplicate=True),
    Output("syn-calc-status", "children",  allow_duplicate=True),
    Input("syn-btn-calc-sel", "n_clicks"),
    State("syn-selected-ids", "data"),
    prevent_initial_call=True,
)
def calc_delta_selected(_, selected_ids):
    if not selected_ids:
        return no_update, no_update, no_update, no_update
    formulas = [x for x in svc.get_all_formulas() if x.id in selected_ids]
    total, errors = 0, []
    for f in formulas:
        try:
            total += svc.compute_synthetic_prices(f.asset_id, full=False)
        except Exception as exc:
            errors.append(f"{f.asset.ticker if f.asset else f.id}: {exc}")
    if errors:
        return "; ".join(errors), True, "danger", ""
    return f"Delta calculado: {total} precio(s) insertado(s).", True, "success", ""


# ── Calcular completo (seleccionados) ─────────────────────────────────────────

@callback(
    Output("syn-alert",       "children",  allow_duplicate=True),
    Output("syn-alert",       "is_open",   allow_duplicate=True),
    Output("syn-alert",       "color",     allow_duplicate=True),
    Output("syn-calc-status", "children",  allow_duplicate=True),
    Input("syn-btn-full-sel", "n_clicks"),
    State("syn-selected-ids", "data"),
    prevent_initial_call=True,
)
def calc_full_selected(_, selected_ids):
    if not selected_ids:
        return no_update, no_update, no_update, no_update
    formulas = [x for x in svc.get_all_formulas() if x.id in selected_ids]
    total, errors = 0, []
    for f in formulas:
        try:
            total += svc.compute_synthetic_prices(f.asset_id, full=True)
        except Exception as exc:
            errors.append(f"{f.asset.ticker if f.asset else f.id}: {exc}")
    if errors:
        return "; ".join(errors), True, "danger", ""
    return f"Recálculo completo: {total} precio(s) insertado(s).", True, "success", ""


# ── Exportar fórmulas ─────────────────────────────────────────────────────────

@callback(
    Output("syn-download", "data"),
    Input("syn-btn-export", "n_clicks"),
    prevent_initial_call=True,
)
def export_formulas(n_clicks):
    if not n_clicks:
        return no_update
    return dcc.send_bytes(svc.export_formulas_excel(), "formulas_sinteticas.xlsx")


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
        results = svc.import_formulas_excel(base64.b64decode(encoded))
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
