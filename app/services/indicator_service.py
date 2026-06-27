"""
Servicio de indicadores.
Agrega indicator_values por grupo (sector/market) para group_indicator_snapshot.
La escritura individual por activo ocurre en screener_service.compute_and_save_snapshot().
"""
import logging
from collections import defaultdict
from datetime import date as date_type

from app.database import get_session
from app.models import Asset, GroupIndicatorSnapshot
from app.models.indicator_definition import IndicatorDefinition
from app.models.indicator_value import IndicatorValue

logger = logging.getLogger(__name__)

_REGIME_SCORE: dict[str, float] = {
    "bullish_strong":         100.0,
    "bullish_nascent_strong":  75.0,
    "bullish":                 60.0,
    "bullish_nascent":         40.0,
    "lateral_nascent":          5.0,
    "lateral":                  0.0,
    "bearish_nascent":        -40.0,
    "bearish_nascent_strong": -75.0,
    "bearish":                -60.0,
    "bearish_strong":        -100.0,
}

_GROUP_DIMS = [
    ("sector_id", "sector"),
    ("market_id", "market"),
]


def _avg(lst: list) -> float | None:
    if not lst:
        return None
    return round(sum(lst) / len(lst), 2)


def compute_group_snapshots(snap_date: date_type) -> None:
    """
    Agrega indicator_values de tendencia por sector y market para snap_date.
    Calcula regime_score_d/w/m como promedio de los scores de cada activo.
    """
    s = get_session()

    # Obtener IDs de los indicadores de tendencia
    trend_codes = ("trend_daily", "trend_weekly", "trend_monthly")
    defs = {
        d.code: d.id
        for d in s.query(IndicatorDefinition).filter(
            IndicatorDefinition.code.in_(trend_codes)
        ).all()
    }
    if not defs:
        return

    trend_ids = list(defs.values())

    # Leer indicator_values de tendencia para snap_date
    iv_rows = (
        s.query(Asset.sector_id, Asset.market_id, IndicatorDefinition.code, IndicatorValue.value_str)
        .join(IndicatorValue, IndicatorValue.asset_id == Asset.id)
        .join(IndicatorDefinition, IndicatorValue.indicator_id == IndicatorDefinition.id)
        .filter(
            IndicatorValue.date == snap_date,
            IndicatorValue.indicator_id.in_(trend_ids),
        )
        .all()
    )

    if not iv_rows:
        return

    groups: dict = defaultdict(lambda: {"d": [], "w": [], "m": []})

    _code_tf = {
        "trend_daily":   "d",
        "trend_weekly":  "w",
        "trend_monthly": "m",
    }

    for sector_id, market_id, code, value_str in iv_rows:
        tf = _code_tf.get(code)
        if tf is None:
            continue
        score = _REGIME_SCORE.get(value_str or "")
        if score is None:
            continue
        for group_type, group_id in [("sector", sector_id), ("market", market_id)]:
            if group_id is None:
                continue
            groups[(group_type, group_id)][tf].append(score)

    for (group_type, group_id), scores in groups.items():
        gsnap = (
            s.query(GroupIndicatorSnapshot)
            .filter(
                GroupIndicatorSnapshot.group_type == group_type,
                GroupIndicatorSnapshot.group_id == group_id,
                GroupIndicatorSnapshot.date == snap_date,
            )
            .first()
        )

        if gsnap is None:
            gsnap = GroupIndicatorSnapshot(
                group_type=group_type,
                group_id=group_id,
                date=snap_date,
            )
            s.add(gsnap)

        gsnap.regime_score_d = _avg(scores["d"])
        gsnap.regime_score_w = _avg(scores["w"])
        gsnap.regime_score_m = _avg(scores["m"])
        counts = [len(scores["d"]), len(scores["w"]), len(scores["m"])]
        gsnap.n_assets = max(counts) if any(counts) else 0

    s.commit()


def run_daily(snap_date: date_type | None = None) -> int:
    """
    Pipeline diario de indicadores de grupo.
    Agrega group_indicator_snapshot para snap_date a partir de indicator_values
    (ya escritos por screener_service.compute_and_save_snapshot por cada activo).
    """
    from datetime import date as dt_date

    if snap_date is None:
        snap_date = dt_date.today()

    try:
        compute_group_snapshots(snap_date)
    except Exception as exc:
        logger.error(
            "indicator_service: error en compute_group_snapshots para %s: %s", snap_date, exc
        )

    logger.info("indicator_service: run_daily completado para %s", snap_date)
    return 0
