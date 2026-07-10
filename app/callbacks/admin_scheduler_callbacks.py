from dash import Input, Output, callback, no_update
import dash_bootstrap_components as dbc

import app.services.scheduler_service as svc


# ── Refresco de estado ────────────────────────────────────────────────────────

@callback(
    Output("scheduler-status-badge",  "children"),
    Output("scheduler-next-run",      "children"),
    Output("scheduler-current-time",  "children"),
    Output("scheduler-input-hour",    "value"),
    Output("scheduler-input-minute",  "value"),
    Input("scheduler-interval",       "n_intervals"),
    Input("scheduler-btn-start",      "n_clicks"),
    Input("scheduler-btn-stop",       "n_clicks"),
    Input("scheduler-btn-apply",      "n_clicks"),
    Input("scheduler-btn-run-now",    "n_clicks"),
)
def refresh_status(*_):
    st = svc.get_status()
    badge = dbc.Badge("Activo", color="success", pill=True) if st["running"] \
        else dbc.Badge("Detenido", color="danger", pill=True)
    time_str = f"{st['hour']:02d}:{st['minute']:02d} UTC" \
        if st["hour"] is not None else "—"
    return badge, st["next_run"] or "—", time_str, st["hour"], st["minute"]


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


# ── Verificación semanal de datos (job independiente) ────────────────────────

_DAY_LABELS = {"mon": "Lunes", "tue": "Martes", "wed": "Miércoles", "thu": "Jueves",
              "fri": "Viernes", "sat": "Sábado", "sun": "Domingo"}


@callback(
    Output("weekly-verify-status-badge",  "children"),
    Output("weekly-verify-next-run",      "children"),
    Output("weekly-verify-current-time",  "children"),
    Output("weekly-verify-input-day",     "value"),
    Output("weekly-verify-input-hour",    "value"),
    Output("weekly-verify-input-minute",  "value"),
    Input("scheduler-interval",           "n_intervals"),
    Input("weekly-verify-btn-enable",     "n_clicks"),
    Input("weekly-verify-btn-disable",    "n_clicks"),
    Input("weekly-verify-btn-apply",      "n_clicks"),
    Input("weekly-verify-btn-run-now",    "n_clicks"),
)
def refresh_weekly_verify_status(*_):
    st = svc.get_weekly_verification_status()
    if st["enabled"] and st["running"]:
        badge = dbc.Badge("Activo", color="success", pill=True)
    elif st["enabled"]:
        badge = dbc.Badge("Habilitado (scheduler detenido)", color="warning", pill=True)
    else:
        badge = dbc.Badge("Deshabilitado", color="secondary", pill=True)
    time_str = f"{_DAY_LABELS.get(st['day'], st['day'])} {st['hour']:02d}:{st['minute']:02d} UTC"
    return badge, st["next_run"] or "—", time_str, st["day"], st["hour"], st["minute"]


@callback(
    Output("weekly-verify-alert", "children",  allow_duplicate=True),
    Output("weekly-verify-alert", "is_open",   allow_duplicate=True),
    Output("weekly-verify-alert", "color",     allow_duplicate=True),
    Input("weekly-verify-btn-enable", "n_clicks"),
    prevent_initial_call=True,
)
def enable_weekly(_):
    if not _:
        return no_update, no_update, no_update
    try:
        svc.enable_weekly_verification()
        return "Verificación semanal habilitada.", True, "success"
    except Exception as exc:
        return str(exc), True, "danger"


@callback(
    Output("weekly-verify-alert", "children",  allow_duplicate=True),
    Output("weekly-verify-alert", "is_open",   allow_duplicate=True),
    Output("weekly-verify-alert", "color",     allow_duplicate=True),
    Input("weekly-verify-btn-disable", "n_clicks"),
    prevent_initial_call=True,
)
def disable_weekly(_):
    if not _:
        return no_update, no_update, no_update
    try:
        svc.disable_weekly_verification()
        return "Verificación semanal deshabilitada.", True, "warning"
    except Exception as exc:
        return str(exc), True, "danger"


@callback(
    Output("weekly-verify-alert", "children",  allow_duplicate=True),
    Output("weekly-verify-alert", "is_open",   allow_duplicate=True),
    Output("weekly-verify-alert", "color",     allow_duplicate=True),
    Input("weekly-verify-btn-run-now", "n_clicks"),
    prevent_initial_call=True,
)
def run_weekly_now(_):
    if not _:
        return no_update, no_update, no_update
    try:
        svc.run_weekly_verification_now()
        return "Ejecución inmediata programada.", True, "info"
    except Exception as exc:
        return str(exc), True, "danger"


@callback(
    Output("weekly-verify-alert", "children",  allow_duplicate=True),
    Output("weekly-verify-alert", "is_open",   allow_duplicate=True),
    Output("weekly-verify-alert", "color",     allow_duplicate=True),
    Input("weekly-verify-btn-apply",    "n_clicks"),
    Input("weekly-verify-input-day",    "value"),
    Input("weekly-verify-input-hour",   "value"),
    Input("weekly-verify-input-minute", "value"),
    prevent_initial_call=True,
)
def apply_weekly_schedule(n_clicks, day, hour, minute):
    if not n_clicks:
        return no_update, no_update, no_update
    if not day or hour is None or minute is None:
        return "Elegí día, hora y minuto.", True, "warning"
    try:
        svc.update_weekly_verification_schedule(day, int(hour), int(minute))
        return (f"Horario actualizado a {_DAY_LABELS.get(day, day)} "
               f"{int(hour):02d}:{int(minute):02d} UTC.", True, "success")
    except Exception as exc:
        return str(exc), True, "danger"
