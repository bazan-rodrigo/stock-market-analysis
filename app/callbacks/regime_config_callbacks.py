from dash import Input, Output, State, callback, no_update

from app.database import get_session
from app.models import RegimeConfig


def _get_config():
    s = get_session()
    return s.query(RegimeConfig).filter(RegimeConfig.id == 1).first()


@callback(
    Output("regime-fast", "value"),
    Output("regime-slow", "value"),
    Output("regime-band", "value"),
    Input("regime-fast", "id"),
)
def load_config(_):
    cfg = _get_config()
    if cfg is None:
        return 50, 200, 2.0
    return cfg.fast_period, cfg.slow_period, cfg.lateral_band_pct


@callback(
    Output("regime-alert", "children"),
    Output("regime-alert", "is_open"),
    Output("regime-alert", "color"),
    Input("regime-btn-save", "n_clicks"),
    State("regime-fast", "value"),
    State("regime-slow", "value"),
    State("regime-band", "value"),
    prevent_initial_call=True,
)
def save_config(_, fast, slow, band):
    if not fast or not slow or not band:
        return "Completá todos los campos.", True, "warning"
    if int(fast) >= int(slow):
        return "La SMA rápida debe ser menor que la SMA lenta.", True, "warning"

    s = get_session()
    cfg = s.query(RegimeConfig).filter(RegimeConfig.id == 1).first()
    if cfg is None:
        cfg = RegimeConfig(id=1)
        s.add(cfg)
    cfg.fast_period      = int(fast)
    cfg.slow_period      = int(slow)
    cfg.lateral_band_pct = float(band)
    s.commit()
    return "Configuración guardada. Recalculá los snapshots para aplicar los nuevos parámetros.", True, "success"
