import base64

from dash import ALL, Input, Output, State, callback, ctx, dcc, html, no_update
import dash_bootstrap_components as dbc

import app.services.strategy_service as svc
import app.services.signal_service as sig_svc
from app.pages.admin_strategies import _th, _td, _SCOPE_OPTS, _GROUP_TYPE_OPTS


# ── Cachear opciones de señales ───────────────────────────────────────────────

@callback(
    Output("str-signal-opts", "data"),
    Input("str-modal", "is_open"),
)
def cache_signal_opts(is_open):
    if not is_open:
        return no_update
    signals = sig_svc.get_all_signals()
    return [{"label": f"{s.key} — {s.name}", "value": s.key} for s in signals]


# ── Tabla ─────────────────────────────────────────────────────────────────────

@callback(
    Output("str-table-container", "children"),
    Output("str-all-ids",         "data"),
    Output("str-btn-edit",        "disabled"),
    Output("str-btn-delete",      "disabled"),
    Output("str-btn-calc",        "disabled"),
    Input("str-alert",            "is_open"),
    Input("str-modal",            "is_open"),
    Input("str-selected-ids",     "data"),
)
def load_table(_a, _m, selected_ids):
    selected_ids = selected_ids or []
    strategies = svc.get_all_strategies()
    all_ids = [s.id for s in strategies]
    n = len(selected_ids)

    if not strategies:
        return (html.P("Sin estrategias configuradas.", className="text-muted mt-2",
                       style={"fontSize": "0.82rem"}),
                all_ids, True, True, True)

    rows = []
    for strat in strategies:
        is_sel = strat.id in selected_ids
        rows.append(html.Tr([
            html.Td(
                dbc.Button(
                    html.I(className="fa fa-check-square" if is_sel else "fa fa-square-o"),
                    id={"type": "str-check", "index": strat.id},
                    color="link", size="sm",
                    style={"color": "#38bdf8" if is_sel else "#6b7280",
                           "padding": "2px 4px", "lineHeight": 1},
                ),
                style={**_td, "width": "32px", "padding": "2px"},
            ),
            html.Td(strat.name, style={**_td, "fontWeight": "500"}),
            html.Td(
                dbc.Badge(str(len(strat.components)), color="secondary"),
                style=_td,
            ),
            html.Td(strat.description or "—",
                    style={**_td, "color": "#9ca3af", "fontSize": "0.76rem",
                           "maxWidth": "320px", "overflow": "hidden",
                           "textOverflow": "ellipsis", "whiteSpace": "nowrap"}),
        ]))

    table = html.Table([
        html.Thead(html.Tr([
            html.Th("",           style={**_th, "width": "32px", "padding": "5px 2px"}),
            html.Th("Nombre",     style=_th),
            html.Th("Comp.",      style=_th),
            html.Th("Descripción",style=_th),
        ])),
        html.Tbody(rows),
    ], style={"width": "100%", "borderCollapse": "collapse"})

    return table, all_ids, (n != 1), (n == 0), (n == 0)


# ── Selección ─────────────────────────────────────────────────────────────────

@callback(
    Output("str-selected-ids", "data", allow_duplicate=True),
    Input({"type": "str-check", "index": ALL}, "n_clicks"),
    State("str-selected-ids", "data"),
    prevent_initial_call=True,
)
def toggle_check(clicks, selected_ids):
    if not any(n for n in clicks if n):
        return no_update
    trigger = ctx.triggered_id
    if not isinstance(trigger, dict):
        return no_update
    sid = trigger["index"]
    sel = list(selected_ids or [])
    if sid in sel:
        sel.remove(sid)
    else:
        sel.append(sid)
    return sel


# ── Modal: abrir / cerrar ─────────────────────────────────────────────────────

@callback(
    Output("str-modal",       "is_open"),
    Output("str-modal-title", "children"),
    Output("str-f-name",      "value"),
    Output("str-f-description", "value"),
    Output("str-editing-id",  "data"),
    Output("str-uid-store",   "data"),
    Output("str-modal-error", "is_open", allow_duplicate=True),
    Input("str-btn-add",      "n_clicks"),
    Input("str-btn-cancel",   "n_clicks"),
    Input("str-btn-edit",     "n_clicks"),
    State("str-selected-ids", "data"),
    prevent_initial_call=True,
)
def toggle_modal(n_add, n_cancel, n_edit, selected_ids):
    trigger = ctx.triggered_id
    _empty = {"uids": [], "counter": 0, "initial_values": {}}

    if trigger == "str-btn-cancel":
        return False, no_update, no_update, no_update, None, _empty, False

    if trigger == "str-btn-add":
        return True, "Nueva estrategia", "", "", None, _empty, False

    if trigger == "str-btn-edit":
        if not selected_ids or len(selected_ids) != 1:
            return no_update, no_update, no_update, no_update, no_update, no_update, no_update
        strat = next((x for x in svc.get_all_strategies() if x.id == selected_ids[0]), None)
        if strat is None:
            return no_update, no_update, no_update, no_update, no_update, no_update, no_update
        uids, ivs = [], {}
        for idx, comp in enumerate(strat.components):
            from app.models import SignalDefinition
            from app.database import get_session
            s = get_session()
            sig = s.query(SignalDefinition).filter(SignalDefinition.id == comp.signal_id).first()
            uids.append(idx)
            ivs[str(idx)] = {
                "signal_key": sig.key if sig else "",
                "weight":     comp.weight,
                "scope":      comp.scope or "",
                "group_type": comp.group_type or "",
                "group_id":   comp.group_id,
            }
        store = {"uids": uids, "counter": len(uids), "initial_values": ivs}
        return True, "Editar estrategia", strat.name, strat.description or "", strat.id, store, False

    return no_update, no_update, no_update, no_update, no_update, no_update, no_update


# ── Render filas de componentes ───────────────────────────────────────────────

@callback(
    Output("str-comp-rows",  "children"),
    Input("str-uid-store",   "data"),
    State("str-signal-opts", "data"),
)
def render_comp_rows(uid_store, signal_opts):
    uids = uid_store.get("uids", [])
    ivs  = uid_store.get("initial_values", {})
    opts = signal_opts or []

    rows = []
    for uid in uids:
        iv = ivs.get(str(uid), {})
        scope_val = iv.get("scope", "")
        rows.append(dbc.Row([
            dbc.Col(
                dcc.Dropdown(
                    id={"type": "str-comp-signal", "index": uid},
                    options=opts,
                    value=iv.get("signal_key"),
                    placeholder="Señal...",
                    style={"fontSize": "0.80rem"},
                ),
                md=4,
            ),
            dbc.Col(
                dbc.Input(
                    id={"type": "str-comp-weight", "index": uid},
                    type="number", value=iv.get("weight", 1.0),
                    min=0, step=0.01,
                    style={"fontSize": "0.80rem"},
                ),
                md=2,
            ),
            dbc.Col(
                dcc.Dropdown(
                    id={"type": "str-comp-scope", "index": uid},
                    options=_SCOPE_OPTS,
                    value=scope_val,
                    clearable=False,
                    style={"fontSize": "0.80rem"},
                ),
                md=3,
            ),
            dbc.Col(
                dcc.Dropdown(
                    id={"type": "str-comp-group-type", "index": uid},
                    options=_GROUP_TYPE_OPTS,
                    value=iv.get("group_type") or None,
                    placeholder="Tipo...",
                    style={"fontSize": "0.80rem",
                           "display": "block" if scope_val else "none"},
                ),
                md=2,
            ),
            dbc.Col(
                dbc.Button("×", id={"type": "str-remove-comp", "index": uid},
                           color="link", size="sm",
                           style={"color": "#ef4444", "padding": "0 6px",
                                  "lineHeight": 1, "fontSize": "1rem"}),
                style={"width": "32px"},
            ),
        ], className="g-1 mb-1 align-items-center"))

    return rows


# ── Añadir / quitar componente ────────────────────────────────────────────────

@callback(
    Output("str-uid-store", "data", allow_duplicate=True),
    Input("str-btn-add-comp",                               "n_clicks"),
    Input({"type": "str-remove-comp", "index": ALL},        "n_clicks"),
    State("str-uid-store",                                  "data"),
    State({"type": "str-comp-signal",    "index": ALL},     "value"),
    State({"type": "str-comp-weight",    "index": ALL},     "value"),
    State({"type": "str-comp-scope",     "index": ALL},     "value"),
    State({"type": "str-comp-group-type","index": ALL},     "value"),
    prevent_initial_call=True,
)
def update_comp_store(add_n, remove_ns, store, signals, weights, scopes, group_types):
    trigger  = ctx.triggered_id
    uids     = store.get("uids", [])
    counter  = store.get("counter", 0)

    ivs = {}
    for i, uid in enumerate(uids):
        ivs[str(uid)] = {
            "signal_key": signals[i]     if i < len(signals)     else None,
            "weight":     weights[i]     if i < len(weights)     else 1.0,
            "scope":      scopes[i]      if i < len(scopes)      else "",
            "group_type": group_types[i] if i < len(group_types) else None,
        }

    if trigger == "str-btn-add-comp":
        ivs[str(counter)] = {"signal_key": None, "weight": 1.0, "scope": "", "group_type": None}
        uids = uids + [counter]
        counter += 1
    elif isinstance(trigger, dict) and trigger.get("type") == "str-remove-comp":
        if not any(n for n in remove_ns if n):
            return no_update
        rem = trigger["index"]
        uids = [u for u in uids if u != rem]
        ivs.pop(str(rem), None)

    return {"uids": uids, "counter": counter, "initial_values": ivs}


# ── Guardar ───────────────────────────────────────────────────────────────────

@callback(
    Output("str-alert",       "children"),
    Output("str-alert",       "is_open"),
    Output("str-alert",       "color"),
    Output("str-modal",       "is_open",  allow_duplicate=True),
    Output("str-modal-error", "children"),
    Output("str-modal-error", "is_open"),
    Output("str-selected-ids","data",     allow_duplicate=True),
    Input("str-btn-save",     "n_clicks"),
    State("str-f-name",       "value"),
    State("str-f-description","value"),
    State("str-uid-store",    "data"),
    State({"type": "str-comp-signal",    "index": ALL}, "value"),
    State({"type": "str-comp-weight",    "index": ALL}, "value"),
    State({"type": "str-comp-scope",     "index": ALL}, "value"),
    State({"type": "str-comp-group-type","index": ALL}, "value"),
    State("str-editing-id",   "data"),
    prevent_initial_call=True,
)
def save(_, name, description, uid_store, signals, weights, scopes, group_types, editing_id):

    def err(msg):
        return no_update, no_update, no_update, no_update, msg, True, no_update

    if not name or not name.strip():
        return err("El nombre es obligatorio.")

    uids = uid_store.get("uids", [])
    if not uids:
        return err("Agregá al menos un componente.")

    components = []
    for i, uid in enumerate(uids):
        sig_key = signals[i] if i < len(signals) else None
        if not sig_key:
            return err(f"Seleccioná la señal del componente {i + 1}.")
        weight  = float(weights[i]) if (i < len(weights) and weights[i] is not None) else 1.0
        scope   = scopes[i] if i < len(scopes) else ""
        gtype   = group_types[i] if i < len(group_types) else None
        components.append({
            "signal_key": sig_key,
            "weight":     weight,
            "scope":      scope or None,
            "group_type": gtype or None,
            "group_id":   None,
        })

    try:
        svc.save_strategy(
            name=name.strip(),
            description=description or None,
            components=components,
            strategy_id=editing_id,
        )
        return "Estrategia guardada.", True, "success", False, "", False, []
    except Exception as exc:
        return err(str(exc))


# ── Eliminar ──────────────────────────────────────────────────────────────────

@callback(
    Output("str-alert",       "children",  allow_duplicate=True),
    Output("str-alert",       "is_open",   allow_duplicate=True),
    Output("str-alert",       "color",     allow_duplicate=True),
    Output("str-selected-ids","data",      allow_duplicate=True),
    Input("str-btn-delete",   "n_clicks"),
    State("str-selected-ids", "data"),
    prevent_initial_call=True,
)
def delete_selected(_, selected_ids):
    if not selected_ids:
        return no_update, no_update, no_update, no_update
    errors, ok = [], 0
    for sid in selected_ids:
        try:
            svc.delete_strategy(sid)
            ok += 1
        except Exception as exc:
            errors.append(str(exc))
    if errors:
        return "; ".join(errors), True, "danger", []
    return f"{ok} estrategia(s) eliminada(s).", True, "success", []


# ── Calcular resultados ───────────────────────────────────────────────────────

@callback(
    Output("str-status",  "children",  allow_duplicate=True),
    Output("str-alert",   "children",  allow_duplicate=True),
    Output("str-alert",   "is_open",   allow_duplicate=True),
    Output("str-alert",   "color",     allow_duplicate=True),
    Input("str-btn-calc", "n_clicks"),
    State("str-selected-ids", "data"),
    State("str-calc-date",    "date"),
    prevent_initial_call=True,
)
def calc_results(_, selected_ids, date_str):
    from datetime import date as dt_date
    if not selected_ids:
        return no_update, no_update, no_update, no_update
    snap_date = dt_date.fromisoformat(date_str) if date_str else dt_date.today()
    total, errors = 0, []
    for sid in selected_ids:
        try:
            total += svc.compute_strategy_results(sid, snap_date)
        except Exception as exc:
            errors.append(str(exc))
    if errors:
        return "", "; ".join(errors), True, "danger"
    return "", f"Calculados {total} resultado(s) para {snap_date}.", True, "success"


# ── Exportar ──────────────────────────────────────────────────────────────────

@callback(
    Output("str-download", "data"),
    Input("str-btn-export", "n_clicks"),
    prevent_initial_call=True,
)
def export(_):
    return dcc.send_bytes(svc.export_strategies_excel(), "estrategias.xlsx")


# ── Importar ──────────────────────────────────────────────────────────────────

@callback(
    Output("str-import-results", "children"),
    Output("str-alert",          "children",  allow_duplicate=True),
    Output("str-alert",          "is_open",   allow_duplicate=True),
    Output("str-alert",          "color",     allow_duplicate=True),
    Input("str-upload",          "contents"),
    State("str-upload",          "filename"),
    prevent_initial_call=True,
)
def import_excel(contents, filename):
    if contents is None:
        return no_update, no_update, no_update, no_update
    try:
        _, encoded = contents.split(",", 1)
        results = svc.import_strategies_excel(base64.b64decode(encoded))
    except Exception as exc:
        return no_update, str(exc), True, "danger"

    ok_count  = sum(1 for r in results if r["status"] == "ok")
    err_count = sum(1 for r in results if r["status"] == "error")
    _COLOR = {"ok": "#4ade80", "error": "#f87171"}

    rows = [
        html.Tr([
            html.Td(r["name"],   style=_td),
            html.Td(r["status"].upper(),
                    style={**_td, "color": _COLOR.get(r["status"], "#9ca3af")}),
            html.Td(r["detail"], style={**_td, "fontSize": "0.75rem", "color": "#9ca3af"}),
        ])
        for r in results
    ]
    table = html.Table([
        html.Thead(html.Tr([html.Th("Nombre", style=_th), html.Th("Estado", style=_th),
                             html.Th("Detalle", style=_th)])),
        html.Tbody(rows),
    ], style={"width": "100%", "borderCollapse": "collapse"})

    msg   = f"Importación: {ok_count} OK, {err_count} error(es)."
    color = "success" if not err_count else ("warning" if ok_count else "danger")
    return table, msg, True, color
