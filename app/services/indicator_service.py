"""
Servicio de indicadores.
Agrega valores de tendencia por grupo para group_indicator_snapshot.
La escritura individual por activo ocurre en technical_service.compute_and_save_snapshot().
"""
import logging
import sqlalchemy as sa
from collections import defaultdict
from datetime import date as date_type

from app.database import get_session
from app.models import Asset, GroupIndicatorSnapshot
from app.models.indicator_store import get_ind_table

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
    ("sector_id",          "sector"),
    ("market_id",          "market"),
    ("industry_id",        "industry"),
    ("country_id",         "country"),
    ("instrument_type_id", "instrument_type"),
]

_TREND_CODES = ("trend_daily", "trend_weekly", "trend_monthly")
_TF_MAP      = {"trend_daily": "d", "trend_weekly": "w", "trend_monthly": "m"}


def _avg(lst: list) -> float | None:
    if not lst:
        return None
    return round(sum(lst) / len(lst), 2)


def get_default_snap_date() -> date_type:
    """Última fecha con precios cargados (fallback: hoy).

    Los indicadores ind_* se escriben con la última fecha de precio de cada
    activo; usar date.today() dejaría el pipeline sin datos los días sin
    rueda (fines de semana, feriados)."""
    from datetime import date as dt_date
    from sqlalchemy import func
    from app.models.price import Price

    s = get_session()
    last = s.query(func.max(Price.date)).scalar()
    return last or dt_date.today()


def compute_group_snapshots(snap_date: date_type) -> None:
    """
    Agrega valores de tendencia por grupos para snap_date.
    Lee directamente desde las tablas ind_trend_*.
    """
    s = get_session()

    # Leer las tres tablas de tendencia → {asset_id: {tf: regime_detail}}
    asset_trends: dict[int, dict[str, str]] = {}
    for code in _TREND_CODES:
        tf = _TF_MAP[code]
        try:
            t = get_ind_table(code)
        except Exception:
            continue
        rows = s.execute(
            sa.select(t.c.asset_id, t.c.value).where(t.c.date == snap_date)
        ).fetchall()
        for asset_id, value_str in rows:
            asset_trends.setdefault(asset_id, {})[tf] = value_str

    if not asset_trends:
        return

    # Leer metadatos de grupo de cada activo
    asset_meta = {
        a.id: {
            "sector":          a.sector_id,
            "market":          a.market_id,
            "industry":        a.industry_id,
            "country":         a.country_id,
            "instrument_type": a.instrument_type_id,
        }
        for a in s.query(
            Asset.id, Asset.sector_id, Asset.market_id,
            Asset.industry_id, Asset.country_id, Asset.instrument_type_id,
        ).all()
    }

    groups: dict = defaultdict(lambda: {"d": [], "w": [], "m": []})

    for asset_id, trends in asset_trends.items():
        meta = asset_meta.get(asset_id, {})
        for _, group_type in _GROUP_DIMS:
            group_id = meta.get(group_type)
            if group_id is None:
                continue
            for tf, value_str in trends.items():
                score = _REGIME_SCORE.get(value_str or "")
                if score is not None:
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
    if snap_date is None:
        snap_date = get_default_snap_date()

    try:
        compute_group_snapshots(snap_date)
    except Exception as exc:
        logger.error(
            "indicator_service: error en compute_group_snapshots para %s: %s", snap_date, exc
        )

    logger.info("indicator_service: run_daily completado para %s", snap_date)
    return 0
