import threading

from dash import Input, Output, State, callback, html, no_update, ALL, ctx
import dash_bootstrap_components as dbc

import app.services.currency_conversion_service as svc
from app.utils import safe_callback
from app.components.ui_constants import TH as _th, TD as _td

_sync_state = {
    "running": False, "current": 0, "total": 0,
    "msg": "", "error": None, "color": "success",
}

# Guarda de re-entrada de la baja de divisor: si el usuario dispara otra baja
# mientras un borrado sigue en curso, la segunda invocación se ignora — sin
# esto corrían dos borrados concurrentes de los mismos activos
# (ObjectDeletedError). El thread del borrado libera el lock al terminar.
_remove_lock = threading.Lock()

# Estado del borrado en curso (thread daemon + polling con dcc.Interval, mismo
# patrón que _sync_state): el borrado puede tardar minutos (lotes sobre todas
# las tablas ind_*/signal_value/prices...), no puede vivir dentro del request.
_remove_state = {
    "running": False, "current": 0, "total": 0, "label": "",
    "base": "", "msg": "", "error": None,
}


def _build_divisors_table() -> html.Div:
    divisors = svc.get_divisors()
    if not divisors:
        return html.P("Sin divisores configurados.", className="text-muted mt-2", style={"fontSize": "0.82rem"})

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
        return html.P("Sin divisores configurados.", className="text-muted mt-2", style={"fontSize": "0.82rem"})

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

    from app.models.instrument_type import InstrumentType

    s = get_session()
    cur_opts = [
        {"label": f"{c.iso_code} — {c.name}" if c.iso_code else c.name, "value": c.id}
        for c in s.query(Currency).order_by(Currency.name).all()
    ]
    asset_opts = [
        {"label": f"{a.ticker} — {a.name}", "value": a.id}
        for a in s.query(Asset)
        .join(Asset.instrument_type)
        .filter(InstrumentType.name.in_(["CURRENCY", "cryptoCURRENCY"]))
        .order_by(Asset.ticker)
        .all()
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
    # Con un borrado en curso no se abre otro modal (el alerta de progreso ya
    # está visible bajo la tabla).
    if _remove_state["running"]:
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
# Al confirmar, el modal se cierra en el acto y el borrado corre en un thread
# daemon (puede tardar minutos; dentro del request el cliente cortaba y el
# modal quedaba abierto para siempre). El avance se ve en ars-remove-alert
# vía polling (ars-remove-interval), mismo patrón que la sincronización.
@callback(
    Output("ars-remove-modal",      "is_open",  allow_duplicate=True),
    Output("ars-pending-remove-id", "data",     allow_duplicate=True),
    Output("ars-remove-interval",   "disabled"),
    Output("ars-remove-alert",      "children"),
    Output("ars-remove-alert",      "is_open"),
    Output("ars-remove-alert",      "color"),
    Input("ars-btn-cancel-remove",  "n_clicks"),
    Input("ars-btn-confirm-remove", "n_clicks"),
    State("ars-pending-remove-id",  "data"),
    prevent_initial_call=True,
)
@safe_callback(lambda exc: (False, None, True, f"Error: {exc}", True, "danger"))
def handle_remove_divisor(n_cancel, n_confirm, divisor_id):
    if ctx.triggered_id == "ars-btn-cancel-remove" or not divisor_id:
        return False, None, no_update, no_update, no_update, no_update

    # Ignorar el re-click si ya hay un borrado en curso (evita doble borrado).
    if not _remove_lock.acquire(blocking=False):
        return (no_update,) * 6

    # Datos del divisor como valores planos ACÁ (sesión del request): los
    # objetos ORM no se comparten con el thread (misma conexión DBAPI →
    # "Commands out of sync", ver docs/notes). Si algo falla antes de lanzar
    # el thread, liberar el lock (si no, quedaría tomado para siempre).
    try:
        from app.database import get_session
        from app.models.currency_conversion import CurrencyConversionDivisor
        s   = get_session()
        div = s.query(CurrencyConversionDivisor).filter(
            CurrencyConversionDivisor.id == divisor_id
        ).first()
        if not div:
            svc.remove_divisor(divisor_id)  # ya borrada: idempotente
        else:
            divisor_asset_id = div.divisor_asset_id
            ticker           = div.divisor_asset.ticker
            n                = svc.count_synthetics_for_divisor(divisor_asset_id)
    except BaseException:
        _remove_lock.release()
        raise
    if not div:
        _remove_lock.release()
        return False, None, no_update, no_update, no_update, no_update

    base = (f"Eliminando {n} sintético{'s' if n != 1 else ''} "
            f"con divisor '{ticker}'…")
    _remove_state.update({"running": True, "current": 0, "total": 0,
                          "label": "", "base": base, "msg": "", "error": None})

    def _run():
        from app.database import Session

        def _progress(done, total, tbl):
            _remove_state["current"] = done
            _remove_state["total"]   = total
            _remove_state["label"]   = tbl

        try:
            svc.delete_synthetics_for_asset(divisor_asset_id, role="denominator",
                                            progress_cb=_progress)
            svc.remove_divisor(divisor_id)
            _remove_state["msg"] = (
                f"Divisor '{ticker}' eliminado"
                + (f" junto con sus {n} sintéticos." if n else "."))
        except Exception as exc:
            _remove_state["error"] = str(exc)
        finally:
            _remove_state["running"] = False
            _remove_lock.release()
            Session.remove()  # libera la sesión/conexión del thread

    threading.Thread(target=_run, daemon=True).start()
    return False, None, False, base, True, "warning"


# ── Polling del borrado ───────────────────────────────────────────────────────
@callback(
    Output("ars-remove-alert",    "children", allow_duplicate=True),
    Output("ars-remove-alert",    "is_open",  allow_duplicate=True),
    Output("ars-remove-alert",    "color",    allow_duplicate=True),
    Output("ars-remove-interval", "disabled", allow_duplicate=True),
    Output("ars-divisors-table",  "children", allow_duplicate=True),
    Output("ars-stats",           "children", allow_duplicate=True),
    Input("ars-remove-interval",  "n_intervals"),
    prevent_initial_call=True,
)
def poll_remove(_):
    if _remove_state["running"]:
        if _remove_state["total"]:
            cur   = min(_remove_state["current"] + 1, _remove_state["total"])
            label = _remove_state["label"] or "finalizando"
            detail = f" (tabla {cur}/{_remove_state['total']}: {label})"
        else:
            detail = ""
        return (_remove_state["base"] + detail, True, "warning",
                False, no_update, no_update)

    if _remove_state["error"]:
        return (f"Error al eliminar: {_remove_state['error']}", True, "danger",
                True, _build_divisors_table(), _build_stats())

    return (_remove_state["msg"], bool(_remove_state["msg"]), "success",
            True, _build_divisors_table(), _build_stats())


# ── Iniciar sincronización ────────────────────────────────────────────────────
@callback(
    Output("ars-interval",   "disabled"),
    Output("ars-progress",   "style"),
    Output("ars-btn-sync",   "disabled"),
    Output("ars-sync-alert", "is_open"),
    Output("ars-sync-alert", "children"),
    Output("ars-sync-alert", "color"),
    Input("ars-btn-sync",    "n_clicks"),
    prevent_initial_call=True,
)
def start_sync(_):
    # ANTES de arrancar (el sync puede tardar): avisar qué señales/estrategias
    # van a quedar desactualizadas en la historia. Los sintéticos nuevos entran
    # a los agregados de sus grupos; sus señales/estrategias propias entran
    # solas en la próxima corrida, lo transversal (grupo) no. Se deriva de las
    # bases pendientes (heredan los grupos de sus sintéticos).
    from app.services.signal_service import (
        signals_and_strategies_affected_by_new_assets)
    afectados = signals_and_strategies_affected_by_new_assets(
        svc.pending_sync_base_asset_ids())
    _sync_state.update({"running": True, "current": 0, "total": 0,
                        "msg": "", "error": None, "color": "success"})

    if afectados:
        pre_msg = ("Sincronizando… Al terminar corré «Recalcular completo» de "
                   "Señales y Estrategias — se desactualizarán en la historia: "
                   + ", ".join(afectados) + ".")
        pre_color = "warning"
    else:
        pre_msg, pre_color = "Sincronizando…", "info"

    def _run():
        def _progress(cur, tot):
            _sync_state["current"] = cur
            _sync_state["total"]   = tot
        try:
            result = svc.sync_all(progress_cb=_progress)
            n_err  = len(result["errors"])
            _sync_state["color"] = "warning" if (n_err or afectados) else "success"
            msg = (
                f"Sincronización completa: {result['created']} creados, "
                f"{result['already_existed']} ya existían"
                + (f", {n_err} errores." if n_err else ".")
            )
            if afectados:
                # Recordatorio corto: el detalle ya se listó al iniciar.
                msg += (" Recordá «Recalcular completo» de Señales y Estrategias "
                        "para incluir los sintéticos nuevos en la historia.")
            _sync_state["msg"] = msg
        except Exception as exc:
            _sync_state["error"] = str(exc)
            _sync_state["color"] = "danger"
        finally:
            _sync_state["running"] = False

    threading.Thread(target=_run, daemon=True).start()
    return (False, {"display": "block", "height": "16px", "fontSize": "0.72rem"},
            True, True, pre_msg, pre_color)


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
        # Mantener abierto el aviso pre-sync (children/color los fijó start_sync)
        return pct, label, _shown, False, True, no_update, True, no_update, no_update

    if _sync_state["error"]:
        return 0, "", _hidden, True, False, f"Error: {_sync_state['error']}", True, "danger", no_update

    return (100, "Completo", _hidden, True, False,
            _sync_state["msg"], bool(_sync_state["msg"]),
            _sync_state["color"], _build_stats())
