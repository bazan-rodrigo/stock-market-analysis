"""
Callbacks para el ABM de eventos de mercado.
"""
from datetime import date

from dash import Input, Output, State, callback, clientside_callback, no_update
from flask_login import current_user

import app.services.event_service as svc
import app.services.reference_service as ref_svc
from app.services.asset_service import get_assets


def _require_admin():
    return not (current_user.is_authenticated and current_user.is_admin)


# ── Cargar tabla ──────────────────────────────────────────────────────────────
@callback(
    Output("events-table", "data"),
    Input("events-table", "id"),
    prevent_initial_call=False,
)
def load_events(_):
    _SCOPE_LABELS = {"global": "Global", "country": "País", "asset": "Activo"}
    rows = svc.get_all_events()
    result = []
    for ev in rows:
        if ev.scope == "country" and ev.country_id:
            from app.models import MarketEvent
            from app.database import get_session
            from app.models import Country
            country = get_session().query(Country).filter_by(id=ev.country_id).first()
            ref = country.name if country else str(ev.country_id)
        elif ev.scope == "asset" and ev.asset_id:
            from app.database import get_session
            from app.models import Asset
            asset = get_session().query(Asset).filter_by(id=ev.asset_id).first()
            ref = asset.ticker if asset else str(ev.asset_id)
        else:
            ref = "—"
        result.append({
            "id":          ev.id,
            "name":        ev.name,
            "start_date":  str(ev.start_date),
            "end_date":    str(ev.end_date),
            "scope_label": _SCOPE_LABELS.get(ev.scope, ev.scope),
            "ref_label":   ref,
            "color":       ev.color or "#ff9800",
        })
    return result


# ── Opciones de país y activo en el formulario ────────────────────────────────
@callback(
    Output("events-f-country_id", "options"),
    Output("events-f-asset_id",   "options"),
    Input("events-table", "id"),
)
def load_form_options(_):
    countries = ref_svc.get_countries()
    assets    = get_assets(only_active=True)
    return (
        [{"label": c.name, "value": c.id} for c in countries],
        [{"label": f"{a.ticker} – {a.name or a.ticker}", "value": a.id} for a in assets],
    )


# ── Mostrar/ocultar filas de país y activo según scope ───────────────────────
clientside_callback(
    """function(scope) {
        var showCountry = scope === 'country' ? {} : {display: 'none'};
        var showAsset   = scope === 'asset'   ? {} : {display: 'none'};
        return [showCountry, showAsset];
    }""",
    Output("events-row-country", "style"),
    Output("events-row-asset",   "style"),
    Input("events-f-scope", "value"),
    prevent_initial_call=False,
)


# ── Habilitar/deshabilitar botones según selección ────────────────────────────
@callback(
    Output("events-btn-edit",   "disabled"),
    Output("events-btn-delete", "disabled"),
    Input("events-table", "selected_rows"),
)
def toggle_buttons(sel_rows):
    disabled = not bool(sel_rows)
    return disabled, disabled


# ── Modal: abrir/cerrar + cargar datos ───────────────────────────────────────
@callback(
    Output("events-modal",       "is_open"),
    Output("events-modal-title", "children"),
    Output("events-f-name",       "value"),
    Output("events-f-start_date", "value"),
    Output("events-f-end_date",   "value"),
    Output("events-f-scope",      "value"),
    Output("events-f-color",      "value"),
    Output("events-f-country_id", "value"),
    Output("events-f-asset_id",   "value"),
    Output("events-editing-id",   "data"),
    Input("events-btn-add",    "n_clicks"),
    Input("events-btn-edit",   "n_clicks"),
    Input("events-btn-cancel", "n_clicks"),
    Input("events-btn-save",   "n_clicks"),
    State("events-table",      "selected_rows"),
    State("events-table",      "data"),
    State("events-editing-id", "data"),
    prevent_initial_call=True,
)
def events_modal(n_add, n_edit, n_cancel, n_save, sel_rows, data, editing_id):
    from dash import ctx
    trigger = ctx.triggered_id

    if trigger == "events-btn-cancel":
        return False, no_update, no_update, no_update, no_update, no_update, no_update, no_update, no_update, None
    if trigger == "events-btn-save":
        return no_update, no_update, no_update, no_update, no_update, no_update, no_update, no_update, no_update, no_update

    if trigger == "events-btn-add":
        return True, "Nuevo evento", "", "", "", "global", "#ff9800", None, None, None

    if trigger == "events-btn-edit" and sel_rows:
        row = data[sel_rows[0]]
        ev  = svc.get_event(row["id"])
        if not ev:
            return no_update, no_update, no_update, no_update, no_update, no_update, no_update, no_update, no_update, no_update
        return (
            True, "Editar evento",
            ev.name,
            str(ev.start_date),
            str(ev.end_date),
            ev.scope,
            ev.color or "#ff9800",
            ev.country_id,
            ev.asset_id,
            ev.id,
        )

    return no_update, no_update, no_update, no_update, no_update, no_update, no_update, no_update, no_update, no_update


# ── Guardar ──────────────────────────────────────────────────────────────────
@callback(
    Output("events-table",  "data",    allow_duplicate=True),
    Output("events-alert",  "children"),
    Output("events-alert",  "color"),
    Output("events-alert",  "is_open"),
    Output("events-modal",  "is_open", allow_duplicate=True),
    Input("events-btn-save", "n_clicks"),
    State("events-editing-id",   "data"),
    State("events-f-name",        "value"),
    State("events-f-start_date",  "value"),
    State("events-f-end_date",    "value"),
    State("events-f-scope",       "value"),
    State("events-f-color",       "value"),
    State("events-f-country_id",  "value"),
    State("events-f-asset_id",    "value"),
    prevent_initial_call=True,
)
def save_event(n_save, editing_id, name, start_date, end_date, scope, color, country_id, asset_id):
    if not n_save:
        return no_update, no_update, no_update, no_update, no_update
    if _require_admin():
        return no_update, "Sin permisos.", "danger", True, no_update
    if not name or not start_date or not end_date or not scope:
        return no_update, "Completá nombre, fechas y alcance.", "warning", True, no_update
    try:
        start = date.fromisoformat(start_date)
        end   = date.fromisoformat(end_date)
        if end < start:
            return no_update, "La fecha de fin debe ser >= inicio.", "warning", True, no_update
        svc.save_event(editing_id, name, start, end, scope, country_id, asset_id, color)
        return load_events(None), "Guardado correctamente.", "success", True, False
    except Exception as e:
        return no_update, f"Error: {e}", "danger", True, no_update


# ── Modal confirmación eliminar ───────────────────────────────────────────────
@callback(
    Output("events-confirm-modal", "is_open"),
    Output("events-confirm-body",  "children"),
    Input("events-btn-delete",         "n_clicks"),
    Input("events-btn-cancel-delete",  "n_clicks"),
    Input("events-btn-confirm-delete", "n_clicks"),
    State("events-table", "selected_rows"),
    State("events-table", "data"),
    prevent_initial_call=True,
)
def events_confirm_delete(n_del, n_cancel, n_confirm, sel_rows, data):
    from dash import ctx
    trigger = ctx.triggered_id
    if trigger in ("events-btn-cancel-delete", "events-btn-confirm-delete"):
        return False, no_update
    if trigger == "events-btn-delete" and sel_rows:
        name = data[sel_rows[0]]["name"]
        return True, f'¿Eliminás el evento "{name}"?'
    return no_update, no_update


# ── Confirmar eliminar ────────────────────────────────────────────────────────
@callback(
    Output("events-table",  "data",    allow_duplicate=True),
    Output("events-alert",  "children", allow_duplicate=True),
    Output("events-alert",  "color",    allow_duplicate=True),
    Output("events-alert",  "is_open",  allow_duplicate=True),
    Input("events-btn-confirm-delete", "n_clicks"),
    State("events-table", "selected_rows"),
    State("events-table", "data"),
    prevent_initial_call=True,
)
def confirm_delete_event(n_confirm, sel_rows, data):
    if not n_confirm or not sel_rows:
        return no_update, no_update, no_update, no_update
    if _require_admin():
        return no_update, "Sin permisos.", "danger", True
    try:
        event_id = data[sel_rows[0]]["id"]
        svc.delete_event(event_id)
        return load_events(None), "Evento eliminado.", "success", True
    except Exception as e:
        return no_update, f"Error: {e}", "danger", True
