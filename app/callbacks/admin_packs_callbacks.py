"""Callbacks de /admin/packs.

Dos pasos separados a propósito: subir un archivo **solo lo revisa** (ensayo
contra la base, sin escribir), y recién el botón Importar escribe. El estado
del archivo vive en un dcc.Store para que el segundo paso trabaje sobre
exactamente lo mismo que se revisó.
"""
import base64

from dash import Input, Output, State, callback, dcc, html, no_update

from app.components.ui_constants import (
    COLOR_NEGATIVE, COLOR_WARNING, TEXT_MUTED,
)
from app.services.visibility import current_viewer


def _lista(titulo: str, items: list[str], color: str):
    if not items:
        return None
    return html.Div([
        html.Div(f"{titulo} ({len(items)})",
                 style={"color": color, "fontWeight": "bold",
                        "fontSize": "0.82rem"}),
        html.Ul([html.Li(t, style={"fontSize": "0.78rem", "color": TEXT_MUTED})
                 for t in items],
                className="mb-2", style={"paddingLeft": "1.2rem"}),
    ])


def _diagnostico(errores: list[str], avisos: list[str]):
    bloques = [_lista("Errores — impiden importar", errores, COLOR_NEGATIVE),
               _lista("Avisos — no impiden importar", avisos, COLOR_WARNING)]
    return [b for b in bloques if b is not None]


# ── Catálogo ──────────────────────────────────────────────────────────────────

@callback(
    Output("pk-download", "data"),
    Input("pk-btn-catalog", "n_clicks"),
    prevent_initial_call=True,
)
def descargar_catalogo(_):
    from datetime import date as _date

    from app.services import pack_service

    _, is_admin = current_viewer()
    if not is_admin:
        return no_update
    return dcc.send_bytes(pack_service.catalog_bytes(),
                          f"catalogo_{_date.today().isoformat()}.json")


# ── Paso 1: subir y revisar (no escribe nada) ─────────────────────────────────

@callback(
    Output("pk-file-store",   "data"),
    Output("pk-table",        "rowData"),
    Output("pk-diagnostics",  "children"),
    Output("pk-filename",     "children"),
    Output("pk-alert",        "children"),
    Output("pk-alert",        "is_open"),
    Output("pk-alert",        "color"),
    Output("pk-btn-import",   "disabled"),
    Input("pk-upload",        "contents"),
    State("pk-upload",        "filename"),
    prevent_initial_call=True,
)
def revisar(contents, filename):
    from app.services import pack_service

    if contents is None:
        return (no_update,) * 8

    user_id, is_admin = current_viewer()
    if not is_admin:
        return (None, [], None, "",
                "Solo un administrador puede importar packs.", True, "danger", True)

    try:
        _, encoded = contents.split(",", 1)
        crudo = base64.b64decode(encoded)
        if not pack_service.looks_like_json(crudo, filename):
            raise pack_service.PackError(
                "esto no es un pack .json. Las planillas de Excel se importan "
                "desde las pantallas de Señales y de Estrategias.")
        pack = pack_service.parse_pack(crudo)
        informe = pack_service.preview_pack(pack, acting_user_id=user_id)
    except pack_service.PackError as exc:
        return (None, [], None, filename or "", str(exc), True, "danger", True)
    except Exception as exc:                       # noqa: BLE001
        return (None, [], None, filename or "",
                f"No se pudo leer el pack: {exc}", True, "danger", True)

    errores, avisos = informe["errors"], informe["warnings"]
    resumen = informe["summary"]
    nombre = pack.get("pack") or (filename or "pack")

    if errores:
        msg = (f"{len(errores)} error(es): el import se rechazaría entero "
               f"(es todo-o-nada). Corregí el pack y volvé a subirlo.")
        color = "danger"
    else:
        msg = (f"«{nombre}» listo para importar: crea {resumen['crea']} y "
               f"actualiza {resumen['actualiza']} definición(es)."
               + (f" {len(avisos)} aviso(s) para revisar." if avisos else ""))
        color = "warning" if avisos else "success"

    return (encoded, informe["rows"], _diagnostico(errores, avisos),
            filename or "", msg, True, color, bool(errores))


# ── Paso 2: importar ──────────────────────────────────────────────────────────

@callback(
    Output("pk-table",      "rowData",  allow_duplicate=True),
    Output("pk-alert",      "children", allow_duplicate=True),
    Output("pk-alert",      "is_open",  allow_duplicate=True),
    Output("pk-alert",      "color",    allow_duplicate=True),
    Output("pk-btn-import", "disabled", allow_duplicate=True),
    Input("pk-btn-import",  "n_clicks"),
    State("pk-file-store",  "data"),
    State("pk-table",       "rowData"),
    prevent_initial_call=True,
)
def importar(_, encoded, filas):
    from app.services import pack_service

    user_id, is_admin = current_viewer()
    if not is_admin:
        return no_update, "Solo un administrador puede importar packs.", True, "danger", True
    if not encoded:
        return (no_update,) * 5

    try:
        salida = pack_service.import_pack(base64.b64decode(encoded),
                                          owner_id=user_id)
    except Exception as exc:                       # noqa: BLE001
        return no_update, f"No se pudo importar: {exc}", True, "danger", False

    # El resultado se cruza con las filas ya mostradas (mismo orden que el
    # informe): así la tabla no cambia de forma entre el antes y el después.
    por_clave = {("Señal", r["key"]): r for r in salida["signals"]}
    por_clave.update({("Estrategia", r["name"]): r for r in salida["strategies"]})

    _ESTADO = {"ok": "imported", "error": "error"}
    filas_nuevas = []
    errores = 0
    for fila in (filas or []):
        r = por_clave.get((fila["tipo"], fila["nombre"]))
        nueva = dict(fila)
        if r is None:
            nueva["status"] = "sin ejecutar"
            nueva["estado"] = "skipped"
        else:
            nueva["status"] = r["detail"]
            nueva["estado"] = _ESTADO.get(r["status"], "skipped")
            errores += r["status"] == "error"
        filas_nuevas.append(nueva)

    if errores:
        msg = (f"{errores} error(es): no se escribió nada de esa parte del "
               f"pack (cada paso es todo-o-nada).")
        if salida["aborted"]:
            msg += (" Las estrategias no se intentaron: sin sus señales, "
                    "cada componente daría 'señal no encontrada'.")
        color = "danger"
    else:
        msg = (f"Importado: {len(salida['signals'])} señal(es) y "
               f"{len(salida['strategies'])} estrategia(s). Falta calcular la "
               f"historia desde el Centro de Datos.")
        color = "success"

    return filas_nuevas, msg, True, color, True


# ── Limpiar ───────────────────────────────────────────────────────────────────

@callback(
    Output("pk-file-store",  "data",     allow_duplicate=True),
    Output("pk-table",       "rowData",  allow_duplicate=True),
    Output("pk-diagnostics", "children", allow_duplicate=True),
    Output("pk-filename",    "children", allow_duplicate=True),
    Output("pk-alert",       "is_open",  allow_duplicate=True),
    Output("pk-btn-import",  "disabled", allow_duplicate=True),
    Input("pk-btn-clear",    "n_clicks"),
    prevent_initial_call=True,
)
def limpiar(_):
    return None, [], None, "", False, True
