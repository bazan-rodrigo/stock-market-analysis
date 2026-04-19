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
    Input("countries-btn-save", "n_clicks"),
    State("countries-table", "selected_rows"),
    State("countries-table", "data"),
    State("countries-editing-id", "data"),
    prevent_initial_call=True,
)
def countries_modal(n_add, n_edit, n_cancel, n_save, sel_rows, data, editing_id):
    from dash import ctx
    trigger = ctx.triggered_id
    if trigger in ("countries-btn-cancel", "countries-btn-save"):
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
    Input("countries-btn-save", "n_clicks"),
    State("countries-f-name", "value"),
    State("countries-f-iso_code", "value"),
    State("countries-editing-id", "data"),
    prevent_initial_call=True,
)
def countries_save(n_clicks, name, iso_code, editing_id):
    if not name or not iso_code:
        return no_update, "Completá todos los campos.", True, "danger"
    try:
        if editing_id:
            svc.update_country(editing_id, name, iso_code)
        else:
            svc.create_country(name, iso_code)
        rows = svc.get_countries()
        data = [{"id": r.id, "name": r.name, "iso_code": r.iso_code} for r in rows]
        return data, "Guardado correctamente.", True, "success"
    except Exception as exc:
        return no_update, str(exc), True, "danger"


@callback(
    Output("countries-btn-edit", "disabled"),
    Output("countries-btn-delete", "disabled"),
    Input("countries-table", "selected_rows"),
)
def countries_row_selection(sel_rows):
    disabled = not bool(sel_rows)
    return disabled, disabled


@callback(
    Output("countries-confirm-modal", "is_open"),
    Input("countries-btn-delete", "n_clicks"),
    Input("countries-btn-confirm-delete", "n_clicks"),
    Input("countries-btn-cancel-delete", "n_clicks"),
    prevent_initial_call=True,
)
def countries_confirm_modal(n_del, n_confirm, n_cancel):
    from dash import ctx
    t = ctx.triggered_id
    if t == "countries-btn-delete":
        return True
    return False


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
def countries_delete(n_clicks, sel_rows, data):
    if not sel_rows:
        return no_update, no_update, no_update, no_update
    row_id = data[sel_rows[0]]["id"]
    try:
        svc.delete_country(row_id)
        rows = svc.get_countries()
        table_data = [{"id": r.id, "name": r.name, "iso_code": r.iso_code} for r in rows]
        return table_data, "Eliminado correctamente.", True, "success"
    except Exception as exc:
        return no_update, str(exc), True, "danger"


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
    Input("currencies-btn-save", "n_clicks"),
    State("currencies-table", "selected_rows"),
    State("currencies-table", "data"),
    State("currencies-editing-id", "data"),
    prevent_initial_call=True,
)
def currencies_modal(n_add, n_edit, n_cancel, n_save, sel_rows, data, editing_id):
    from dash import ctx
    t = ctx.triggered_id
    if t in ("currencies-btn-cancel", "currencies-btn-save"):
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
    Input("currencies-btn-save", "n_clicks"),
    State("currencies-f-name", "value"),
    State("currencies-f-iso_code", "value"),
    State("currencies-editing-id", "data"),
    prevent_initial_call=True,
)
def currencies_save(n_clicks, name, iso_code, editing_id):
    if not name or not iso_code:
        return no_update, "Completá todos los campos.", True, "danger"
    try:
        if editing_id:
            svc.update_currency(editing_id, name, iso_code)
        else:
            svc.create_currency(name, iso_code)
        rows = svc.get_currencies()
        data = [{"id": r.id, "name": r.name, "iso_code": r.iso_code} for r in rows]
        return data, "Guardado correctamente.", True, "success"
    except Exception as exc:
        return no_update, str(exc), True, "danger"


@callback(
    Output("currencies-btn-edit", "disabled"),
    Output("currencies-btn-delete", "disabled"),
    Input("currencies-table", "selected_rows"),
)
def currencies_row_selection(sel_rows):
    d = not bool(sel_rows)
    return d, d


@callback(
    Output("currencies-confirm-modal", "is_open"),
    Input("currencies-btn-delete", "n_clicks"),
    Input("currencies-btn-confirm-delete", "n_clicks"),
    Input("currencies-btn-cancel-delete", "n_clicks"),
    prevent_initial_call=True,
)
def currencies_confirm_modal(n_del, n_confirm, n_cancel):
    from dash import ctx
    return ctx.triggered_id == "currencies-btn-delete"


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
    try:
        svc.delete_currency(data[sel_rows[0]]["id"])
        rows = svc.get_currencies()
        table_data = [{"id": r.id, "name": r.name, "iso_code": r.iso_code} for r in rows]
        return table_data, "Eliminado correctamente.", True, "success"
    except Exception as exc:
        return no_update, str(exc), True, "danger"


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
    assets    = get_session().query(Asset).filter(Asset.active == True).order_by(Asset.ticker).all()
    data = [{"id": m.id, "name": m.name, "country_name": m.country.name if m.country else ""} for m in markets]
    country_opts   = [{"label": c.name, "value": c.id} for c in countries]
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
    Input("markets-btn-save", "n_clicks"),
    State("markets-table", "selected_rows"),
    State("markets-table", "data"),
    State("markets-editing-id", "data"),
    prevent_initial_call=True,
)
def markets_modal(n_add, n_edit, n_cancel, n_save, sel_rows, data, editing_id):
    from dash import ctx
    t = ctx.triggered_id
    if t in ("markets-btn-cancel", "markets-btn-save"):
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
    Input("markets-btn-save", "n_clicks"),
    State("markets-f-name", "value"),
    State("markets-f-country_id", "value"),
    State("markets-f-benchmark_id", "value"),
    State("markets-editing-id", "data"),
    prevent_initial_call=True,
)
def markets_save(_, name, country_id, benchmark_id, editing_id):
    if not name or not country_id:
        return no_update, "Completá todos los campos.", True, "danger"
    try:
        bm = int(benchmark_id) if benchmark_id else None
        if editing_id:
            svc.update_market(editing_id, name, int(country_id), bm)
        else:
            svc.create_market(name, int(country_id), bm)
        markets = svc.get_markets()
        data = [{"id": m.id, "name": m.name, "country_name": m.country.name if m.country else ""} for m in markets]
        return data, "Guardado correctamente.", True, "success"
    except Exception as exc:
        return no_update, str(exc), True, "danger"


@callback(
    Output("markets-btn-edit", "disabled"),
    Output("markets-btn-delete", "disabled"),
    Input("markets-table", "selected_rows"),
)
def markets_row_selection(sel_rows):
    d = not bool(sel_rows)
    return d, d


@callback(
    Output("markets-confirm-modal", "is_open"),
    Input("markets-btn-delete", "n_clicks"),
    Input("markets-btn-confirm-delete", "n_clicks"),
    Input("markets-btn-cancel-delete", "n_clicks"),
    prevent_initial_call=True,
)
def markets_confirm_modal(n_del, n_confirm, n_cancel):
    from dash import ctx
    return ctx.triggered_id == "markets-btn-delete"


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
    try:
        svc.delete_market(data[sel_rows[0]]["id"])
        markets = svc.get_markets()
        table_data = [{"id": m.id, "name": m.name, "country_name": m.country.name} for m in markets]
        return table_data, "Eliminado correctamente.", True, "success"
    except Exception as exc:
        return no_update, str(exc), True, "danger"


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
    Input("instrument_types-btn-save", "n_clicks"),
    State("instrument_types-table", "selected_rows"),
    State("instrument_types-table", "data"),
    State("instrument_types-editing-id", "data"),
    prevent_initial_call=True,
)
def instrument_types_modal(n_add, n_edit, n_cancel, n_save, sel_rows, data, editing_id):
    from dash import ctx
    t = ctx.triggered_id
    if t in ("instrument_types-btn-cancel", "instrument_types-btn-save"):
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
    Input("instrument_types-btn-save", "n_clicks"),
    State("instrument_types-f-name", "value"),
    State("instrument_types-f-default_currency_id", "value"),
    State("instrument_types-editing-id", "data"),
    prevent_initial_call=True,
)
def instrument_types_save(_, name, currency_id, editing_id):
    if not name or not currency_id:
        return no_update, "Completá todos los campos.", True, "danger"
    try:
        if editing_id:
            svc.update_instrument_type(editing_id, name, int(currency_id))
        else:
            svc.create_instrument_type(name, int(currency_id))
        itypes = svc.get_instrument_types()
        data = [{"id": it.id, "name": it.name, "currency_name": it.default_currency.iso_code} for it in itypes]
        return data, "Guardado correctamente.", True, "success"
    except Exception as exc:
        return no_update, str(exc), True, "danger"


@callback(
    Output("instrument_types-btn-edit", "disabled"),
    Output("instrument_types-btn-delete", "disabled"),
    Input("instrument_types-table", "selected_rows"),
)
def instrument_types_row_selection(sel_rows):
    d = not bool(sel_rows)
    return d, d


@callback(
    Output("instrument_types-confirm-modal", "is_open"),
    Input("instrument_types-btn-delete", "n_clicks"),
    Input("instrument_types-btn-confirm-delete", "n_clicks"),
    Input("instrument_types-btn-cancel-delete", "n_clicks"),
    prevent_initial_call=True,
)
def instrument_types_confirm(n_del, n_confirm, n_cancel):
    from dash import ctx
    return ctx.triggered_id == "instrument_types-btn-delete"


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
    try:
        svc.delete_instrument_type(data[sel_rows[0]]["id"])
        itypes = svc.get_instrument_types()
        table_data = [{"id": it.id, "name": it.name, "currency_name": it.default_currency.iso_code} for it in itypes]
        return table_data, "Eliminado correctamente.", True, "success"
    except Exception as exc:
        return no_update, str(exc), True, "danger"


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
    Input("sectors-btn-save", "n_clicks"),
    State("sectors-table", "selected_rows"),
    State("sectors-table", "data"),
    State("sectors-editing-id", "data"),
    prevent_initial_call=True,
)
def sectors_modal(n_add, n_edit, n_cancel, n_save, sel_rows, data, editing_id):
    from dash import ctx
    t = ctx.triggered_id
    if t in ("sectors-btn-cancel", "sectors-btn-save"):
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
    Input("sectors-btn-save", "n_clicks"),
    State("sectors-f-name", "value"),
    State("sectors-editing-id", "data"),
    prevent_initial_call=True,
)
def sectors_save(_, name, editing_id):
    if not name:
        return no_update, "Completá el nombre.", True, "danger"
    try:
        if editing_id:
            svc.update_sector(editing_id, name)
        else:
            svc.create_sector(name)
        data = [{"id": r.id, "name": r.name} for r in svc.get_sectors()]
        return data, "Guardado correctamente.", True, "success"
    except Exception as exc:
        return no_update, str(exc), True, "danger"


@callback(
    Output("sectors-btn-edit", "disabled"),
    Output("sectors-btn-delete", "disabled"),
    Input("sectors-table", "selected_rows"),
)
def sectors_row_selection(sel_rows):
    d = not bool(sel_rows)
    return d, d


@callback(
    Output("sectors-confirm-modal", "is_open"),
    Input("sectors-btn-delete", "n_clicks"),
    Input("sectors-btn-confirm-delete", "n_clicks"),
    Input("sectors-btn-cancel-delete", "n_clicks"),
    prevent_initial_call=True,
)
def sectors_confirm(n_del, n_confirm, n_cancel):
    from dash import ctx
    return ctx.triggered_id == "sectors-btn-delete"


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
    try:
        svc.delete_sector(data[sel_rows[0]]["id"])
        table_data = [{"id": r.id, "name": r.name} for r in svc.get_sectors()]
        return table_data, "Eliminado correctamente.", True, "success"
    except Exception as exc:
        return no_update, str(exc), True, "danger"


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
    Input("industries-btn-save", "n_clicks"),
    State("industries-table", "selected_rows"),
    State("industries-table", "data"),
    State("industries-editing-id", "data"),
    prevent_initial_call=True,
)
def industries_modal(n_add, n_edit, n_cancel, n_save, sel_rows, data, editing_id):
    from dash import ctx
    t = ctx.triggered_id
    if t in ("industries-btn-cancel", "industries-btn-save"):
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
    Input("industries-btn-save", "n_clicks"),
    State("industries-f-name", "value"),
    State("industries-f-sector_id", "value"),
    State("industries-editing-id", "data"),
    prevent_initial_call=True,
)
def industries_save(_, name, sector_id, editing_id):
    if not name or not sector_id:
        return no_update, "Completá todos los campos.", True, "danger"
    try:
        if editing_id:
            svc.update_industry(editing_id, name, int(sector_id))
        else:
            svc.create_industry(name, int(sector_id))
        industries = svc.get_industries()
        data = [{"id": i.id, "name": i.name, "sector_name": i.sector.name} for i in industries]
        return data, "Guardado correctamente.", True, "success"
    except Exception as exc:
        return no_update, str(exc), True, "danger"


@callback(
    Output("industries-btn-edit", "disabled"),
    Output("industries-btn-delete", "disabled"),
    Input("industries-table", "selected_rows"),
)
def industries_row_selection(sel_rows):
    d = not bool(sel_rows)
    return d, d


@callback(
    Output("industries-confirm-modal", "is_open"),
    Input("industries-btn-delete", "n_clicks"),
    Input("industries-btn-confirm-delete", "n_clicks"),
    Input("industries-btn-cancel-delete", "n_clicks"),
    prevent_initial_call=True,
)
def industries_confirm(n_del, n_confirm, n_cancel):
    from dash import ctx
    return ctx.triggered_id == "industries-btn-delete"


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
    try:
        svc.delete_industry(data[sel_rows[0]]["id"])
        industries = svc.get_industries()
        table_data = [{"id": i.id, "name": i.name, "sector_name": i.sector.name} for i in industries]
        return table_data, "Eliminado correctamente.", True, "success"
    except Exception as exc:
        return no_update, str(exc), True, "danger"


# ===========================================================================
# FUENTES DE PRECIOS
# ===========================================================================

@callback(Output("price_sources-table", "data"), Input("price_sources-table", "id"))
def load_price_sources(_):
    rows = svc.get_price_sources()
    return [{"id": r.id, "name": r.name, "description": r.description or "", "active": "Sí" if r.active else "No"} for r in rows]


@callback(
    Output("price_sources-modal", "is_open"),
    Output("price_sources-modal-title", "children"),
    Output("price_sources-f-name", "value"),
    Output("price_sources-f-description", "value"),
    Output("price_sources-f-active", "value"),
    Output("price_sources-editing-id", "data"),
    Input("price_sources-btn-add", "n_clicks"),
    Input("price_sources-btn-edit", "n_clicks"),
    Input("price_sources-btn-cancel", "n_clicks"),
    Input("price_sources-btn-save", "n_clicks"),
    State("price_sources-table", "selected_rows"),
    State("price_sources-table", "data"),
    State("price_sources-editing-id", "data"),
    prevent_initial_call=True,
)
def price_sources_modal(n_add, n_edit, n_cancel, n_save, sel_rows, data, editing_id):
    from dash import ctx
    t = ctx.triggered_id
    if t in ("price_sources-btn-cancel", "price_sources-btn-save"):
        return False, no_update, no_update, no_update, no_update, None
    if t == "price_sources-btn-add":
        return True, "Nueva fuente", "", "", True, None
    if t == "price_sources-btn-edit" and sel_rows:
        from app.database import get_session
        from app.models import PriceSource
        ps = get_session().get(PriceSource, data[sel_rows[0]]["id"])
        return True, "Editar fuente", ps.name, ps.description or "", ps.active, ps.id
    return no_update, no_update, no_update, no_update, no_update, no_update


@callback(
    Output("price_sources-table", "data", allow_duplicate=True),
    Output("price_sources-alert", "children"),
    Output("price_sources-alert", "is_open"),
    Output("price_sources-alert", "color"),
    Input("price_sources-btn-save", "n_clicks"),
    State("price_sources-f-name", "value"),
    State("price_sources-f-description", "value"),
    State("price_sources-f-active", "value"),
    State("price_sources-editing-id", "data"),
    prevent_initial_call=True,
)
def price_sources_save(_, name, description, active, editing_id):
    if not name:
        return no_update, "El nombre es obligatorio.", True, "danger"
    try:
        active_bool = bool(active)
        if editing_id:
            svc.update_price_source(editing_id, name, description or "", active_bool)
        else:
            svc.create_price_source(name, description or "", active_bool)
        rows = svc.get_price_sources()
        data = [{"id": r.id, "name": r.name, "description": r.description or "", "active": "Sí" if r.active else "No"} for r in rows]
        return data, "Guardado correctamente.", True, "success"
    except Exception as exc:
        return no_update, str(exc), True, "danger"


@callback(
    Output("price_sources-btn-edit", "disabled"),
    Output("price_sources-btn-delete", "disabled"),
    Input("price_sources-table", "selected_rows"),
)
def price_sources_row_selection(sel_rows):
    d = not bool(sel_rows)
    return d, d


@callback(
    Output("price_sources-confirm-modal", "is_open"),
    Input("price_sources-btn-delete", "n_clicks"),
    Input("price_sources-btn-confirm-delete", "n_clicks"),
    Input("price_sources-btn-cancel-delete", "n_clicks"),
    prevent_initial_call=True,
)
def price_sources_confirm(n_del, n_confirm, n_cancel):
    from dash import ctx
    return ctx.triggered_id == "price_sources-btn-delete"


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
    if not sel_rows:
        return no_update, no_update, no_update, no_update
    try:
        svc.delete_price_source(data[sel_rows[0]]["id"])
        rows = svc.get_price_sources()
        table_data = [{"id": r.id, "name": r.name, "description": r.description or "", "active": "Sí" if r.active else "No"} for r in rows]
        return table_data, "Eliminado correctamente.", True, "success"
    except Exception as exc:
        return no_update, str(exc), True, "danger"


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
    Input("users-btn-save", "n_clicks"),
    State("users-table", "selected_rows"),
    State("users-table", "data"),
    State("users-editing-id", "data"),
    prevent_initial_call=True,
)
def users_modal(n_add, n_edit, n_cancel, n_save, sel_rows, data, editing_id):
    from dash import ctx
    t = ctx.triggered_id
    if t in ("users-btn-cancel", "users-btn-save"):
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
        return no_update, "Completá los campos obligatorios.", True, "danger"
    if not editing_id and not password:
        return no_update, "La contraseña es obligatoria para nuevos usuarios.", True, "danger"
    try:
        if editing_id:
            svc.update_user(editing_id, username, role, bool(active), password or None)
        else:
            svc.create_user(username, password, role)
        rows = svc.get_users()
        data = [{"id": r.id, "username": r.username, "role": r.role, "active": "Sí" if r.active else "No", "created_at": str(r.created_at.date())} for r in rows]
        return data, "Guardado correctamente.", True, "success"
    except Exception as exc:
        return no_update, str(exc), True, "danger"


@callback(
    Output("users-btn-edit", "disabled"),
    Output("users-btn-delete", "disabled"),
    Input("users-table", "selected_rows"),
)
def users_row_selection(sel_rows):
    d = not bool(sel_rows)
    return d, d


@callback(
    Output("users-confirm-modal", "is_open"),
    Input("users-btn-delete", "n_clicks"),
    Input("users-btn-confirm-delete", "n_clicks"),
    Input("users-btn-cancel-delete", "n_clicks"),
    prevent_initial_call=True,
)
def users_confirm(n_del, n_confirm, n_cancel):
    from dash import ctx
    return ctx.triggered_id == "users-btn-delete"


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
    try:
        svc.delete_user(data[sel_rows[0]]["id"])
        rows = svc.get_users()
        table_data = [{"id": r.id, "username": r.username, "role": r.role, "active": "Sí" if r.active else "No", "created_at": str(r.created_at.date())} for r in rows]
        return table_data, "Eliminado correctamente.", True, "success"
    except Exception as exc:
        return no_update, str(exc), True, "danger"
