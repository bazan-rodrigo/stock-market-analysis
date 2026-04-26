from dash import Input, Output, State, callback

from app.database import get_session
from app.models import VolatilityConfig


def _get_config():
    s = get_session()
    return s.query(VolatilityConfig).filter(VolatilityConfig.id == 1).first()


@callback(
    Output("vol-atr-period", "value"),
    Output("vol-confirm",    "value"),
    Output("vol-pct-low",    "value"),
    Output("vol-pct-high",   "value"),
    Output("vol-pct-extreme","value"),
    Output("vol-dur-short",  "value"),
    Output("vol-dur-long",   "value"),
    Input("vol-atr-period", "id"),
)
def load_vol_config(_):
    cfg = _get_config()
    if cfg is None:
        return 14, 3, 25.0, 75.0, 90.0, 33.0, 67.0
    return (
        cfg.atr_period,
        cfg.confirm_bars,
        cfg.pct_low,
        cfg.pct_high,
        cfg.pct_extreme,
        cfg.dur_short_pct,
        cfg.dur_long_pct,
    )


@callback(
    Output("vol-alert", "children"),
    Output("vol-alert", "is_open"),
    Output("vol-alert", "color"),
    Input("vol-btn-save", "n_clicks"),
    State("vol-atr-period", "value"),
    State("vol-confirm",    "value"),
    State("vol-pct-low",    "value"),
    State("vol-pct-high",   "value"),
    State("vol-pct-extreme","value"),
    State("vol-dur-short",  "value"),
    State("vol-dur-long",   "value"),
    prevent_initial_call=True,
)
def save_vol_config(_, atr_period, confirm, pct_low, pct_high, pct_extreme, dur_short, dur_long):
    if any(v is None for v in [atr_period, confirm, pct_low, pct_high, pct_extreme, dur_short, dur_long]):
        return "Completá todos los campos.", True, "warning"
    if not (pct_low < pct_high < pct_extreme):
        return "P_bajo < P_alto < P_extremo debe cumplirse.", True, "warning"
    if not (dur_short < dur_long):
        return "Percentil duración corta debe ser menor que larga.", True, "warning"

    s = get_session()
    cfg = s.query(VolatilityConfig).filter(VolatilityConfig.id == 1).first()
    if cfg is None:
        cfg = VolatilityConfig(id=1)
        s.add(cfg)

    cfg.atr_period    = int(atr_period)
    cfg.confirm_bars  = int(confirm)
    cfg.pct_low       = float(pct_low)
    cfg.pct_high      = float(pct_high)
    cfg.pct_extreme   = float(pct_extreme)
    cfg.dur_short_pct = float(dur_short)
    cfg.dur_long_pct  = float(dur_long)
    s.commit()

    return (
        "Configuración guardada. Recalculá los snapshots para aplicar los nuevos parámetros.",
        True,
        "success",
    )
