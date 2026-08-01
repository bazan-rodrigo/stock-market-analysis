"""Callbacks de la pantalla Conexión IA.

El token en claro existe UNA sola vez: cuando se genera. No se guarda, así que
no hay forma de volver a mostrarlo — si el usuario lo pierde, genera otro (lo
cual invalida el anterior, que es también cómo se rota si se filtró).
"""
from dash import Input, Output, State, callback, html, no_update
import dash_bootstrap_components as dbc
from flask_login import current_user

from app.ai import tokens
from app.components.ui_constants import COLOR_POSITIVE, TEXT_MUTED


def _uid() -> int | None:
    if not current_user.is_authenticated:
        return None
    return int(current_user.get_id())


def _estado_texto(uid: int | None):
    if uid is None:
        return html.Small("Sesión no válida.", className="text-muted")
    est = tokens.estado(uid)
    if not est["tiene"]:
        return html.Small(
            "Todavía no generaste un token. Sin token, ningún cliente de IA "
            "puede conectarse a tu cuenta.",
            style={"color": TEXT_MUTED})
    creado = est["creado"].strftime("%Y-%m-%d %H:%M") if est["creado"] else "—"
    return html.Small([
        html.Span("● ", style={"color": COLOR_POSITIVE}),
        f"Tenés un token activo, generado el {creado} (UTC). ",
        html.Span("Por seguridad no se puede volver a mostrar: si lo perdiste, "
                  "generá uno nuevo.", style={"color": TEXT_MUTED}),
    ])


@callback(
    Output("ia-estado", "children"),
    Input("ia-refresh", "data"),
)
def mostrar_estado(_):
    return _estado_texto(_uid())


@callback(
    Output("ia-token-nuevo", "children"),
    Output("ia-refresh",     "data", allow_duplicate=True),
    Output("ia-alert",       "children", allow_duplicate=True),
    Output("ia-alert",       "is_open",  allow_duplicate=True),
    Output("ia-alert",       "color",    allow_duplicate=True),
    Input("ia-btn-generar",  "n_clicks"),
    State("ia-refresh",      "data"),
    prevent_initial_call=True,
)
def generar(_, refresh):
    uid = _uid()
    if uid is None:
        return no_update, no_update, "Sesión no válida.", True, "danger"
    try:
        token = tokens.generar(uid)
    except Exception as exc:                       # noqa: BLE001
        return no_update, no_update, str(exc), True, "danger"

    caja = dbc.Card(dbc.CardBody([
        html.Small("Copialo ahora — no se vuelve a mostrar:",
                   className="d-block mb-2 fw-semibold"),
        # Seleccionable y monoespaciado: se copia a mano, no hay botón de
        # portapapeles porque exigiría JS propio para un solo uso.
        html.Code(token, style={"fontSize": "0.85rem", "userSelect": "all",
                                "wordBreak": "break-all"}),
    ]), color="dark", outline=True)
    return (caja, (refresh or 0) + 1,
            "Token generado. El anterior, si había, quedó invalidado.",
            True, "success")


@callback(
    Output("ia-token-nuevo", "children", allow_duplicate=True),
    Output("ia-refresh",     "data", allow_duplicate=True),
    Output("ia-alert",       "children", allow_duplicate=True),
    Output("ia-alert",       "is_open",  allow_duplicate=True),
    Output("ia-alert",       "color",    allow_duplicate=True),
    Input("ia-btn-revocar",  "n_clicks"),
    State("ia-refresh",      "data"),
    prevent_initial_call=True,
)
def revocar(_, refresh):
    uid = _uid()
    if uid is None:
        return no_update, no_update, "Sesión no válida.", True, "danger"
    try:
        tenia = tokens.revocar(uid)
    except Exception as exc:                       # noqa: BLE001
        return no_update, no_update, str(exc), True, "danger"

    msg = ("Token revocado: los clientes que lo usaban dejan de tener acceso."
           if tenia else "No tenías ningún token activo.")
    return None, (refresh or 0) + 1, msg, True, "warning" if tenia else "info"
