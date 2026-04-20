from dash import Input, Output, callback, html, no_update
import dash_bootstrap_components as dbc

import app.services.scheduler_service as svc
from app.config import Config


# ── Refresco de estado ────────────────────────────────────────────────────────

@callback(
    Output("scheduler-status-badge",  "children"),
    Output("scheduler-next-run",      "children"),
    Output("scheduler-current-time",  "children"),
    Input("scheduler-interval",       "n_intervals"),
    Input("scheduler-btn-start",      "n_clicks"),
    Input("scheduler-btn-stop",       "n_clicks"),
    Input("scheduler-btn-apply",      "n_clicks"),
    Input("scheduler-btn-run-now",    "n_clicks"),
)
def refresh_status(*_):
    st = svc.get_status()
    if st["running"]:
        badge = dbc.Badge("Activo", color="success", pill=True)
        time_str = f"{st['hour']}:{st['minute'].zfill(2) if st['minute'] else '00'} UTC"
    else:
        badge = dbc.Badge("Detenido", color="danger", pill=True)
        time_str = "—"
    return badge, st["next_run"] or "—", time_str


# ── Iniciar ───────────────────────────────────────────────────────────────────

@callback(
    Output("scheduler-alert", "children",  allow_duplicate=True),
    Output("scheduler-alert", "is_open",   allow_duplicate=True),
    Output("scheduler-alert", "color",     allow_duplicate=True),
    Input("scheduler-btn-start", "n_clicks"),
    prevent_initial_call=True,
)
def start(_):
    if not _:
        return no_update, no_update, no_update
    try:
        svc.start_scheduler()
        return "Scheduler iniciado.", True, "success"
    except Exception as exc:
        return str(exc), True, "danger"


# ── Detener ───────────────────────────────────────────────────────────────────

@callback(
    Output("scheduler-alert", "children",  allow_duplicate=True),
    Output("scheduler-alert", "is_open",   allow_duplicate=True),
    Output("scheduler-alert", "color",     allow_duplicate=True),
    Input("scheduler-btn-stop", "n_clicks"),
    prevent_initial_call=True,
)
def stop(_):
    if not _:
        return no_update, no_update, no_update
    try:
        svc.shutdown_scheduler()
        return "Scheduler detenido.", True, "warning"
    except Exception as exc:
        return str(exc), True, "danger"


# ── Ejecutar ahora ────────────────────────────────────────────────────────────

@callback(
    Output("scheduler-alert", "children",  allow_duplicate=True),
    Output("scheduler-alert", "is_open",   allow_duplicate=True),
    Output("scheduler-alert", "color",     allow_duplicate=True),
    Input("scheduler-btn-run-now", "n_clicks"),
    prevent_initial_call=True,
)
def run_now(_):
    if not _:
        return no_update, no_update, no_update
    try:
        svc.run_now()
        return "Ejecución inmediata programada.", True, "info"
    except Exception as exc:
        return str(exc), True, "danger"


# ── Cambiar horario ───────────────────────────────────────────────────────────

@callback(
    Output("scheduler-alert", "children",  allow_duplicate=True),
    Output("scheduler-alert", "is_open",   allow_duplicate=True),
    Output("scheduler-alert", "color",     allow_duplicate=True),
    Input("scheduler-btn-apply",    "n_clicks"),
    Input("scheduler-input-hour",   "value"),
    Input("scheduler-input-minute", "value"),
    prevent_initial_call=True,
)
def apply_schedule(n_clicks, hour, minute):
    if not n_clicks:
        return no_update, no_update, no_update
    if hour is None or minute is None:
        return "Ingresá hora y minuto.", True, "warning"
    try:
        svc.update_schedule(int(hour), int(minute))
        return f"Horario actualizado a {int(hour):02d}:{int(minute):02d} UTC.", True, "success"
    except Exception as exc:
        return str(exc), True, "danger"
