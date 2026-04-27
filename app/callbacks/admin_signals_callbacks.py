import base64

from dash import ALL, Input, Output, State, callback, ctx, dcc, html, no_update
import dash_bootstrap_components as dbc

import app.services.signal_service as svc
from app.pages.admin_signals import _help_card, _th, _td


# ── Tabla ─────────────────────────────────────────────────────────────────────

@callback(
    Output("sig-table-container", "children"),
    Output("sig-all-ids",         "data"),
    Output("sig-btn-edit",        "disabled"),
    Output("sig-btn-delete",      "disabled"),
    Input("sig-alert",            "is_open"),
    Input("sig-modal",            "is_open"),
    Input("sig-selected-ids",     "data"),
)
def load_table(_a, _m, selected_ids):
    selected_ids = selected_ids or []
    signals = svc.get_all_signals()
    all_ids = [s.id for s in signals]
    n = len(selected_ids)

    if not signals:
        return (html.P("Sin señales configuradas.", className="text-muted mt-2",
                       style={"fontSize": "0.82rem"}),
                all_ids, True, True)

    _SOURCE_COLOR = {"asset": "#38bdf8", "group": "#4ade80"}
    _FT_LABEL = {
        "discrete_map": "Mapa",
        "threshold":    "Umbrales",
        "range":        "Rango",
        "composite":    "Compuesta",
    }

    rows = []
    for sig in signals:
        is_sel = sig.id in selected_ids
        rows.append(html.Tr([
            html.Td(
                dbc.Button(
                    html.I(className="fa fa-check-square" if is_sel else "fa fa-square-o"),
                    id={"type": "sig-check", "index": sig.id},
                    color="link", size="sm",
                    style={"color": "#38bdf8" if is_sel else "#6b7280",
                           "padding": "2px 4px", "lineHeight": 1},
                ),
                style={**_td, "width": "32px", "padding": "2px"},
            ),
            html.Td(html.Code(sig.key, style={"fontSize": "0.78rem", "color": "#94a3b8"}),
                    style=_td),
            html.Td(sig.name, style=_td),
            html.Td(
                dbc.Badge(sig.source, color="info" if sig.source == "asset" else "success",
                          className="me-1"),
                style=_td,
            ),
            html.Td(html.Code(sig.indicator_key or "—",
                              style={"fontSize": "0.76rem", "color": "#6b7280"}),
                    style=_td),
            html.Td(_FT_LABEL.get(sig.formula_type, sig.formula_type), style=_td),
            html.Td(
                dbc.Badge("sistema", color="secondary") if sig.is_system else "",
                style=_td,
            ),
        ]))

    table = html.Table([
        html.Thead(html.Tr([
            html.Th("",              style={**_th, "width": "32px", "padding": "5px 2px"}),
            html.Th("Key",           style=_th),
            html.Th("Nombre",        style=_th),
            html.Th("Fuente",        style=_th),
            html.Th("Indicador",     style=_th),
            html.Th("Fórmula",       style=_th),
            html.Th("",              style=_th),
        ])),
        html.Tbody(rows),
    ], style={"width": "100%", "borderCollapse": "collapse"})

    return table, all_ids, (n != 1), (n == 0)


# ── Selección ─────────────────────────────────────────────────────────────────

@callback(
    Output("sig-selected-ids", "data", allow_duplicate=True),
    Input({"type": "sig-check", "index": ALL}, "n_clicks"),
    State("sig-selected-ids", "data"),
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
    Output("sig-modal",         "is_open"),
    Output("sig-modal-title",   "children"),
    Output("sig-f-key",         "value"),
    Output("sig-f-key",         "disabled"),
    Output("sig-f-name",        "value"),
    Output("sig-f-source",      "value"),
    Output("sig-f-group-type",  "value"),
    Output("sig-f-indicator-key", "value"),
    Output("sig-f-formula-type","value"),
    Output("sig-f-description", "value"),
    Output("sig-f-params",      "value"),
    Output("sig-editing-id",    "data"),
    Output("sig-modal-error",   "is_open", allow_duplicate=True),
    Input("sig-btn-add",        "n_clicks"),
    Input("sig-btn-cancel",     "n_clicks"),
    Input("sig-btn-edit",       "n_clicks"),
    State("sig-selected-ids",   "data"),
    prevent_initial_call=True,
)
def toggle_modal(n_add, n_cancel, n_edit, selected_ids):
    trigger = ctx.triggered_id
    _none13 = (no_update,) * 13

    if trigger == "sig-btn-cancel":
        return False, *([no_update] * 11), None, False

    if trigger == "sig-btn-add":
        return True, "Nueva señal", "", False, "", None, None, "", None, "", "{}", None, False

    if trigger == "sig-btn-edit":
        if not selected_ids or len(selected_ids) != 1:
            return *_none13,
        sig = next((x for x in svc.get_all_signals() if x.id == selected_ids[0]), None)
        if sig is None:
            return *_none13,
        return (
            True, "Editar señal",
            sig.key, sig.is_system,   # key deshabilitado si es sistema
            sig.name, sig.source,
            sig.group_type, sig.indicator_key,
            sig.formula_type, sig.description or "", sig.params,
            sig.id, False,
        )

    return *_none13,


# ── Mostrar/ocultar col grupo ─────────────────────────────────────────────────

@callback(
    Output("sig-col-group-type", "style"),
    Input("sig-f-source", "value"),
)
def toggle_group_col(source):
    if source == "group":
        return {}
    return {"display": "none"}


# ── Ayuda de fórmula ──────────────────────────────────────────────────────────

@callback(
    Output("sig-formula-help", "children"),
    Input("sig-f-formula-type", "value"),
)
def update_help(ft):
    return _help_card(ft)


# ── Guardar ───────────────────────────────────────────────────────────────────

@callback(
    Output("sig-alert",       "children"),
    Output("sig-alert",       "is_open"),
    Output("sig-alert",       "color"),
    Output("sig-modal",       "is_open",  allow_duplicate=True),
    Output("sig-modal-error", "children"),
    Output("sig-modal-error", "is_open"),
    Output("sig-selected-ids","data",     allow_duplicate=True),
    Input("sig-btn-save",     "n_clicks"),
    State("sig-f-key",        "value"),
    State("sig-f-name",       "value"),
    State("sig-f-source",     "value"),
    State("sig-f-group-type", "value"),
    State("sig-f-indicator-key", "value"),
    State("sig-f-formula-type",  "value"),
    State("sig-f-description",   "value"),
    State("sig-f-params",        "value"),
    State("sig-editing-id",      "data"),
    prevent_initial_call=True,
)
def save(_, key, name, source, group_type, indicator_key,
         formula_type, description, params, editing_id):

    def err(msg):
        return no_update, no_update, no_update, no_update, msg, True, no_update

    if not key or not key.strip():
        return err("La clave (key) es obligatoria.")
    if not name or not name.strip():
        return err("El nombre es obligatorio.")
    if not source:
        return err("Seleccioná la fuente (asset o group).")
    if not formula_type:
        return err("Seleccioná el tipo de fórmula.")
    if not params or not params.strip():
        return err("Los parámetros JSON son obligatorios.")

    try:
        svc.save_signal(
            key=key.strip(),
            name=name.strip(),
            source=source,
            formula_type=formula_type,
            params_json=params.strip(),
            description=description or None,
            group_type=group_type or None,
            indicator_key=indicator_key or None,
            signal_id=editing_id,
        )
        return "Señal guardada.", True, "success", False, "", False, []
    except Exception as exc:
        return err(str(exc))


# ── Eliminar ──────────────────────────────────────────────────────────────────

@callback(
    Output("sig-alert",       "children",  allow_duplicate=True),
    Output("sig-alert",       "is_open",   allow_duplicate=True),
    Output("sig-alert",       "color",     allow_duplicate=True),
    Output("sig-selected-ids","data",      allow_duplicate=True),
    Input("sig-btn-delete",   "n_clicks"),
    State("sig-selected-ids", "data"),
    prevent_initial_call=True,
)
def delete_selected(_, selected_ids):
    if not selected_ids:
        return no_update, no_update, no_update, no_update
    errors = []
    ok = 0
    for sid in selected_ids:
        try:
            svc.delete_signal(sid)
            ok += 1
        except Exception as exc:
            errors.append(str(exc))
    if errors:
        return "; ".join(errors), True, "danger", []
    return f"{ok} señal(es) eliminada(s).", True, "success", []


# ── Recalcular ────────────────────────────────────────────────────────────────

@callback(
    Output("sig-status",  "children",  allow_duplicate=True),
    Output("sig-alert",   "children",  allow_duplicate=True),
    Output("sig-alert",   "is_open",   allow_duplicate=True),
    Output("sig-alert",   "color",     allow_duplicate=True),
    Input("sig-btn-recalc", "n_clicks"),
    State("sig-recalc-date", "date"),
    prevent_initial_call=True,
)
def recalculate(_, date_str):
    from datetime import date as dt_date
    snap_date = dt_date.fromisoformat(date_str) if date_str else dt_date.today()
    try:
        result = svc.run_recalculate(snap_date)
        msg = (f"Recálculo {snap_date}: "
               f"{result['signal_values']} signal_value, "
               f"{result['group_signal_values']} group_signal_value.")
        return "", msg, True, "success"
    except Exception as exc:
        return "", str(exc), True, "danger"


# ── Exportar ──────────────────────────────────────────────────────────────────

@callback(
    Output("sig-download", "data"),
    Input("sig-btn-export", "n_clicks"),
    prevent_initial_call=True,
)
def export(_):
    return dcc.send_bytes(svc.export_signals_excel(), "señales.xlsx")


# ── Importar ──────────────────────────────────────────────────────────────────

@callback(
    Output("sig-import-results", "children"),
    Output("sig-alert",          "children",  allow_duplicate=True),
    Output("sig-alert",          "is_open",   allow_duplicate=True),
    Output("sig-alert",          "color",     allow_duplicate=True),
    Input("sig-upload",          "contents"),
    State("sig-upload",          "filename"),
    prevent_initial_call=True,
)
def import_excel(contents, filename):
    if contents is None:
        return no_update, no_update, no_update, no_update
    try:
        _, encoded = contents.split(",", 1)
        results = svc.import_signals_excel(base64.b64decode(encoded))
    except Exception as exc:
        return no_update, str(exc), True, "danger"

    ok_count  = sum(1 for r in results if r["status"] == "ok")
    err_count = sum(1 for r in results if r["status"] == "error")

    _COLOR = {"ok": "#4ade80", "error": "#f87171"}
    rows = [
        html.Tr([
            html.Td(r["key"],    style=_td),
            html.Td(r["status"].upper(),
                    style={**_td, "color": _COLOR.get(r["status"], "#9ca3af")}),
            html.Td(r["detail"], style={**_td, "fontSize": "0.75rem", "color": "#9ca3af"}),
        ])
        for r in results
    ]
    table = html.Table([
        html.Thead(html.Tr([html.Th("Key", style=_th), html.Th("Estado", style=_th),
                             html.Th("Detalle", style=_th)])),
        html.Tbody(rows),
    ], style={"width": "100%", "borderCollapse": "collapse"})

    msg   = f"Importación: {ok_count} OK, {err_count} error(es)."
    color = "success" if not err_count else ("warning" if ok_count else "danger")
    return table, msg, True, color
