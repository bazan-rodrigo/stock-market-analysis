import logging

from dash import Input, Output, State, callback

from app.database import get_session
from app.models import SRConfig
from app.utils import safe_callback

logger = logging.getLogger(__name__)

_DEFAULTS = (252, 5, 0.5, 2)


def _get_config():
    s = get_session()
    return s.query(SRConfig).filter(SRConfig.id == 1).first()


@callback(
    Output("sr-lookback",     "value"),
    Output("sr-pivot-window", "value"),
    Output("sr-cluster-pct",  "value"),
    Output("sr-min-touches",  "value"),
    Input("sr-lookback", "id"),
)
def load_sr_config(_):
    try:
        cfg = _get_config()
        if cfg is None:
            return _DEFAULTS
        return (
            cfg.lookback_days,
            cfg.pivot_window,
            cfg.cluster_pct,
            cfg.min_touches,
        )
    except Exception:
        logger.exception("Error cargando SRConfig")
        return _DEFAULTS


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
@safe_callback(lambda exc: (f"Error inesperado: {exc}", True, "danger"))
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
