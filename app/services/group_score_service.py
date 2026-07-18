"""
Servicio de scores de grupo (ex indicator_service, renombrado: no calcula
ningún indicador). Agrega la tendencia por sector/mercado/industria/país/
tipo de instrumento leyendo las tablas ind_trend_* y la persiste en
group_scores — el insumo de las señales de grupo (source=group).
La escritura individual por activo ocurre en technical_service.compute_current_indicators().

También vive acá get_default_target_date (última fecha con precios), usada
por todo el pipeline señales → estrategias.
"""
import logging
import sqlalchemy as sa
from collections import defaultdict
from datetime import date as date_type

from app.database import get_session
from app.models import Asset, GroupScore
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


def get_default_target_date() -> date_type:
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


def compute_group_scores(target_date: date_type) -> None:
    """
    Agrega valores de tendencia por grupos para target_date.
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
            # value IS NOT NULL: en una tabla ancha la fila de target_date puede
            # tener trend_* en NULL (la escribió otro código de la cadencia); sin
            # el filtro entraría como tendencia None. En las ind_trend_* per-código
            # (sin value NULL) es equivalente.
            sa.select(t.c.asset_id, t.c.value)
            .where(t.c.date == target_date, t.c.value.isnot(None))
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

    aggregated = aggregate_group_scores(asset_trends, asset_meta)

    # Upsert ORM (una fecha): el modo rango escribe estas mismas filas en
    # bloque — la agregación compartida vive en aggregate_group_scores
    existing = {
        (g.group_type, g.group_id): g
        for g in s.query(GroupScore).filter(GroupScore.date == target_date).all()
    }
    for (group_type, group_id), vals in aggregated.items():
        gscore = existing.get((group_type, group_id))
        if gscore is None:
            gscore = GroupScore(
                group_type=group_type,
                group_id=group_id,
                date=target_date,
            )
            s.add(gscore)
        gscore.regime_score_d = vals["regime_score_d"]
        gscore.regime_score_w = vals["regime_score_w"]
        gscore.regime_score_m = vals["regime_score_m"]
        gscore.n_assets       = vals["n_assets"]

    s.commit()


def aggregate_group_scores(asset_trends: dict, asset_meta: dict) -> dict[tuple, dict]:
    """{(group_type, group_id): {regime_score_d/w/m, n_assets}} — LÓGICA
    PURA compartida por el camino por-fecha y el modo rango.

    asset_trends: {asset_id: {tf: regime_detail}} (tf: d|w|m).
    asset_meta:   {asset_id: {group_type: group_id}}."""
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

    out: dict[tuple, dict] = {}
    for key, scores in groups.items():
        counts = [len(scores["d"]), len(scores["w"]), len(scores["m"])]
        out[key] = {
            "regime_score_d": _avg(scores["d"]),
            "regime_score_w": _avg(scores["w"]),
            "regime_score_m": _avg(scores["m"]),
            "n_assets":       max(counts) if any(counts) else 0,
        }
    return out


def run_daily(target_date: date_type | None = None) -> int:
    if target_date is None:
        target_date = get_default_target_date()

    try:
        compute_group_scores(target_date)
    except Exception as exc:
        logger.error(
            "group_score_service: error en compute_group_scores para %s: %s", target_date, exc
        )

    logger.info("group_score_service: run_daily completado para %s", target_date)
    return 0
