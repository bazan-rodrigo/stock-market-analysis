from dash import Input, Output, State, callback, no_update

from app.database import get_session
from app.models import RegimeConfig


def _get_config():
    s = get_session()
    return s.query(RegimeConfig).filter(RegimeConfig.id == 1).first()


@callback(
    Output("regime-ema-d",    "value"),
    Output("regime-ema-w",    "value"),
    Output("regime-ema-m",    "value"),
    Output("regime-slope-lb", "value"),
    Output("regime-slope-thr","value"),
    Output("regime-confirm",  "value"),
    Input("regime-ema-d", "id"),
)
def load_config(_):
    cfg = _get_config()
    if cfg is None:
        return 200, 50, 20, 20, 0.5, 3
    return (
        cfg.ema_period_d,
        cfg.ema_period_w,
        cfg.ema_period_m,
        cfg.slope_lookback,
        cfg.slope_threshold_pct,
        cfg.confirm_bars,
    )


@callback(
    Output("regime-alert", "children"),
    Output("regime-alert", "is_open"),
    Output("regime-alert", "color"),
    Input("regime-btn-save", "n_clicks"),
    State("regime-ema-d",    "value"),
    State("regime-ema-w",    "value"),
    State("regime-ema-m",    "value"),
    State("regime-slope-lb", "value"),
    State("regime-slope-thr","value"),
    State("regime-confirm",  "value"),
    prevent_initial_call=True,
)
def save_config(_, ema_d, ema_w, ema_m, slope_lb, slope_thr, confirm):
    if any(v is None for v in [ema_d, ema_w, ema_m, slope_lb, slope_thr, confirm]):
        return "Completá todos los campos.", True, "warning"

    s = get_session()
    cfg = s.query(RegimeConfig).filter(RegimeConfig.id == 1).first()
    if cfg is None:
        cfg = RegimeConfig(id=1)
        s.add(cfg)

    cfg.ema_period_d        = int(ema_d)
    cfg.ema_period_w        = int(ema_w)
    cfg.ema_period_m        = int(ema_m)
    cfg.slope_lookback      = int(slope_lb)
    cfg.slope_threshold_pct = float(slope_thr)
    cfg.confirm_bars        = int(confirm)
    s.commit()

    return (
        "Configuración guardada. Recalculá los snapshots para aplicar los nuevos parámetros.",
        True,
        "success",
    )
