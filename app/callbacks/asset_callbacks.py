import threading

from dash import Input, Output, State, callback, no_update

import app.services.asset_service as asset_svc
import app.services.price_service as price_svc
import app.services.reference_service as ref_svc


def _asset_to_row(a) -> dict:
    return {
        "id": a.id,
        "ticker": a.ticker,
        "name": a.name,
        "country_name": a.country.name if a.country else "",
        "market_name": a.market.name if a.market else "",
        "instrument_type_name": a.instrument_type.name if a.instrument_type else "",
        "currency_iso": a.currency.iso_code if a.currency else "",
        "sector_name": a.sector.name if a.sector else "",
        "source_name": a.price_source.name,
    }


def _get_form_options():
    from app.database import get_session
    from app.models import Asset
    sources    = ref_svc.get_price_sources(only_active=True)
    currencies = ref_svc.get_currencies()
    countries  = ref_svc.get_countries()
    markets    = ref_svc.get_markets()
    itypes     = ref_svc.get_instrument_types()
    sectors    = ref_svc.get_sectors()
    industries = ref_svc.get_industries()
    all_assets = get_session().query(Asset).filter(Asset.active == True).order_by(Asset.ticker).all()
    return (
        [{"label": s.name, "value": s.id} for s in sources],
        [{"label": f"{c.iso_code} - {c.name}", "value": c.id} for c in currencies],
        [{"label": c.name, "value": c.id} for c in countries],
        [{"label": m.name, "value": m.id} for m in markets],
        [{"label": it.name, "value": it.id} for it in itypes],
        [{"label": "", "value": ""}] + [{"label": s.name, "value": s.id} for s in sectors],
        [{"label": "", "value": ""}] + [{"label": i.name, "value": i.id} for i in industries],
        [{"label": f"{a.ticker} — {a.name}", "value": a.id} for a in all_assets],
    )


def _match_option(opts: list, name: str | None):
    """Busca un valor por nombre (case-insensitive) en una lista de opciones."""
    if not name:
        return no_update, None
    name_lower = name.lower()
    for opt in opts:
        if opt.get("label", "").lower() == name_lower:
            return opt["value"], None
    return no_update, name  # no encontrado → devuelve el nombre para el mensaje


@callback(
    Output("assets-table", "data"),
    Input("assets-table", "id"),
)
def load_assets(_):
    return [_asset_to_row(a) for a in asset_svc.get_assets()]


@callback(
    Output("assets-btn-edit", "disabled"),
    Output("assets-btn-delete", "disabled"),
    Input("assets-table", "selected_rows"),
)
def assets_row_selection(sel_rows):
    d = not bool(sel_rows)
    return d, d


@callback(
    Output("assets-modal", "is_open"),
    Output("assets-modal-title", "children"),
    Output("assets-f-ticker", "value"),
    Output("assets-f-name", "value"),
    Output("assets-f-price_source_id", "options"),
    Output("assets-f-price_source_id", "value"),
    Output("assets-f-currency_id", "options"),
    Output("assets-f-currency_id", "value"),
    Output("assets-f-country_id", "options"),
    Output("assets-f-country_id", "value"),
    Output("assets-f-market_id", "options"),
    Output("assets-f-market_id", "value"),
    Output("assets-f-instrument_type_id", "options"),
    Output("assets-f-instrument_type_id", "value"),
    Output("assets-f-sector_id", "options"),
    Output("assets-f-sector_id", "value"),
    Output("assets-f-industry_id", "options"),
    Output("assets-f-industry_id", "value"),
    Output("assets-f-benchmark_id", "options"),
    Output("assets-f-benchmark_id", "value"),
    Output("assets-editing-id", "data"),
    Output("assets-autocomplete-alert", "children"),
    Output("assets-autocomplete-alert", "is_open"),
    Output("assets-form-error", "children"),
    Output("assets-form-error", "is_open"),
    Input("assets-btn-add", "n_clicks"),
    Input("assets-btn-edit", "n_clicks"),
    Input("assets-btn-cancel", "n_clicks"),
    Input("assets-btn-autocomplete", "n_clicks"),
    State("assets-table", "selected_rows"),
    State("assets-table", "data"),
    State("assets-editing-id", "data"),
    State("assets-f-ticker", "value"),
    State("assets-f-price_source_id", "value"),
    State("assets-f-currency_id", "options"),
    State("assets-f-sector_id", "options"),
    State("assets-f-industry_id", "options"),
    prevent_initial_call=True,
)
def assets_modal(
    n_add, n_edit, n_cancel, n_auto,
    sel_rows, data, editing_id,
    ticker, source_id, currency_options, sector_options, industry_options,
):
    from dash import ctx
    t = ctx.triggered_id
    _nu = no_update
    src_opts, cur_opts, country_opts, market_opts, itype_opts, sector_opts, ind_opts, bm_opts = _get_form_options()

    if t == "assets-btn-cancel":
        return False, *([_nu] * 24)

    if t == "assets-btn-autocomplete":
        if not ticker or not source_id:
            return (*([_nu] * 22), "Ingresá el ticker y seleccioná la fuente antes de autocompletar.", True, _nu, False)
        try:
            meta = asset_svc.autocomplete_from_source(ticker, int(source_id))

            created = []

            def _goc(fn, val, label):
                if not val:
                    return _nu, None
                obj, is_new = fn(val)
                if is_new:
                    created.append(f"{label} '{val}'")
                return obj.id, obj.id

            # País
            country_id_new, _ = _goc(ref_svc.get_or_create_country,
                                      meta.get("country"), "país")

            # Moneda
            currency_id_new, _ = _goc(ref_svc.get_or_create_currency,
                                       meta.get("currency_iso"), "moneda")

            # Mercado (usa fullExchangeName, con country_id ya resuelto)
            _market_name = meta.get("exchange_name") or meta.get("exchange")
            market_id_new = _nu
            if _market_name:
                _mobj, _is_new = ref_svc.get_or_create_market(_market_name)
                market_id_new = _mobj.id
                if _is_new:
                    created.append(f"mercado '{_market_name}'")

            # Tipo de instrumento (quoteType)
            itype_id_new, _ = _goc(ref_svc.get_or_create_instrument_type,
                                    meta.get("quote_type"), "tipo de instrumento")

            # Sector
            sector_obj_id = None
            if meta.get("sector"):
                sec_obj, is_new = ref_svc.get_or_create_sector(meta["sector"])
                sector_obj_id = sec_obj.id
                if is_new:
                    created.append(f"sector '{meta['sector']}'")

            # Industria
            industry_obj_id = None
            if meta.get("industry"):
                ind_obj, is_new = ref_svc.get_or_create_industry(
                    meta["industry"], sector_obj_id
                )
                industry_obj_id = ind_obj.id
                if is_new:
                    created.append(f"industria '{meta['industry']}'")

            # Recargar opciones actualizadas
            _, cur_opts_new, country_opts_new, market_opts_new, itype_opts_new, \
                sector_opts_new, ind_opts_new, bm_opts_new = _get_form_options()

            msg = "Autocompletado. Revisá los campos antes de guardar."
            if created:
                msg += " — Creados: " + ", ".join(created) + "."

            return (
                _nu, _nu,
                _nu, meta.get("name") or _nu,
                _nu, _nu,
                cur_opts_new, currency_id_new,
                country_opts_new, country_id_new,
                market_opts_new, market_id_new,
                itype_opts_new, itype_id_new,
                sector_opts_new, sector_obj_id or _nu,
                ind_opts_new, industry_obj_id or _nu,
                bm_opts_new, _nu,
                _nu,
                msg, True,
                _nu, False,
            )
        except Exception as exc:
            return (*([_nu] * 21), str(exc), True, _nu, False)

    if t == "assets-btn-add":
        return (
            True, "Nuevo activo",
            "", "",
            src_opts, None,
            cur_opts, None,
            country_opts, None,
            market_opts, None,
            itype_opts, None,
            sector_opts, None,
            ind_opts, None,
            bm_opts, None,
            None,
            _nu, False,
            "", False,
        )

    if t == "assets-btn-edit" and sel_rows:
        a = asset_svc.get_asset_by_id(data[sel_rows[0]]["id"])
        return (
            True, f"Editar activo — {a.ticker}",
            a.ticker, a.name,
            src_opts, a.price_source_id,
            cur_opts, a.currency_id,
            country_opts, a.country_id,
            market_opts, a.market_id,
            itype_opts, a.instrument_type_id,
            sector_opts, a.sector_id,
            ind_opts, a.industry_id,
            bm_opts, a.benchmark_id,
            a.id,
            _nu, False,
            "", False,
        )

    return (False, *([_nu] * 24))


@callback(
    Output("assets-table", "data", allow_duplicate=True),
    Output("assets-alert", "children"),
    Output("assets-alert", "is_open"),
    Output("assets-alert", "color"),
    Output("assets-modal", "is_open", allow_duplicate=True),
    Output("assets-form-error", "children", allow_duplicate=True),
    Output("assets-form-error", "is_open", allow_duplicate=True),
    Input("assets-btn-save", "n_clicks"),
    State("assets-f-ticker", "value"),
    State("assets-f-name", "value"),
    State("assets-f-country_id", "value"),
    State("assets-f-market_id", "value"),
    State("assets-f-instrument_type_id", "value"),
    State("assets-f-currency_id", "value"),
    State("assets-f-price_source_id", "value"),
    State("assets-f-sector_id", "value"),
    State("assets-f-industry_id", "value"),
    State("assets-f-benchmark_id", "value"),
    State("assets-editing-id", "data"),
    prevent_initial_call=True,
)
def assets_save(
    _, ticker, name, country_id, market_id, itype_id, currency_id,
    source_id, sector_id, industry_id, benchmark_id, editing_id
):
    _nu = no_update

    def _empty(v):
        if v is None or v == "":
            return True
        try:
            import math
            return math.isnan(float(v))
        except (TypeError, ValueError):
            return False

    required = {"Ticker": ticker, "Fuente de precios": source_id}
    missing = [label for label, v in required.items() if _empty(v)]
    if missing:
        msg = "Campos obligatorios sin completar: " + ", ".join(missing) + "."
        return _nu, _nu, False, _nu, _nu, msg, True

    def _int(v):
        return int(v) if not _empty(v) else None

    try:
        kwargs = dict(
            ticker=ticker,
            name=name or None,
            country_id=_int(country_id),
            market_id=_int(market_id),
            instrument_type_id=_int(itype_id),
            currency_id=_int(currency_id),
            price_source_id=int(source_id),
            sector_id=_int(sector_id),
            industry_id=_int(industry_id),
            benchmark_id=_int(benchmark_id),
        )
        if editing_id:
            asset_svc.update_asset(editing_id, **kwargs)
            msg = f"{ticker.upper()} actualizado correctamente."
        else:
            new_asset = asset_svc.create_asset(**kwargs)
            # Descargar precios en background
            threading.Thread(
                target=price_svc.update_asset_prices,
                args=(new_asset.id,),
                daemon=True,
            ).start()
            msg = f"{ticker.upper()} creado. Descarga de precios iniciada en background."

        return (
            [_asset_to_row(a) for a in asset_svc.get_assets()],
            msg, True, "success",
            False,   # cerrar modal
            "", False,
        )
    except Exception as exc:
        # Error de negocio: modal se queda abierto
        return _nu, _nu, False, _nu, _nu, str(exc), True



@callback(
    Output("assets-confirm-modal", "is_open"),
    Input("assets-btn-delete", "n_clicks"),
    Input("assets-btn-confirm-delete", "n_clicks"),
    Input("assets-btn-cancel-delete", "n_clicks"),
    prevent_initial_call=True,
)
def assets_confirm_modal(n_del, n_confirm, n_cancel):
    from dash import ctx
    return ctx.triggered_id == "assets-btn-delete"


@callback(
    Output("assets-table", "data", allow_duplicate=True),
    Output("assets-alert", "children", allow_duplicate=True),
    Output("assets-alert", "is_open", allow_duplicate=True),
    Output("assets-alert", "color", allow_duplicate=True),
    Input("assets-btn-confirm-delete", "n_clicks"),
    State("assets-table", "selected_rows"),
    State("assets-table", "data"),
    prevent_initial_call=True,
)
def assets_delete(_, sel_rows, data):
    if not sel_rows:
        return no_update, no_update, no_update, no_update
    try:
        asset_svc.delete_asset(data[sel_rows[0]]["id"])
        return (
            [_asset_to_row(a) for a in asset_svc.get_assets()],
            "Activo eliminado.", True, "success",
        )
    except Exception as exc:
        return no_update, str(exc), True, "danger"
