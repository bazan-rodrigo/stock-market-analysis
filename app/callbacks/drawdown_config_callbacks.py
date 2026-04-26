import logging

from dash import Input, Output, State, callback

from app.database import get_session
from app.models import DrawdownConfig
from app.utils import safe_callback

logger = logging.getLogger(__name__)


@callback(
    Output("dd-min-depth", "value"),
    Input("dd-min-depth", "id"),
)
def load_config(_):
    try:
        s = get_session()
        cfg = s.query(DrawdownConfig).filter(DrawdownConfig.id == 1).first()
        return cfg.min_depth_pct if cfg else 20.0
    except Exception:
        logger.exception("Error cargando DrawdownConfig")
        return 20.0


@callback(
    Output("dd-alert", "children"),
    Output("dd-alert", "is_open"),
    Output("dd-alert", "color"),
    Input("dd-btn-save", "n_clicks"),
    State("dd-min-depth", "value"),
    prevent_initial_call=True,
)
@safe_callback(lambda exc: (f"Error inesperado: {exc}", True, "danger"))
def save_config(_, min_depth):
    if min_depth is None:
        return "Completá el campo.", True, "warning"

    s = get_session()
    cfg = s.query(DrawdownConfig).filter(DrawdownConfig.id == 1).first()
    if cfg is None:
        cfg = DrawdownConfig(id=1)
        s.add(cfg)
    cfg.min_depth_pct = float(min_depth)
    s.commit()
    return (
        "Configuración guardada. Recalculá los snapshots para aplicar el nuevo umbral.",
        True, "success",
    )
