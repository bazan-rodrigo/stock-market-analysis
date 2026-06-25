from dash import Input, Output, callback, no_update
from flask_login import current_user


@callback(
    Output("appsettings-alert",         "children"),
    Output("appsettings-alert",         "is_open"),
    Output("appsettings-alert",         "color"),
    Output("appsettings-public-access", "label"),
    Input("appsettings-public-access",  "value"),
    prevent_initial_call=True,
)
def toggle_public_access(enabled):
    if not current_user.is_authenticated or not current_user.is_admin:
        return no_update, no_update, no_update, no_update

    from app.services.app_config_service import set_public_access
    try:
        set_public_access(bool(enabled))
        msg   = "Acceso sin login habilitado." if enabled else "Acceso sin login deshabilitado."
        color = "success"
        label = "Habilitado" if enabled else "Deshabilitado"
    except Exception as exc:
        msg   = f"Error al guardar: {exc}"
        color = "danger"
        label = no_update

    return msg, True, color, label
