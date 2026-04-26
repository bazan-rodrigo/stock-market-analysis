import threading

from dash import Input, Output, State, callback, html, no_update, ALL, ctx
import dash_bootstrap_components as dbc

import app.services.currency_conversion_service as svc
from app.utils import safe_callback

_sync_state = {
    "running": False, "current": 0, "total": 0,
    "msg": "", "error": None, "color": "success",
}

_th = {"fontSize": "0.76rem", "color": "#9ca3af", "fontWeight": "normal",
       "padding": "5px 10px", "borderBottom": "1px solid #374151"}
_td = {"fontSize": "0.82rem", "padding": "5px 10px", "borderBottom": "1px solid #1f2937"}


def _build_divisors_table() -> html.Div:
    divisors = svc.get_divisors()
    if not divisors:
        return html.P("Sin divisores configurados.", className="text-muted small")

    rows = [
        html.Tr([
            html.Td(d.currency.iso_code or d.currency.name,
                    style={**_td, "fontWeight": "bold", "fontFamily": "monospace"}),
            html.Td(d.divisor_asset.ticker,
                    style={**_td, "fontWeight": "bold", "fontFamily": "monospace"}),
            html.Td(d.divisor_asset.name or "—", style=_td),
            html.Td(
                dbc.Button("Eliminar",
                           id={"type": "ars-remove-div", "index": d.id},
                           color="outline-danger", size="sm",
                           style={"fontSize": "0.72rem", "padding": "1px 8px"}),
                style={**_td, "textAlign": "right"},
            ),
        ])
        for d in divisors
    ]

    return html.Table([
        html.Thead(html.Tr([
            html.Th("Moneda",  style=_th),
            html.Th("Ticker",  style=_th),
            html.Th("Nombre",  style=_th),
            html.Th("",        style={**_th, "width": "80px"}),
        ])),
        html.Tbody(rows),
    ], style={"width": "100%", "borderCollapse": "collapse"})


def _build_stats() -> html.Div:
    stats = svc.get_stats()
    if not stats:
        return html.P("Sin divisores configurados.", className="text-muted small")

    lines = []
    for st in stats:
        cur = st["currency"]
        label = cur.iso_code or cur.name
        lines.append(html.Div(
            f"{label}: {st['n_divisors']} divisor(es) × {st['n_base']} activos "
            f"= {st['n_expected']} esperados — "
            f"{st['n_existing']} existentes, {st['n_missing']} faltantes.",
            className="mb-1",
        ))
    return html.Div(lines)


# ── Cargar opciones + tabla inicial ──────────────────────────────────────────
@callback(
    Output("ars-currency-select", "options"),
    Output("ars-divisor-select",  "options"),
    Output("ars-divisors-table",  "children"),
    Output("ars-stats",           "children"),
    Input("ars-divisor-select",   "id"),
)
def load_page(_):
    from app.database import get_session
    from app.models import Asset
    from app.models.currency import Currency

    s = get_session()
    cur_opts = [
        {"label": f"{c.iso_code} — {c.name}" if c.iso_code else c.name, "value": c.id}
        for c in s.query(Currency).order_by(Currency.name).all()
    ]
    asset_opts = [
        {"label": f"{a.ticker} — {a.name}", "value": a.id}
        for a in s.query(Asset).order_by(Asset.ticker).all()
    ]
    return cur_opts, asset_opts, _build_divisors_table(), _build_stats()


# ── Agregar divisor ───────────────────────────────────────────────────────────
@callback(
    Output("ars-divisors-table",  "children", allow_duplicate=True),
    Output("ars-stats",           "children", allow_duplicate=True),
    Output("ars-add-alert",       "children"),
    Output("ars-add-alert",       "is_open"),
    Output("ars-add-alert",       "color"),
    Output("ars-currency-select", "value"),
    Output("ars-divisor-select",  "value"),
    Input("ars-btn-add",          "n_clicks"),
    State("ars-currency-select",  "value"),
    State("ars-divisor-select",   "value"),
    prevent_initial_call=True,
)
@safe_callback(lambda exc: (no_update, no_update, f"Error: {exc}", True, "danger", no_update, no_update))
def add_divisor(_, currency_id, asset_id):
    if not currency_id:
        return no_update, no_update, "Seleccioná una moneda fuente.", True, "warning", no_update, no_update
    if not asset_id:
        return no_update, no_update, "Seleccioná un activo divisor.", True, "warning", no_update, no_update
    svc.add_divisor(currency_id, asset_id)
    return _build_divisors_table(), _build_stats(), "", False, "info", None, None


# ── Eliminar divisor: abrir modal de confirmación ────────────────────────────
@callback(
    Output("ars-remove-modal",        "is_open"),
    Output("ars-pending-remove-id",   "data"),
    Output("ars-remove-confirm-body", "children"),
    Input({"type": "ars-remove-div", "index": ALL}, "n_clicks"),
    prevent_initial_call=True,
)
@safe_callback(lambda exc: (False, no_update, f"Error: {exc}"))
def open_remove_modal(n_clicks_list):
    if not any(n for n in n_clicks_list if n):
        return no_update, no_update, no_update
    divisor_id = ctx.triggered_id["index"]

    from app.database import get_session
    from app.models.currency_conversion import CurrencyConversionDivisor
    s   = get_session()
    div = s.query(CurrencyConversionDivisor).filter(
        CurrencyConversionDivisor.id == divisor_id
    ).first()
    if not div:
        return no_update, no_update, no_update

    n   = svc.count_synthetics_for_divisor(div.divisor_asset_id)
    cur = div.currency.iso_code or div.currency.name
    msg = (
        f"Se eliminarán {n} activo{'s' if n != 1 else ''} sintético{'s' if n != 1 else ''} "
        f"de {cur} con divisor '{div.divisor_asset.ticker}'. ¿Confirmás?"
        if n else
        f"¿Eliminás el divisor '{div.divisor_asset.ticker}' para {cur}?"
    )
    return True, divisor_id, msg


# ── Eliminar divisor: cancelar / confirmar ────────────────────────────────────
@callback(
    Output("ars-remove-modal",       "is_open",   allow_duplicate=True),
    Output("ars-pending-remove-id",  "data",      allow_duplicate=True),
    Output("ars-divisors-table",     "children",  allow_duplicate=True),
    Output("ars-stats",              "children",  allow_duplicate=True),
    Output("ars-btn-confirm-remove", "disabled",  allow_duplicate=True),
    Output("ars-btn-confirm-remove", "children",  allow_duplicate=True),
    Input("ars-btn-cancel-remove",   "n_clicks"),
    Input("ars-btn-confirm-remove",  "n_clicks"),
    State("ars-pending-remove-id",   "data"),
    prevent_initial_call=True,
)
@safe_callback(lambda exc: (False, None, no_update, f"Error: {exc}", False, "Eliminar"))
def handle_remove_divisor(n_cancel, n_confirm, divisor_id):
    if ctx.triggered_id == "ars-btn-cancel-remove":
        return False, None, no_update, no_update, False, "Eliminar"

    if not divisor_id:
        return False, None, no_update, no_update, False, "Eliminar"

    from app.database import get_session
    from app.models.currency_conversion import CurrencyConversionDivisor
    s   = get_session()
    div = s.query(CurrencyConversionDivisor).filter(
        CurrencyConversionDivisor.id == divisor_id
    ).first()
    if div:
        svc.delete_synthetics_for_asset(div.divisor_asset_id)
    svc.remove_divisor(divisor_id)
    return False, None, _build_divisors_table(), _build_stats(), False, "Eliminar"


# ── Iniciar sincronización ────────────────────────────────────────────────────
@callback(
    Output("ars-interval",   "disabled"),
    Output("ars-progress",   "style"),
    Output("ars-btn-sync",   "disabled"),
    Output("ars-sync-alert", "is_open"),
    Input("ars-btn-sync",    "n_clicks"),
    prevent_initial_call=True,
)
def start_sync(_):
    _sync_state.update({"running": True, "current": 0, "total": 0,
                        "msg": "", "error": None, "color": "success"})

    def _run():
        def _progress(cur, tot):
            _sync_state["current"] = cur
            _sync_state["total"]   = tot
        try:
            result = svc.sync_all(progress_cb=_progress)
            n_err  = len(result["errors"])
            _sync_state["color"] = "warning" if n_err else "success"
            _sync_state["msg"]   = (
                f"Sincronización completa: {result['created']} creados, "
                f"{result['already_existed']} ya existían"
                + (f", {n_err} errores." if n_err else ".")
            )
        except Exception as exc:
            _sync_state["error"] = str(exc)
            _sync_state["color"] = "danger"
        finally:
            _sync_state["running"] = False

    threading.Thread(target=_run, daemon=True).start()
    return False, {"display": "block", "height": "16px", "fontSize": "0.72rem"}, True, False


# ── Polling de progreso ───────────────────────────────────────────────────────
@callback(
    Output("ars-progress",   "value"),
    Output("ars-progress",   "label"),
    Output("ars-progress",   "style",   allow_duplicate=True),
    Output("ars-interval",   "disabled", allow_duplicate=True),
    Output("ars-btn-sync",   "disabled", allow_duplicate=True),
    Output("ars-sync-alert", "children", allow_duplicate=True),
    Output("ars-sync-alert", "is_open",  allow_duplicate=True),
    Output("ars-sync-alert", "color",    allow_duplicate=True),
    Output("ars-stats",      "children", allow_duplicate=True),
    Input("ars-interval",    "n_intervals"),
    prevent_initial_call=True,
)
def poll_sync(_):
    _hidden = {"display": "none"}
    _shown  = {"display": "block", "height": "16px", "fontSize": "0.72rem"}

    if _sync_state["running"]:
        cur   = _sync_state["current"]
        total = _sync_state["total"] or 1
        pct   = int(cur / total * 100)
        label = f"{cur} / {_sync_state['total']}" if _sync_state["total"] else "Iniciando..."
        return pct, label, _shown, False, True, no_update, False, "info", no_update

    if _sync_state["error"]:
        return 0, "", _hidden, True, False, f"Error: {_sync_state['error']}", True, "danger", no_update

    return (100, "Completo", _hidden, True, False,
            _sync_state["msg"], bool(_sync_state["msg"]),
            _sync_state["color"], _build_stats())
