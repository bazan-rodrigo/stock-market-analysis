import logging

from dash import Input, Output, State, callback

from app.services import pnf_service
from app.utils import safe_callback

logger = logging.getLogger(__name__)


@callback(
    Output("pnf-box-method", "value"),
    Output("pnf-box-pct",    "value"),
    Output("pnf-atr-period", "value"),
    Output("pnf-box-fixed",  "value"),
    Output("pnf-reversal",   "value"),
    Output("pnf-source",     "value"),
    Input("pnf-box-method",  "id"),
)
def load_config(_):
    try:
        cfg = pnf_service.get_pnf_config()
        return (cfg.box_method, cfg.box_pct, cfg.box_atr_period,
                cfg.box_fixed, cfg.reversal, cfg.source)
    except Exception:
        logger.exception("Error cargando PnfConfig")
        return "atr", 1.0, 14, 1.0, 3, "close"


@callback(
    Output("pnf-alert", "children"),
    Output("pnf-alert", "is_open"),
    Output("pnf-alert", "color"),
    Input("pnf-btn-save",    "n_clicks"),
    State("pnf-box-method",  "value"),
    State("pnf-box-pct",     "value"),
    State("pnf-atr-period",  "value"),
    State("pnf-box-fixed",   "value"),
    State("pnf-reversal",    "value"),
    State("pnf-source",      "value"),
    prevent_initial_call=True,
)
@safe_callback(lambda exc: (f"Error inesperado: {exc}", True, "danger"))
def save_config(_, box_method, box_pct, atr_period, box_fixed, reversal, source):
    if None in (box_method, box_pct, atr_period, box_fixed, reversal, source):
        return "Completá todos los campos.", True, "warning"

    from app.database import get_session
    from app.models import PnfConfig

    s = get_session()
    cfg = s.query(PnfConfig).filter(PnfConfig.id == 1).first()
    if cfg is None:
        cfg = PnfConfig(id=1)
        s.add(cfg)
    cfg.box_method     = str(box_method)
    cfg.box_pct        = float(box_pct)
    cfg.box_atr_period = int(atr_period)
    cfg.box_fixed      = float(box_fixed)
    cfg.reversal       = int(reversal)
    cfg.source         = str(source)
    s.commit()
    return (
        "Configuración guardada. Volvé a cargar el activo en el gráfico para aplicarla.",
        True, "success",
    )
