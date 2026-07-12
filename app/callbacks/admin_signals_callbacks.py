import base64

from dash import Input, Output, State, callback, ctx, dcc, html, no_update

import app.services.signal_service as svc
from app.callbacks.signal_params_ui import (
    PB_FIELD_STATES, builder_from_params, empty_params_store,
    params_from_builder, pb_capture_from_args,
)
from app.components.ui_constants import (
    TH as _th, TD as _td,
    COLOR_POSITIVE, COLOR_NEGATIVE,
    formula_help_card as _help_card,
)


# ── Tabla ─────────────────────────────────────────────────────────────────────

_FT_LABEL = {
    "discrete_map": "Mapa",
    "threshold":    "Umbrales",
    "range":        "Rango",
    "composite":    "Compuesta",
}

@callback(
    Output("sig-datatable", "data"),
    Output("sig-datatable", "selected_rows"),
    Output("sig-all-ids",   "data"),
    Input("sig-alert",      "is_open"),
    Input("sig-modal",      "is_open"),
)
def load_table(_a, _m):
    signals = svc.get_all_signals()
    all_ids = [s.id for s in signals]
    data = [
        {
            "id":            s.id,
            "key":           s.key,
            "name":          s.name,
            "source":        s.source,
            "indicator_key": s.indicator_key or "—",
            "formula_type":  _FT_LABEL.get(s.formula_type, s.formula_type),
            "sistema":       "Sí" if s.is_system else "",
        }
        for s in signals
    ]
    return data, [], all_ids


# ── Selección ─────────────────────────────────────────────────────────────────

@callback(
    Output("sig-selected-ids", "data"),
    Input("sig-datatable",     "selected_rows"),
    State("sig-datatable",     "data"),
    prevent_initial_call=True,
)
def update_selected_ids(selected_rows, data):
    if not selected_rows or not data:
        return []
    return [data[i]["id"] for i in selected_rows]


@callback(
    Output("sig-btn-edit",   "disabled"),
    Output("sig-btn-delete", "disabled"),
    Input("sig-selected-ids", "data"),
)
def update_buttons(selected_ids):
    n = len(selected_ids or [])
    return (n != 1), (n == 0)


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
    Output("sig-pb-store",      "data"),
    Output("sig-params-advanced", "value"),
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
    _noup = no_update
    _noop = (_noup,) * 15  # 15 outputs totales

    if trigger == "sig-btn-cancel":
        # is_open=False, resto sin cambio, editing_id=None, error=False
        return (False, _noup, _noup, _noup, _noup, _noup, _noup,
                _noup, _noup, _noup, _noup, _noup, _noup, None, False)

    if trigger == "sig-btn-add":
        return (True, "Nueva señal", "", False, "", None, None,
                "", None, "", "{}", empty_params_store(), False, None, False)

    if trigger == "sig-btn-edit":
        if not selected_ids or len(selected_ids) != 1:
            return _noop
        sig = next((x for x in svc.get_all_signals() if x.id == selected_ids[0]), None)
        if sig is None:
            return _noop
        # Params al editor estructurado; si el JSON guardado no es
        # representable (editado a mano, forma inesperada), modo avanzado
        pb_store = builder_from_params(sig.formula_type, sig.params)
        advanced = pb_store is None
        return (
            True, "Editar señal",
            sig.key, sig.is_system,
            sig.name, sig.source,
            sig.group_type, sig.indicator_key,
            sig.formula_type, sig.description or "", sig.params,
            pb_store if pb_store is not None else empty_params_store(),
            advanced,
            sig.id, False,
        )

    return _noop


# ── Mostrar/ocultar col grupo ─────────────────────────────────────────────────

@callback(
    Output("sig-col-group-type", "style"),
    Input("sig-f-source", "value"),
)
def toggle_group_col(source):
    if source == "group":
        return {}
    return {"display": "none"}


# Las señales de grupo leen de group_scores, que solo tiene estos campos.
# Sin esta separación el dropdown ofrecía indicadores de activo
# (trend_daily, ...) para señales de grupo — así se rompieron las 6 señales
# de sistema tendencia_sector_*/tendencia_mercado_* (guardadas con
# indicator_key inválido, nunca volvieron a puntuar).
_GROUP_INDICATOR_OPTS = [
    {"label": "regime_score_d — Tendencia diaria del grupo",   "value": "regime_score_d"},
    {"label": "regime_score_w — Tendencia semanal del grupo",  "value": "regime_score_w"},
    {"label": "regime_score_m — Tendencia mensual del grupo",  "value": "regime_score_m"},
]


@callback(
    Output("sig-f-indicator-key", "options"),
    Input("sig-f-source", "value"),
)
def indicator_opts_by_source(source):
    if source == "group":
        return _GROUP_INDICATOR_OPTS
    from app.pages.admin_signals import _build_indicator_opts
    return _build_indicator_opts()


# ── Ayuda de fórmula ──────────────────────────────────────────────────────────

@callback(
    Output("sig-formula-help", "children"),
    Input("sig-f-formula-type", "value"),
    Input("sig-params-advanced", "value"),
)
def update_help(ft, advanced):
    # El ejemplo JSON solo aporta en modo avanzado; el editor estructurado
    # hace el resto autoexplicativo
    return _help_card(ft, show_example=bool(advanced))


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
    State("sig-params-advanced", "value"),
    State("sig-pb-store",        "data"),
    *PB_FIELD_STATES,
    prevent_initial_call=True,
)
def save(_, key, name, source, group_type, indicator_key,
         formula_type, description, params, editing_id,
         advanced, pb_store, *pb_field_args):

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

    if not advanced:
        # Serializar desde el editor estructurado
        pb_store = pb_capture_from_args(pb_store, pb_field_args)
        params, p_error = params_from_builder(formula_type, pb_store)
        if p_error:
            return err(p_error)
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
    target_date = dt_date.fromisoformat(date_str) if date_str else dt_date.today()
    try:
        result = svc.run_recalculate(target_date)
        msg = (f"Pipeline {target_date}: "
               f"{result['signal_values']} signal_value, "
               f"{result['group_signal_values']} group_signal_value, "
               f"{result.get('strategy_results', 0)} strategy_result.")
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

    _COLOR = {"ok": COLOR_POSITIVE, "error": COLOR_NEGATIVE}
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
