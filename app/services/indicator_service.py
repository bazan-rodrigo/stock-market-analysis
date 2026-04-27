"""
Servicio de indicadores.
Lee screener_snapshot y escribe indicator_snapshot (por fecha) y
group_indicator_snapshot (agrupado por sector/market).
"""
import logging
from collections import defaultdict
from datetime import date as date_type

from app.database import get_session
from app.models import Asset, IndicatorSnapshot, GroupIndicatorSnapshot, ScreenerSnapshot

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


def _score_regime(regime: str | None) -> float | None:
    if regime is None:
        return None
    return _REGIME_SCORE.get(regime)


def _avg(lst: list) -> float | None:
    if not lst:
        return None
    return round(sum(lst) / len(lst), 2)


def save_from_snapshot(
    asset_id: int, snap_date: date_type, snap: ScreenerSnapshot
) -> None:
    """Upsert de IndicatorSnapshot desde un ScreenerSnapshot ya calculado."""
    s = get_session()

    isnap = (
        s.query(IndicatorSnapshot)
        .filter(
            IndicatorSnapshot.asset_id == asset_id,
            IndicatorSnapshot.date == snap_date,
        )
        .first()
    )

    if isnap is None:
        isnap = IndicatorSnapshot(asset_id=asset_id, date=snap_date)
        s.add(isnap)

    isnap.regime_d          = snap.regime_d
    isnap.regime_w          = snap.regime_w
    isnap.regime_m          = snap.regime_m
    isnap.dd_current        = snap.dd_current
    isnap.dd_max1           = snap.dd_max1
    isnap.vol_d             = snap.vol_d
    isnap.vol_w             = snap.vol_w
    isnap.vol_m             = snap.vol_m
    isnap.atr_pct_d         = snap.atr_pct_d
    isnap.atr_pct_w         = snap.atr_pct_w
    isnap.atr_pct_m         = snap.atr_pct_m
    isnap.rsi               = snap.rsi
    isnap.rsi_w             = snap.rsi_w
    isnap.rsi_m             = snap.rsi_m
    isnap.var_daily         = snap.var_daily
    isnap.var_month         = snap.var_month
    isnap.var_quarter       = snap.var_quarter
    isnap.var_year          = snap.var_year
    isnap.var_52w           = snap.var_52w
    isnap.dist_sma_d        = snap.dist_sma_d
    isnap.dist_sma_w        = snap.dist_sma_w
    isnap.dist_sma_m        = snap.dist_sma_m
    isnap.vs_sma20          = snap.vs_sma20
    isnap.vs_sma50          = snap.vs_sma50
    isnap.vs_sma200         = snap.vs_sma200
    isnap.pivot_resist_pct  = snap.pivot_resist_pct
    isnap.pivot_support_pct = snap.pivot_support_pct
    isnap.last_close        = snap.last_close

    s.commit()


def compute_group_snapshots(snap_date: date_type) -> None:
    """
    Agrega IndicatorSnapshot por sector y market para snap_date.
    Calcula regime_score_d/w/m como promedio de los scores de cada activo.
    """
    s = get_session()

    rows = (
        s.query(
            Asset.sector_id,
            Asset.market_id,
            IndicatorSnapshot.regime_d,
            IndicatorSnapshot.regime_w,
            IndicatorSnapshot.regime_m,
        )
        .join(IndicatorSnapshot, IndicatorSnapshot.asset_id == Asset.id)
        .filter(IndicatorSnapshot.date == snap_date)
        .all()
    )

    if not rows:
        return

    groups: dict = defaultdict(lambda: {"d": [], "w": [], "m": []})

    for sector_id, market_id, reg_d, reg_w, reg_m in rows:
        score_d = _score_regime(reg_d)
        score_w = _score_regime(reg_w)
        score_m = _score_regime(reg_m)

        for group_type, group_id in [("sector", sector_id), ("market", market_id)]:
            if group_id is None:
                continue
            key = (group_type, group_id)
            if score_d is not None:
                groups[key]["d"].append(score_d)
            if score_w is not None:
                groups[key]["w"].append(score_w)
            if score_m is not None:
                groups[key]["m"].append(score_m)

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
    Pipeline diario de indicadores:
    1. Copia screener_snapshot → indicator_snapshot para cada activo.
    2. Agrega group_indicator_snapshot para snap_date.
    Devuelve cantidad de activos procesados.
    """
    from datetime import date as dt_date

    if snap_date is None:
        snap_date = dt_date.today()

    s = get_session()
    snaps = s.query(ScreenerSnapshot).all()
    processed = 0

    for snap in snaps:
        try:
            save_from_snapshot(snap.asset_id, snap_date, snap)
            processed += 1
        except Exception as exc:
            logger.error(
                "indicator_service: error en asset_id=%d: %s", snap.asset_id, exc
            )

    compute_group_snapshots(snap_date)
    logger.info(
        "indicator_service: run_daily completado para %s (%d activos)", snap_date, processed
    )
    return processed
