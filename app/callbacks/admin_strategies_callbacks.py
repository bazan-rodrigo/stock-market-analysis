import base64

from dash import ALL, Input, Output, State, callback, ctx, dcc, html, no_update
import dash_bootstrap_components as dbc

import app.services.strategy_service as svc
import app.services.signal_service as sig_svc
from app.services.visibility import can_edit, current_viewer, publica_str
from app.callbacks.strategy_filter_ui import (
    empty_filter_store, store_to_tree, tree_to_store,
)
from app.pages.admin_strategies import _SCOPE_OPTS, _GROUP_TYPE_OPTS
from app.components.ui_constants import TH as _th, TD as _td


def _visible_strategies():
    return svc.get_visible_strategies(*current_viewer())


# ── Cachear opciones de señales ───────────────────────────────────────────────

@callback(
    Output("str-signal-opts", "data"),
    Input("str-modal", "is_open"),
)
def cache_signal_opts(is_open):
    if not is_open:
        return no_update
    signals = sig_svc.get_visible_signals(*current_viewer())
    return [{"label": f"{s.key} — {s.name}", "value": s.key} for s in signals]


# ── Tabla ─────────────────────────────────────────────────────────────────────

@callback(
    Output("str-datatable",  "data"),
    Output("str-datatable",  "selected_rows"),
    Output("str-all-ids",    "data"),
    Input("str-alert",       "is_open"),
    Input("str-modal",       "is_open"),
)
def load_table(_a, _m):
    from app.database import get_session
    from app.models import User
    strategies = _visible_strategies()
    owners = {u.id: u.username
              for u in get_session().query(User.id, User.username).all()}
    all_ids = [s.id for s in strategies]
    data = [
        {
            "id":          s.id,
            "name":        s.name,
            "components":  len(s.components),
            "filter":      "sí" if s.filter_conditions else "—",
            "owner":       owners.get(s.owner_id, "—"),
            "publica":     publica_str(s.is_public),
            "description": s.description or "—",
        }
        for s in strategies
    ]
    return data, [], all_ids


# ── Selección ─────────────────────────────────────────────────────────────────

@callback(
    Output("str-selected-ids", "data"),
    Input("str-datatable",     "selected_rows"),
    State("str-datatable",     "data"),
    prevent_initial_call=True,
)
def update_selected_ids(selected_rows, data):
    if not selected_rows or not data:
        return []
    return [data[i]["id"] for i in selected_rows]


@callback(
    Output("str-btn-edit",    "disabled"),
    Output("str-btn-delete",  "disabled"),
    Output("str-btn-calc",    "disabled"),
    Output("str-btn-history", "disabled"),
    Input("str-selected-ids", "data"),
)
def update_buttons(selected_ids):
    n = len(selected_ids or [])
    if n == 0:
        return True, True, True, True
    # Acciones solo sobre estrategias propias (o admin)
    user_id, is_admin = current_viewer()
    by_id = {s.id: s for s in _visible_strategies()}
    editable = all(
        sid in by_id and can_edit(by_id[sid].owner_id, user_id, is_admin)
        for sid in selected_ids
    )
    return (n != 1 or not editable), not editable, not editable, \
           (n != 1 or not editable)


# ── Modal: abrir / cerrar ─────────────────────────────────────────────────────

@callback(
    Output("str-modal",       "is_open"),
    Output("str-modal-title", "children"),
    Output("str-f-name",      "value"),
    Output("str-f-description", "value"),
    Output("str-f-public",    "value"),
    Output("str-editing-id",  "data"),
    Output("str-uid-store",   "data"),
    Output("str-filter-store","data"),
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
        return (False, no_update, no_update, no_update, no_update, None,
                _empty, empty_filter_store(), False)

    if trigger == "str-btn-add":
        return (True, "Nueva estrategia", "", "", False, None,
                _empty, empty_filter_store(), False)

    if trigger == "str-btn-edit":
        if not selected_ids or len(selected_ids) != 1:
            return (no_update,) * 9
        strat = next((x for x in _visible_strategies()
                      if x.id == selected_ids[0]), None)
        if strat is None:
            return (no_update,) * 9
        from app.models import SignalDefinition
        from app.database import get_session
        s = get_session()
        signal_ids = [comp.signal_id for comp in strat.components]
        sigs_by_id = {
            sig.id: sig
            for sig in s.query(SignalDefinition).filter(SignalDefinition.id.in_(signal_ids)).all()
        } if signal_ids else {}
        uids, ivs = [], {}
        for idx, comp in enumerate(strat.components):
            sig = sigs_by_id.get(comp.signal_id)
            uids.append(idx)
            ivs[str(idx)] = {
                "signal_key": sig.key if sig else "",
                "weight":     comp.weight,
                "scope":      comp.scope or "",
                "group_type": comp.group_type or "",
                "group_id":   comp.group_id,
            }
        store = {"uids": uids, "counter": len(uids), "initial_values": ivs}
        return (True, "Editar estrategia", strat.name, strat.description or "",
                bool(strat.is_public), strat.id, store,
                tree_to_store(strat.filter_conditions), False)

    return (no_update,) * 9


# ── Render filas de componentes ───────────────────────────────────────────────

@callback(
    Output("str-comp-rows",  "children"),
    Input("str-uid-store",   "data"),
    # Input (no State): al abrir el modal las filas se renderizan antes de
    # que cache_signal_opts termine — cuando las opciones llegan, hay que
    # re-renderizar o los dropdowns quedan vacíos hasta reabrir
    Input("str-signal-opts", "data"),
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
                           style={"color": "#ef5350", "padding": "0 6px",
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
    State("str-f-public",     "value"),
    State("str-uid-store",    "data"),
    State({"type": "str-comp-signal",    "index": ALL}, "value"),
    State({"type": "str-comp-weight",    "index": ALL}, "value"),
    State({"type": "str-comp-scope",     "index": ALL}, "value"),
    State({"type": "str-comp-group-type","index": ALL}, "value"),
    State("str-editing-id",   "data"),
    State("str-filter-store", "data"),
    State("str-filter-opts",  "data"),
    State({"type": "strf-left", "index": ALL}, "value"),
    State({"type": "strf-left", "index": ALL}, "id"),
    State({"type": "strf-op",   "index": ALL}, "value"),
    State({"type": "strf-op",   "index": ALL}, "id"),
    State({"type": "strf-val",  "index": ALL}, "value"),
    State({"type": "strf-val",  "index": ALL}, "id"),
    State({"type": "strf-vs",   "index": ALL}, "value"),
    State({"type": "strf-vs",   "index": ALL}, "id"),
    prevent_initial_call=True,
)
def save(_, name, description, is_public, uid_store,
         signals, weights, scopes, group_types,
         editing_id, filter_store, filter_opts,
         f_lefts, f_ids_left, f_ops, f_ids_op, f_vals, f_ids_val, f_vss, f_ids_vs):

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

    # Filtro de elegibilidad: volcar los controles al store y serializar
    from app.callbacks.strategy_filter_ui import _capture_fields
    filter_conditions = None
    if filter_store:
        filter_store, _ = _capture_fields(
            filter_store, f_ids_left, f_lefts, f_ids_op, f_ops,
            f_ids_val, f_vals, f_ids_vs, f_vss)
        no_hist = set((filter_opts or {}).get("no_hist", []))
        filter_conditions, f_errors = store_to_tree(filter_store, no_hist)
        if f_errors:
            return err(" ".join(f_errors))

    user_id, is_admin = current_viewer()
    try:
        svc.save_strategy(
            name=name.strip(),
            description=description or None,
            components=components,
            filter_conditions=filter_conditions,
            strategy_id=editing_id,
            is_public=bool(is_public),
            acting_user_id=user_id,
            acting_is_admin=is_admin,
        )
        # Una edición cambia una definición ya calculada: un delta solo toca la
        # última fecha, así que para aplicar el cambio a TODA la historia hace
        # falta "Recalcular completo" (recalcula señales y estrategias). En un
        # alta no hay historia previa: alcanza con "Calcular historia" (delta).
        nombre = name.strip()
        if editing_id:
            msg = (f"Estrategia «{nombre}» guardada. Cambió una definición ya "
                   f"calculada: corré «Recalcular completo» (Centro de Datos → "
                   f"Señales y Estrategias) para aplicar el cambio a toda la "
                   f"historia. A recalcular: la estrategia «{nombre}».")
        else:
            msg = (f"Estrategia «{nombre}» guardada. Corré «Calcular historia» "
                   f"para poblar sus resultados.")
        return msg, True, "success", False, "", False, []
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
    user_id, is_admin = current_viewer()
    errors, ok = [], 0
    for sid in selected_ids:
        try:
            svc.delete_strategy(sid, acting_user_id=user_id,
                                acting_is_admin=is_admin)
            ok += 1
        except Exception as exc:
            errors.append(str(exc))
    if errors:
        return "; ".join(errors), True, "danger", []
    return f"{ok} estrategia(s) eliminada(s).", True, "success", []


# ── Calcular resultados ───────────────────────────────────────────────────────

@callback(
    Output("str-status",       "children",  allow_duplicate=True),
    Output("str-alert",        "children",  allow_duplicate=True),
    Output("str-alert",        "is_open",   allow_duplicate=True),
    Output("str-alert",        "color",     allow_duplicate=True),
    Output("str-calc-preview", "children"),
    Input("str-btn-calc",      "n_clicks"),
    State("str-selected-ids",  "data"),
    State("str-calc-date",     "date"),
    prevent_initial_call=True,
)
def calc_results(_, selected_ids, date_str):
    from datetime import date as dt_date
    if not selected_ids:
        return no_update, no_update, no_update, no_update, no_update
    user_id, is_admin = current_viewer()
    by_id = {s.id: s for s in _visible_strategies()}
    target_date = dt_date.fromisoformat(date_str) if date_str else dt_date.today()
    total, errors = 0, []
    for sid in selected_ids:
        strat = by_id.get(sid)
        if strat is None or not can_edit(strat.owner_id, user_id, is_admin):
            errors.append(f"estrategia id={sid}: solo el dueño o un "
                          f"administrador pueden calcular resultados")
            continue
        try:
            total += svc.compute_strategy_results(sid, target_date)
        except Exception as exc:
            errors.append(str(exc))
    if errors:
        return "", "; ".join(errors), True, "danger", html.Div()

    # Aviso in-sample: alguna estrategia filtra con resolution=current (valor
    # vigente) sobre una fecha pasada → sesgo de anticipación deliberado
    insample_alert = None
    if target_date < dt_date.today():
        from app.services import strategy_filter as sf
        biased = [
            strat.name
            for sid in selected_ids
            if (strat := svc.get_strategy_by_id(sid)) is not None
            and sf.uses_current_resolution(sf.parse_tree(strat.filter_conditions))
        ]
        if biased:
            insample_alert = dbc.Alert(
                [html.Strong("Diagnóstico in-sample: "),
                 f"el filtro de {', '.join(biased)} usa valores vigentes "
                 f"(sin historia) sobre una fecha pasada — los resultados "
                 f"tienen sesgo de anticipación y no sirven como backtest."],
                color="warning", className="py-2 small mb-2",
            )

    # Preview: top 10 de la primera (o única) estrategia seleccionada
    preview = html.Div()
    if len(selected_ids) == 1:
        results = svc.get_strategy_results(selected_ids[0], target_date)
        if results:
            top = results[:10]
            strat = svc.get_strategy_by_id(selected_ids[0])
            strat_name = strat.name if strat else f"#{selected_ids[0]}"
            rows = [
                html.Tr([
                    html.Td(
                        dbc.Badge(str(r["rank"]), color="secondary"),
                        style={**_td, "textAlign": "center", "width": "44px"},
                    ),
                    html.Td(html.Strong(r["ticker"]), style=_td),
                    html.Td(r["name"] or "—",
                            style={**_td, "color": "#9ca3af", "fontSize": "0.76rem"}),
                    html.Td(
                        html.Span(f"{r['score']:.1f}",
                                  style={"fontFamily": "monospace",
                                         "color": "#4ade80" if (r["score"] or 0) >= 20
                                                  else "#f87171" if (r["score"] or 0) <= -20
                                                  else "#94a3b8"}),
                        style=_td,
                    ),
                ])
                for r in top
            ]
            link_href = f"/senales"
            preview = dbc.Card(dbc.CardBody([
                html.Div([
                    html.Span(f"Top 10 — {strat_name} ({target_date})",
                              style={"fontSize": "0.84rem", "fontWeight": "500",
                                     "color": "#e5e7eb"}),
                    html.A("Ver en screener →", href=link_href,
                           style={"fontSize": "0.78rem", "color": "#60a5fa",
                                  "marginLeft": "12px", "textDecoration": "none"}),
                ], className="mb-2"),
                html.Table([
                    html.Thead(html.Tr([
                        html.Th("Rank",   style={**_th, "width": "44px"}),
                        html.Th("Ticker", style=_th),
                        html.Th("Nombre", style=_th),
                        html.Th("Score",  style=_th),
                    ])),
                    html.Tbody(rows),
                ], style={"width": "100%", "borderCollapse": "collapse"}),
            ]), style={"backgroundColor": "#1f2937", "border": "1px solid #374151"})

    if insample_alert is not None:
        preview = html.Div([insample_alert, preview])
    return "", f"Calculados {total} resultado(s) para {target_date}.", True, "success", preview


# ── Exportar ──────────────────────────────────────────────────────────────────

@callback(
    Output("str-download", "data"),
    Input("str-btn-export", "n_clicks"),
    prevent_initial_call=True,
)
def export(_):
    _, is_admin = current_viewer()
    if not is_admin:
        return no_update
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
    user_id, is_admin = current_viewer()
    if not is_admin:
        return no_update, "Solo un administrador puede importar estrategias.", True, "danger"
    try:
        _, encoded = contents.split(",", 1)
        results = svc.import_strategies_excel(base64.b64decode(encoded),
                                              owner_id=user_id)
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


# ── Calcular historia (backfill acotado a la estrategia propia) ───────────────

@callback(
    Output("str-status",  "children",  allow_duplicate=True),
    Output("str-alert",   "children",  allow_duplicate=True),
    Output("str-alert",   "is_open",   allow_duplicate=True),
    Output("str-alert",   "color",     allow_duplicate=True),
    Input("str-btn-history",  "n_clicks"),
    State("str-selected-ids", "data"),
    State("str-history-days", "value"),
    prevent_initial_call=True,
)
def compute_history(_, selected_ids, days):
    """Llena las fechas pasadas sin resultado de la estrategia seleccionada
    (scope strategy:<id> del backfill del Centro de Datos). Sincrónico bajo
    dcc.Loading — acotado a UNA estrategia es tolerable."""
    if not selected_ids or len(selected_ids) != 1:
        return no_update, no_update, no_update, no_update
    user_id, is_admin = current_viewer()
    strat = next((x for x in _visible_strategies()
                  if x.id == selected_ids[0]), None)
    if strat is None:
        return "", "Estrategia no encontrada.", True, "danger"
    if not can_edit(strat.owner_id, user_id, is_admin):
        return "", "Solo el dueño o un administrador pueden calcular la historia.", True, "danger"
    try:
        import app.services.signal_service as sig_service
        result = sig_service.update_signal_history(
            days=int(days) if days else None, scope=f"strategy:{strat.id}")
        n_err = len(result.get("errors") or [])
        msg = (f"Historia de '{strat.name}': {result.get('success', 0)}/"
               f"{result.get('total', 0)} fecha(s) calculadas"
               + (f", {n_err} con error." if n_err else "."))
        return "", msg, True, ("warning" if n_err else "success")
    except Exception as exc:
        return "", str(exc), True, "danger"
