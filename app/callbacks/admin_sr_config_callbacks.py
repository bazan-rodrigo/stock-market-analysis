from dash import Input, Output, State, callback, no_update

from app.database import get_session
from app.models import SRConfig


def _get_config():
    s = get_session()
    cfg = s.query(SRConfig).filter(SRConfig.id == 1).first()
    return cfg


@callback(
    Output("sr-lookback",     "value"),
    Output("sr-pivot-window", "value"),
    Output("sr-cluster-pct",  "value"),
    Output("sr-min-touches",  "value"),
    Input("sr-lookback", "id"),
)
def load_sr_config(_):
    cfg = _get_config()
    if cfg is None:
        return 252, 5, 0.5, 2
    return (
        cfg.lookback_days,
        cfg.pivot_window,
        cfg.cluster_pct,
        cfg.min_touches,
    )


@callback(
    Output("sr-alert", "children"),
    Output("sr-alert", "is_open"),
    Output("sr-alert", "color"),
    Input("sr-btn-save", "n_clicks"),
    State("sr-lookback",     "value"),
    State("sr-pivot-window", "value"),
    State("sr-cluster-pct",  "value"),
    State("sr-min-touches",  "value"),
    prevent_initial_call=True,
)
def save_sr_config(_, lookback, window, cluster, touches):
    if any(v is None for v in [lookback, window, cluster, touches]):
        return "Completá todos los campos.", True, "warning"

    s = get_session()
    cfg = s.query(SRConfig).filter(SRConfig.id == 1).first()
    if cfg is None:
        cfg = SRConfig(id=1)
        s.add(cfg)

    cfg.lookback_days = int(lookback)
    cfg.pivot_window  = int(window)
    cfg.cluster_pct   = float(cluster)
    cfg.min_touches   = int(touches)
    s.commit()

    return (
        "Configuración guardada. Recalculá los snapshots para aplicar los nuevos parámetros.",
        True,
        "success",
    )
