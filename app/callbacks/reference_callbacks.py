"""
Callbacks para todas las pantallas ABM de referencia.
Patrón: open modal → guardar → actualizar tabla → cerrar modal → feedback.
"""
from dash import Input, Output, State, callback, no_update
from flask_login import current_user

import app.services.reference_service as svc


# ===========================================================================
# Helper genérico para los callbacks ABM
# ===========================================================================

def _require_admin():
    return not (current_user.is_authenticated and current_user.is_admin)


def _confirm_body(sel_rows, data, name_field="name"):
    n = len(sel_rows or [])
    if n == 0:
        return no_update
    if n == 1:
        name = (data[sel_rows[0]] or {}).get(name_field, "")
        return f"¿Eliminás '{name}'? Esta acción no se puede deshacer."
    if n <= 5:
        names = ", ".join((data[i] or {}).get(name_field, str(i)) for i in sel_rows)
        return f"¿Eliminás {n} registros? ({names})"
    return f"¿Eliminás {n} registros? Esta acción no se puede deshacer."


def _register_select_all(entity_id):
    @callback(
        Output(f"{entity_id}-table", "selected_rows"),
        Input(f"{entity_id}-btn-select-all", "n_clicks"),
        Input(f"{entity_id}-btn-deselect-all", "n_clicks"),
        State(f"{entity_id}-table", "data"),
        prevent_initial_call=True,
    )
    def _cb(n_sel, n_desel, data):
        from dash import ctx
        if ctx.triggered_id == f"{entity_id}-btn-deselect-all":
            return []
        return list(range(len(data or [])))


for _eid in ("countries", "currencies", "markets", "instrument_types",
             "sectors", "industries", "price_sources", "users"):
    _register_select_all(_eid)


def _bulk_delete(sel_rows, data, delete_fn, reload_fn, row_mapper):
    errors, deleted = [], 0
    for i in sel_rows:
        try:
            delete_fn(data[i]["id"])
            deleted += 1
        except Exception as exc:
            errors.append(str(exc))
    rows = reload_fn()
    table_data = [row_mapper(r) for r in rows]
    if errors:
        msg = f"Eliminados {deleted}. Errores: " + "; ".join(errors)
        color = "warning" if deleted > 0 else "danger"
    else:
        msg = f"{deleted} registro{'s' if deleted != 1 else ''} eliminado{'s' if deleted != 1 else ''} correctamente."
        color = "success"
    return table_data, msg, True, color


# ===========================================================================
# PAÍSES
# ===========================================================================

@callback(
    Output("countries-table", "data"),
    Input("countries-table", "id"),
    prevent_initial_call=False,
)
def load_countries(_):
    rows = svc.get_countries()
    return [{"id": r.id, "name": r.name, "iso_code": r.iso_code} for r in rows]


@callback(
    Output("countries-modal", "is_open"),
    Output("countries-modal-title", "children"),
    Output("countries-f-name", "value"),
    Output("countries-f-iso_code", "value"),
    Output("countries-editing-id", "data"),
    Input("countries-btn-add", "n_clicks"),
    Input("countries-btn-edit", "n_clicks"),
    Input("countries-btn-cancel", "n_clicks"),
    State("countries-table", "selected_rows"),
    State("countries-table", "data"),
    State("countries-editing-id", "data"),
    prevent_initial_call=True,
)
def countries_modal(n_add, n_edit, n_cancel, sel_rows, data, editing_id):
    from dash import ctx
    trigger = ctx.triggered_id
    if trigger == "countries-btn-cancel":
        return False, no_update, no_update, no_update, None
    if trigger == "countries-btn-add":
        return True, "Nuevo país", "", "", None
    if trigger == "countries-btn-edit" and sel_rows:
        row = data[sel_rows[0]]
        return True, "Editar país", row["name"], row["iso_code"], row["id"]
    return no_update, no_update, no_update, no_update, no_update


@callback(
    Output("countries-table", "data", allow_duplicate=True),
    Output("countries-alert", "children"),
    Output("countries-alert", "is_open"),
    Output("countries-alert", "color"),
    Output("countries-modal", "is_open", allow_duplicate=True),
    Output("countries-modal-error", "children"),
    Output("countries-modal-error", "is_open"),
    Input("countries-btn-save", "n_clicks"),
    State("countries-f-name", "value"),
    State("countries-f-iso_code", "value"),
    State("countries-editing-id", "data"),
    prevent_initial_call=True,
)
def countries_save(n_clicks, name, iso_code, editing_id):
    if not name or not iso_code:
        return no_update, no_update, no_update, no_update, no_update, "Completá todos los campos.", True
    try:
        if editing_id:
            svc.update_country(editing_id, name, iso_code)
        else:
            svc.create_country(name, iso_code)
        rows = svc.get_countries()
        data = [{"id": r.id, "name": r.name, "iso_code": r.iso_code} for r in rows]
        return data, "Guardado correctamente.", True, "success", False, "", False
    except Exception as exc:
        return no_update, no_update, no_update, no_update, no_update, str(exc), True


@callback(
    Output("countries-btn-edit", "disabled"),
    Output("countries-btn-delete", "disabled"),
    Input("countries-table", "selected_rows"),
)
def countries_row_selection(sel_rows):
    return len(sel_rows or []) != 1, not bool(sel_rows)


@callback(
    Output("countries-confirm-modal", "is_open"),
    Output("countries-confirm-body", "children"),
    Input("countries-btn-delete", "n_clicks"),
    Input("countries-btn-confirm-delete", "n_clicks"),
    Input("countries-btn-cancel-delete", "n_clicks"),
    State("countries-table", "selected_rows"),
    State("countries-table", "data"),
    prevent_initial_call=True,
)
def countries_confirm_modal(n_del, n_confirm, n_cancel, sel_rows, data):
    from dash import ctx
    if ctx.triggered_id != "countries-btn-delete":
        return False, no_update
    return True, _confirm_body(sel_rows, data)


@callback(
    Output("countries-table", "data", allow_duplicate=True),
    Output("countries-alert", "children", allow_duplicate=True),
    Output("countries-alert", "is_open", allow_duplicate=True),
    Output("countries-alert", "color", allow_duplicate=True),
    Input("countries-btn-confirm-delete", "n_clicks"),
    State("countries-table", "selected_rows"),
    State("countries-table", "data"),
    prevent_initial_call=True,
)
def countries_delete(_, sel_rows, data):
    if not sel_rows:
        return no_update, no_update, no_update, no_update
    _m = lambda r: {"id": r.id, "name": r.name, "iso_code": r.iso_code}
    return _bulk_delete(sel_rows, data, svc.delete_country, svc.get_countries, _m)


# ===========================================================================
# MONEDAS
# ===========================================================================

@callback(
    Output("currencies-table", "data"),
    Input("currencies-table", "id"),
)
def load_currencies(_):
    rows = svc.get_currencies()
    return [{"id": r.id, "name": r.name, "iso_code": r.iso_code} for r in rows]


@callback(
    Output("currencies-modal", "is_open"),
    Output("currencies-modal-title", "children"),
    Output("currencies-f-name", "value"),
    Output("currencies-f-iso_code", "value"),
    Output("currencies-editing-id", "data"),
    Input("currencies-btn-add", "n_clicks"),
    Input("currencies-btn-edit", "n_clicks"),
    Input("currencies-btn-cancel", "n_clicks"),
    State("currencies-table", "selected_rows"),
    State("currencies-table", "data"),
    State("currencies-editing-id", "data"),
    prevent_initial_call=True,
)
def currencies_modal(n_add, n_edit, n_cancel, sel_rows, data, editing_id):
    from dash import ctx
    t = ctx.triggered_id
    if t == "currencies-btn-cancel":
        return False, no_update, no_update, no_update, None
    if t == "currencies-btn-add":
        return True, "Nueva moneda", "", "", None
    if t == "currencies-btn-edit" and sel_rows:
        row = data[sel_rows[0]]
        return True, "Editar moneda", row["name"], row["iso_code"], row["id"]
    return no_update, no_update, no_update, no_update, no_update


@callback(
    Output("currencies-table", "data", allow_duplicate=True),
    Output("currencies-alert", "children"),
    Output("currencies-alert", "is_open"),
    Output("currencies-alert", "color"),
    Output("currencies-modal", "is_open", allow_duplicate=True),
    Output("currencies-modal-error", "children"),
    Output("currencies-modal-error", "is_open"),
    Input("currencies-btn-save", "n_clicks"),
    State("currencies-f-name", "value"),
    State("currencies-f-iso_code", "value"),
    State("currencies-editing-id", "data"),
    prevent_initial_call=True,
)
def currencies_save(n_clicks, name, iso_code, editing_id):
    if not name:
        return no_update, no_update, no_update, no_update, no_update, "El nombre es obligatorio.", True
    try:
        if editing_id:
            svc.update_currency(editing_id, name, iso_code)
        else:
            svc.create_currency(name, iso_code)
        rows = svc.get_currencies()
        data = [{"id": r.id, "name": r.name, "iso_code": r.iso_code} for r in rows]
        return data, "Guardado correctamente.", True, "success", False, "", False
    except Exception as exc:
        return no_update, no_update, no_update, no_update, no_update, str(exc), True


@callback(
    Output("currencies-btn-edit", "disabled"),
    Output("currencies-btn-delete", "disabled"),
    Input("currencies-table", "selected_rows"),
)
def currencies_row_selection(sel_rows):
    return len(sel_rows or []) != 1, not bool(sel_rows)


@callback(
    Output("currencies-confirm-modal", "is_open"),
    Output("currencies-confirm-body", "children"),
    Input("currencies-btn-delete", "n_clicks"),
    Input("currencies-btn-confirm-delete", "n_clicks"),
    Input("currencies-btn-cancel-delete", "n_clicks"),
    State("currencies-table", "selected_rows"),
    State("currencies-table", "data"),
    prevent_initial_call=True,
)
def currencies_confirm_modal(n_del, n_confirm, n_cancel, sel_rows, data):
    from dash import ctx
    if ctx.triggered_id != "currencies-btn-delete":
        return False, no_update
    return True, _confirm_body(sel_rows, data)


@callback(
    Output("currencies-table", "data", allow_duplicate=True),
    Output("currencies-alert", "children", allow_duplicate=True),
    Output("currencies-alert", "is_open", allow_duplicate=True),
    Output("currencies-alert", "color", allow_duplicate=True),
    Input("currencies-btn-confirm-delete", "n_clicks"),
    State("currencies-table", "selected_rows"),
    State("currencies-table", "data"),
    prevent_initial_call=True,
)
def currencies_delete(_, sel_rows, data):
    if not sel_rows:
        return no_update, no_update, no_update, no_update
    _m = lambda r: {"id": r.id, "name": r.name, "iso_code": r.iso_code}
    return _bulk_delete(sel_rows, data, svc.delete_currency, svc.get_currencies, _m)


# ===========================================================================
# MERCADOS
# ===========================================================================

@callback(
    Output("markets-table", "data"),
    Output("markets-f-country_id", "options"),
    Output("markets-f-benchmark_id", "options"),
    Input("markets-table", "id"),
)
def load_markets(_):
    from app.database import get_session
    from app.models import Asset
    markets   = svc.get_markets()
    countries = svc.get_countries()
    assets    = get_session().query(Asset).order_by(Asset.ticker).all()
    data = [{"id": m.id, "name": m.name, "country_name": m.country.name if m.country else ""} for m in markets]
    country_opts   = [{"label": "— Sin país —", "value": ""}] + [{"label": c.name, "value": c.id} for c in countries]
    benchmark_opts = [{"label": f"{a.ticker} — {a.name}", "value": a.id} for a in assets]
    return data, country_opts, benchmark_opts


@callback(
    Output("markets-modal", "is_open"),
    Output("markets-modal-title", "children"),
    Output("markets-f-name", "value"),
    Output("markets-f-country_id", "value"),
    Output("markets-f-benchmark_id", "value"),
    Output("markets-editing-id", "data"),
    Input("markets-btn-add", "n_clicks"),
    Input("markets-btn-edit", "n_clicks"),
    Input("markets-btn-cancel", "n_clicks"),
    State("markets-table", "selected_rows"),
    State("markets-table", "data"),
    State("markets-editing-id", "data"),
    prevent_initial_call=True,
)
def markets_modal(n_add, n_edit, n_cancel, sel_rows, data, editing_id):
    from dash import ctx
    t = ctx.triggered_id
    if t == "markets-btn-cancel":
        return False, no_update, no_update, no_update, no_update, None
    if t == "markets-btn-add":
        return True, "Nuevo mercado", "", None, None, None
    if t == "markets-btn-edit" and sel_rows:
        from app.database import get_session
        from app.models import Market
        m = get_session().get(Market, data[sel_rows[0]]["id"])
        return True, "Editar mercado", m.name, m.country_id, m.benchmark_id, m.id
    return no_update, no_update, no_update, no_update, no_update, no_update


@callback(
    Output("markets-table", "data", allow_duplicate=True),
    Output("markets-alert", "children"),
    Output("markets-alert", "is_open"),
    Output("markets-alert", "color"),
    Output("markets-modal", "is_open", allow_duplicate=True),
    Output("markets-modal-error", "children"),
    Output("markets-modal-error", "is_open"),
    Input("markets-btn-save", "n_clicks"),
    State("markets-f-name", "value"),
    State("markets-f-country_id", "value"),
    State("markets-f-benchmark_id", "value"),
    State("markets-editing-id", "data"),
    prevent_initial_call=True,
)
def markets_save(_, name, country_id, benchmark_id, editing_id):
    if not name:
        return no_update, no_update, no_update, no_update, no_update, "El nombre es obligatorio.", True
    try:
        cid = int(country_id) if country_id else None
        bm = int(benchmark_id) if benchmark_id else None
        if editing_id:
            svc.update_market(editing_id, name, cid, bm)
        else:
            svc.create_market(name, cid, bm)
        markets = svc.get_markets()
        data = [{"id": m.id, "name": m.name, "country_name": m.country.name if m.country else ""} for m in markets]
        return data, "Guardado correctamente.", True, "success", False, "", False
    except Exception as exc:
        return no_update, no_update, no_update, no_update, no_update, str(exc), True


@callback(
    Output("markets-btn-edit", "disabled"),
    Output("markets-btn-delete", "disabled"),
    Input("markets-table", "selected_rows"),
)
def markets_row_selection(sel_rows):
    return len(sel_rows or []) != 1, not bool(sel_rows)


@callback(
    Output("markets-confirm-modal", "is_open"),
    Output("markets-confirm-body", "children"),
    Input("markets-btn-delete", "n_clicks"),
    Input("markets-btn-confirm-delete", "n_clicks"),
    Input("markets-btn-cancel-delete", "n_clicks"),
    State("markets-table", "selected_rows"),
    State("markets-table", "data"),
    prevent_initial_call=True,
)
def markets_confirm_modal(n_del, n_confirm, n_cancel, sel_rows, data):
    from dash import ctx
    if ctx.triggered_id != "markets-btn-delete":
        return False, no_update
    return True, _confirm_body(sel_rows, data)


@callback(
    Output("markets-table", "data", allow_duplicate=True),
    Output("markets-alert", "children", allow_duplicate=True),
    Output("markets-alert", "is_open", allow_duplicate=True),
    Output("markets-alert", "color", allow_duplicate=True),
    Input("markets-btn-confirm-delete", "n_clicks"),
    State("markets-table", "selected_rows"),
    State("markets-table", "data"),
    prevent_initial_call=True,
)
def markets_delete(_, sel_rows, data):
    if not sel_rows:
        return no_update, no_update, no_update, no_update
    _m = lambda m: {"id": m.id, "name": m.name, "country_name": m.country.name if m.country else ""}
    return _bulk_delete(sel_rows, data, svc.delete_market, svc.get_markets, _m)


# ===========================================================================
# TIPOS DE INSTRUMENTO
# ===========================================================================

@callback(
    Output("instrument_types-table", "data"),
    Output("instrument_types-f-default_currency_id", "options"),
    Input("instrument_types-table", "id"),
)
def load_instrument_types(_):
    itypes = svc.get_instrument_types()
    currencies = svc.get_currencies()
    data = [
        {"id": it.id, "name": it.name, "currency_name": it.default_currency.iso_code if it.default_currency else ""}
        for it in itypes
    ]
    currency_opts = [{"label": f"{c.iso_code} - {c.name}", "value": c.id} for c in currencies]
    return data, currency_opts


@callback(
    Output("instrument_types-modal", "is_open"),
    Output("instrument_types-modal-title", "children"),
    Output("instrument_types-f-name", "value"),
    Output("instrument_types-f-default_currency_id", "value"),
    Output("instrument_types-editing-id", "data"),
    Input("instrument_types-btn-add", "n_clicks"),
    Input("instrument_types-btn-edit", "n_clicks"),
    Input("instrument_types-btn-cancel", "n_clicks"),
    State("instrument_types-table", "selected_rows"),
    State("instrument_types-table", "data"),
    State("instrument_types-editing-id", "data"),
    prevent_initial_call=True,
)
def instrument_types_modal(n_add, n_edit, n_cancel, sel_rows, data, editing_id):
    from dash import ctx
    t = ctx.triggered_id
    if t == "instrument_types-btn-cancel":
        return False, no_update, no_update, no_update, None
    if t == "instrument_types-btn-add":
        return True, "Nuevo tipo de instrumento", "", None, None
    if t == "instrument_types-btn-edit" and sel_rows:
        from app.database import get_session
        from app.models import InstrumentType
        it = get_session().get(InstrumentType, data[sel_rows[0]]["id"])
        return True, "Editar tipo de instrumento", it.name, it.default_currency_id, it.id
    return no_update, no_update, no_update, no_update, no_update


@callback(
    Output("instrument_types-table", "data", allow_duplicate=True),
    Output("instrument_types-alert", "children"),
    Output("instrument_types-alert", "is_open"),
    Output("instrument_types-alert", "color"),
    Output("instrument_types-modal", "is_open", allow_duplicate=True),
    Output("instrument_types-modal-error", "children"),
    Output("instrument_types-modal-error", "is_open"),
    Input("instrument_types-btn-save", "n_clicks"),
    State("instrument_types-f-name", "value"),
    State("instrument_types-f-default_currency_id", "value"),
    State("instrument_types-editing-id", "data"),
    prevent_initial_call=True,
)
def instrument_types_save(_, name, currency_id, editing_id):
    if not name or not currency_id:
        return no_update, no_update, no_update, no_update, no_update, "Completá todos los campos.", True
    try:
        if editing_id:
            svc.update_instrument_type(editing_id, name, int(currency_id))
        else:
            svc.create_instrument_type(name, int(currency_id))
        itypes = svc.get_instrument_types()
        data = [{"id": it.id, "name": it.name, "currency_name": it.default_currency.iso_code} for it in itypes]
        return data, "Guardado correctamente.", True, "success", False, "", False
    except Exception as exc:
        return no_update, no_update, no_update, no_update, no_update, str(exc), True


@callback(
    Output("instrument_types-btn-edit", "disabled"),
    Output("instrument_types-btn-delete", "disabled"),
    Input("instrument_types-table", "selected_rows"),
)
def instrument_types_row_selection(sel_rows):
    return len(sel_rows or []) != 1, not bool(sel_rows)


@callback(
    Output("instrument_types-confirm-modal", "is_open"),
    Output("instrument_types-confirm-body", "children"),
    Input("instrument_types-btn-delete", "n_clicks"),
    Input("instrument_types-btn-confirm-delete", "n_clicks"),
    Input("instrument_types-btn-cancel-delete", "n_clicks"),
    State("instrument_types-table", "selected_rows"),
    State("instrument_types-table", "data"),
    prevent_initial_call=True,
)
def instrument_types_confirm(n_del, n_confirm, n_cancel, sel_rows, data):
    from dash import ctx
    if ctx.triggered_id != "instrument_types-btn-delete":
        return False, no_update
    return True, _confirm_body(sel_rows, data)


@callback(
    Output("instrument_types-table", "data", allow_duplicate=True),
    Output("instrument_types-alert", "children", allow_duplicate=True),
    Output("instrument_types-alert", "is_open", allow_duplicate=True),
    Output("instrument_types-alert", "color", allow_duplicate=True),
    Input("instrument_types-btn-confirm-delete", "n_clicks"),
    State("instrument_types-table", "selected_rows"),
    State("instrument_types-table", "data"),
    prevent_initial_call=True,
)
def instrument_types_delete(_, sel_rows, data):
    if not sel_rows:
        return no_update, no_update, no_update, no_update
    _m = lambda it: {"id": it.id, "name": it.name, "currency_name": it.default_currency.iso_code if it.default_currency else ""}
    return _bulk_delete(sel_rows, data, svc.delete_instrument_type, svc.get_instrument_types, _m)


# ===========================================================================
# SECTORES
# ===========================================================================

@callback(Output("sectors-table", "data"), Input("sectors-table", "id"))
def load_sectors(_):
    return [{"id": r.id, "name": r.name} for r in svc.get_sectors()]


@callback(
    Output("sectors-modal", "is_open"),
    Output("sectors-modal-title", "children"),
    Output("sectors-f-name", "value"),
    Output("sectors-editing-id", "data"),
    Input("sectors-btn-add", "n_clicks"),
    Input("sectors-btn-edit", "n_clicks"),
    Input("sectors-btn-cancel", "n_clicks"),
    State("sectors-table", "selected_rows"),
    State("sectors-table", "data"),
    State("sectors-editing-id", "data"),
    prevent_initial_call=True,
)
def sectors_modal(n_add, n_edit, n_cancel, sel_rows, data, editing_id):
    from dash import ctx
    t = ctx.triggered_id
    if t == "sectors-btn-cancel":
        return False, no_update, no_update, None
    if t == "sectors-btn-add":
        return True, "Nuevo sector", "", None
    if t == "sectors-btn-edit" and sel_rows:
        row = data[sel_rows[0]]
        return True, "Editar sector", row["name"], row["id"]
    return no_update, no_update, no_update, no_update


@callback(
    Output("sectors-table", "data", allow_duplicate=True),
    Output("sectors-alert", "children"),
    Output("sectors-alert", "is_open"),
    Output("sectors-alert", "color"),
    Output("sectors-modal", "is_open", allow_duplicate=True),
    Output("sectors-modal-error", "children"),
    Output("sectors-modal-error", "is_open"),
    Input("sectors-btn-save", "n_clicks"),
    State("sectors-f-name", "value"),
    State("sectors-editing-id", "data"),
    prevent_initial_call=True,
)
def sectors_save(_, name, editing_id):
    if not name:
        return no_update, no_update, no_update, no_update, no_update, "Completá el nombre.", True
    try:
        if editing_id:
            svc.update_sector(editing_id, name)
        else:
            svc.create_sector(name)
        data = [{"id": r.id, "name": r.name} for r in svc.get_sectors()]
        return data, "Guardado correctamente.", True, "success", False, "", False
    except Exception as exc:
        return no_update, no_update, no_update, no_update, no_update, str(exc), True


@callback(
    Output("sectors-btn-edit", "disabled"),
    Output("sectors-btn-delete", "disabled"),
    Input("sectors-table", "selected_rows"),
)
def sectors_row_selection(sel_rows):
    return len(sel_rows or []) != 1, not bool(sel_rows)


@callback(
    Output("sectors-confirm-modal", "is_open"),
    Output("sectors-confirm-body", "children"),
    Input("sectors-btn-delete", "n_clicks"),
    Input("sectors-btn-confirm-delete", "n_clicks"),
    Input("sectors-btn-cancel-delete", "n_clicks"),
    State("sectors-table", "selected_rows"),
    State("sectors-table", "data"),
    prevent_initial_call=True,
)
def sectors_confirm(n_del, n_confirm, n_cancel, sel_rows, data):
    from dash import ctx
    if ctx.triggered_id != "sectors-btn-delete":
        return False, no_update
    return True, _confirm_body(sel_rows, data)


@callback(
    Output("sectors-table", "data", allow_duplicate=True),
    Output("sectors-alert", "children", allow_duplicate=True),
    Output("sectors-alert", "is_open", allow_duplicate=True),
    Output("sectors-alert", "color", allow_duplicate=True),
    Input("sectors-btn-confirm-delete", "n_clicks"),
    State("sectors-table", "selected_rows"),
    State("sectors-table", "data"),
    prevent_initial_call=True,
)
def sectors_delete(_, sel_rows, data):
    if not sel_rows:
        return no_update, no_update, no_update, no_update
    _m = lambda r: {"id": r.id, "name": r.name}
    return _bulk_delete(sel_rows, data, svc.delete_sector, svc.get_sectors, _m)


# ===========================================================================
# INDUSTRIAS
# ===========================================================================

@callback(
    Output("industries-table", "data"),
    Output("industries-f-sector_id", "options"),
    Input("industries-table", "id"),
)
def load_industries(_):
    industries = svc.get_industries()
    sectors = svc.get_sectors()
    data = [{"id": i.id, "name": i.name, "sector_name": i.sector.name} for i in industries]
    sector_opts = [{"label": s.name, "value": s.id} for s in sectors]
    return data, sector_opts


@callback(
    Output("industries-modal", "is_open"),
    Output("industries-modal-title", "children"),
    Output("industries-f-name", "value"),
    Output("industries-f-sector_id", "value"),
    Output("industries-editing-id", "data"),
    Input("industries-btn-add", "n_clicks"),
    Input("industries-btn-edit", "n_clicks"),
    Input("industries-btn-cancel", "n_clicks"),
    State("industries-table", "selected_rows"),
    State("industries-table", "data"),
    State("industries-editing-id", "data"),
    prevent_initial_call=True,
)
def industries_modal(n_add, n_edit, n_cancel, sel_rows, data, editing_id):
    from dash import ctx
    t = ctx.triggered_id
    if t == "industries-btn-cancel":
        return False, no_update, no_update, no_update, None
    if t == "industries-btn-add":
        return True, "Nueva industria", "", None, None
    if t == "industries-btn-edit" and sel_rows:
        from app.database import get_session
        from app.models import Industry
        ind = get_session().get(Industry, data[sel_rows[0]]["id"])
        return True, "Editar industria", ind.name, ind.sector_id, ind.id
    return no_update, no_update, no_update, no_update, no_update


@callback(
    Output("industries-table", "data", allow_duplicate=True),
    Output("industries-alert", "children"),
    Output("industries-alert", "is_open"),
    Output("industries-alert", "color"),
    Output("industries-modal", "is_open", allow_duplicate=True),
    Output("industries-modal-error", "children"),
    Output("industries-modal-error", "is_open"),
    Input("industries-btn-save", "n_clicks"),
    State("industries-f-name", "value"),
    State("industries-f-sector_id", "value"),
    State("industries-editing-id", "data"),
    prevent_initial_call=True,
)
def industries_save(_, name, sector_id, editing_id):
    if not name or not sector_id:
        return no_update, no_update, no_update, no_update, no_update, "Completá todos los campos.", True
    try:
        if editing_id:
            svc.update_industry(editing_id, name, int(sector_id))
        else:
            svc.create_industry(name, int(sector_id))
        industries = svc.get_industries()
        data = [{"id": i.id, "name": i.name, "sector_name": i.sector.name} for i in industries]
        return data, "Guardado correctamente.", True, "success", False, "", False
    except Exception as exc:
        return no_update, no_update, no_update, no_update, no_update, str(exc), True


@callback(
    Output("industries-btn-edit", "disabled"),
    Output("industries-btn-delete", "disabled"),
    Input("industries-table", "selected_rows"),
)
def industries_row_selection(sel_rows):
    return len(sel_rows or []) != 1, not bool(sel_rows)


@callback(
    Output("industries-confirm-modal", "is_open"),
    Output("industries-confirm-body", "children"),
    Input("industries-btn-delete", "n_clicks"),
    Input("industries-btn-confirm-delete", "n_clicks"),
    Input("industries-btn-cancel-delete", "n_clicks"),
    State("industries-table", "selected_rows"),
    State("industries-table", "data"),
    prevent_initial_call=True,
)
def industries_confirm(n_del, n_confirm, n_cancel, sel_rows, data):
    from dash import ctx
    if ctx.triggered_id != "industries-btn-delete":
        return False, no_update
    return True, _confirm_body(sel_rows, data)


@callback(
    Output("industries-table", "data", allow_duplicate=True),
    Output("industries-alert", "children", allow_duplicate=True),
    Output("industries-alert", "is_open", allow_duplicate=True),
    Output("industries-alert", "color", allow_duplicate=True),
    Input("industries-btn-confirm-delete", "n_clicks"),
    State("industries-table", "selected_rows"),
    State("industries-table", "data"),
    prevent_initial_call=True,
)
def industries_delete(_, sel_rows, data):
    if not sel_rows:
        return no_update, no_update, no_update, no_update
    _m = lambda i: {"id": i.id, "name": i.name, "sector_name": i.sector.name if i.sector else ""}
    return _bulk_delete(sel_rows, data, svc.delete_industry, svc.get_industries, _m)


# ===========================================================================
# FUENTES DE PRECIOS
# ===========================================================================

@callback(Output("price_sources-table", "data"), Input("price_sources-table", "id"))
def load_price_sources(_):
    rows = svc.get_price_sources()
    return [{"id": r.id, "name": r.name, "description": r.description or ""} for r in rows]


@callback(
    Output("price_sources-modal", "is_open"),
    Output("price_sources-modal-title", "children"),
    Output("price_sources-f-name", "value"),
    Output("price_sources-f-description", "value"),
    Output("price_sources-editing-id", "data"),
    Input("price_sources-btn-add", "n_clicks"),
    Input("price_sources-btn-edit", "n_clicks"),
    Input("price_sources-btn-cancel", "n_clicks"),
    State("price_sources-table", "selected_rows"),
    State("price_sources-table", "data"),
    State("price_sources-editing-id", "data"),
    prevent_initial_call=True,
)
def price_sources_modal(n_add, n_edit, n_cancel, sel_rows, data, editing_id):
    from dash import ctx
    t = ctx.triggered_id
    if t == "price_sources-btn-cancel":
        return False, no_update, no_update, no_update, None
    if t == "price_sources-btn-add":
        return True, "Nueva fuente", "", "", None
    if t == "price_sources-btn-edit" and sel_rows:
        from app.database import get_session
        from app.models import PriceSource
        ps = get_session().get(PriceSource, data[sel_rows[0]]["id"])
        return True, "Editar fuente", ps.name, ps.description or "", ps.id
    return no_update, no_update, no_update, no_update, no_update


@callback(
    Output("price_sources-table", "data", allow_duplicate=True),
    Output("price_sources-alert", "children"),
    Output("price_sources-alert", "is_open"),
    Output("price_sources-alert", "color"),
    Output("price_sources-modal", "is_open", allow_duplicate=True),
    Output("price_sources-modal-error", "children"),
    Output("price_sources-modal-error", "is_open"),
    Input("price_sources-btn-save", "n_clicks"),
    State("price_sources-f-name", "value"),
    State("price_sources-f-description", "value"),
    State("price_sources-editing-id", "data"),
    prevent_initial_call=True,
)
def price_sources_save(_, name, description, editing_id):
    if not name:
        return no_update, no_update, no_update, no_update, no_update, "El nombre es obligatorio.", True
    try:
        if editing_id:
            svc.update_price_source(editing_id, name, description or "")
        else:
            svc.create_price_source(name, description or "")
        rows = svc.get_price_sources()
        data = [{"id": r.id, "name": r.name, "description": r.description or ""} for r in rows]
        return data, "Guardado correctamente.", True, "success", False, "", False
    except Exception as exc:
        return no_update, no_update, no_update, no_update, no_update, str(exc), True


@callback(
    Output("price_sources-btn-edit", "disabled"),
    Output("price_sources-btn-delete", "disabled"),
    Input("price_sources-table", "selected_rows"),
)
def price_sources_row_selection(sel_rows):
    return len(sel_rows or []) != 1, not bool(sel_rows)


@callback(
    Output("price_sources-confirm-modal", "is_open"),
    Output("price_sources-confirm-body", "children"),
    Input("price_sources-btn-delete", "n_clicks"),
    Input("price_sources-btn-confirm-delete", "n_clicks"),
    Input("price_sources-btn-cancel-delete", "n_clicks"),
    State("price_sources-table", "selected_rows"),
    State("price_sources-table", "data"),
    prevent_initial_call=True,
)
def price_sources_confirm(n_del, n_confirm, n_cancel, sel_rows, data):
    from dash import ctx
    if ctx.triggered_id != "price_sources-btn-delete":
        return False, no_update
    return True, _confirm_body(sel_rows, data)


@callback(
    Output("price_sources-table", "data", allow_duplicate=True),
    Output("price_sources-alert", "children", allow_duplicate=True),
    Output("price_sources-alert", "is_open", allow_duplicate=True),
    Output("price_sources-alert", "color", allow_duplicate=True),
    Input("price_sources-btn-confirm-delete", "n_clicks"),
    State("price_sources-table", "selected_rows"),
    State("price_sources-table", "data"),
    prevent_initial_call=True,
)
def price_sources_delete(_, sel_rows, data):
    from app.services.reference_service import _PROTECTED_SOURCES
    if not sel_rows:
        return no_update, no_update, no_update, no_update
    sel_rows = [i for i in sel_rows if data[i].get("name") not in _PROTECTED_SOURCES]
    if not sel_rows:
        return no_update, no_update, no_update, no_update
    _m = lambda r: {"id": r.id, "name": r.name, "description": r.description or ""}
    return _bulk_delete(sel_rows, data, svc.delete_price_source, svc.get_price_sources, _m)


# ===========================================================================
# USUARIOS (admin)
# ===========================================================================

@callback(Output("users-table", "data"), Input("users-table", "id"))
def load_users(_):
    rows = svc.get_users()
    return [{"id": r.id, "username": r.username, "role": r.role, "active": "Sí" if r.active else "No", "created_at": str(r.created_at.date())} for r in rows]


@callback(
    Output("users-modal", "is_open"),
    Output("users-modal-title", "children"),
    Output("users-f-username", "value"),
    Output("users-f-role", "value"),
    Output("users-f-password", "value"),
    Output("users-f-active", "value"),
    Output("users-editing-id", "data"),
    Input("users-btn-add", "n_clicks"),
    Input("users-btn-edit", "n_clicks"),
    Input("users-btn-cancel", "n_clicks"),
    State("users-table", "selected_rows"),
    State("users-table", "data"),
    State("users-editing-id", "data"),
    prevent_initial_call=True,
)
def users_modal(n_add, n_edit, n_cancel, sel_rows, data, editing_id):
    from dash import ctx
    t = ctx.triggered_id
    if t == "users-btn-cancel":
        return False, no_update, no_update, no_update, no_update, no_update, None
    if t == "users-btn-add":
        return True, "Nuevo usuario", "", "analyst", "", True, None
    if t == "users-btn-edit" and sel_rows:
        from app.database import get_session
        from app.models import User
        u = get_session().get(User, data[sel_rows[0]]["id"])
        return True, "Editar usuario", u.username, u.role, "", u.active, u.id
    return no_update, no_update, no_update, no_update, no_update, no_update, no_update


@callback(
    Output("users-table", "data", allow_duplicate=True),
    Output("users-alert", "children"),
    Output("users-alert", "is_open"),
    Output("users-alert", "color"),
    Output("users-modal", "is_open", allow_duplicate=True),
    Output("users-modal-error", "children"),
    Output("users-modal-error", "is_open"),
    Input("users-btn-save", "n_clicks"),
    State("users-f-username", "value"),
    State("users-f-role", "value"),
    State("users-f-password", "value"),
    State("users-f-active", "value"),
    State("users-editing-id", "data"),
    prevent_initial_call=True,
)
def users_save(_, username, role, password, active, editing_id):
    if not username or not role:
        return no_update, no_update, no_update, no_update, no_update, "Completá los campos obligatorios.", True
    if not editing_id and not password:
        return no_update, no_update, no_update, no_update, no_update, "La contraseña es obligatoria para nuevos usuarios.", True
    try:
        if editing_id:
            svc.update_user(editing_id, username, role, bool(active), password or None)
        else:
            svc.create_user(username, password, role)
        rows = svc.get_users()
        data = [{"id": r.id, "username": r.username, "role": r.role, "active": "Sí" if r.active else "No", "created_at": str(r.created_at.date())} for r in rows]
        return data, "Guardado correctamente.", True, "success", False, "", False
    except Exception as exc:
        return no_update, no_update, no_update, no_update, no_update, str(exc), True


@callback(
    Output("users-btn-edit", "disabled"),
    Output("users-btn-delete", "disabled"),
    Input("users-table", "selected_rows"),
)
def users_row_selection(sel_rows):
    return len(sel_rows or []) != 1, not bool(sel_rows)


@callback(
    Output("users-confirm-modal", "is_open"),
    Output("users-confirm-body", "children"),
    Input("users-btn-delete", "n_clicks"),
    Input("users-btn-confirm-delete", "n_clicks"),
    Input("users-btn-cancel-delete", "n_clicks"),
    State("users-table", "selected_rows"),
    State("users-table", "data"),
    prevent_initial_call=True,
)
def users_confirm(n_del, n_confirm, n_cancel, sel_rows, data):
    from dash import ctx
    if ctx.triggered_id != "users-btn-delete":
        return False, no_update
    return True, _confirm_body(sel_rows, data, name_field="username")


@callback(
    Output("users-table", "data", allow_duplicate=True),
    Output("users-alert", "children", allow_duplicate=True),
    Output("users-alert", "is_open", allow_duplicate=True),
    Output("users-alert", "color", allow_duplicate=True),
    Input("users-btn-confirm-delete", "n_clicks"),
    State("users-table", "selected_rows"),
    State("users-table", "data"),
    prevent_initial_call=True,
)
def users_delete(_, sel_rows, data):
    if not sel_rows:
        return no_update, no_update, no_update, no_update
    _m = lambda r: {"id": r.id, "username": r.username, "role": r.role, "active": "Sí" if r.active else "No", "created_at": str(r.created_at.date())}
    return _bulk_delete(sel_rows, data, svc.delete_user, svc.get_users, _m)
