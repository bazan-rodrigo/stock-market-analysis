"""
Servicio de scores de grupo (ex indicator_service, renombrado: no calcula
ningún indicador). Agrega la tendencia por sector/mercado/industria/país/
tipo de instrumento leyendo las tablas ind_trend_*. El resultado NO se
persiste: lo calcula AL VUELO group_scores_for(), que lee el Mapa de
Tendencia de Mercado (ya no hay tabla group_scores ni señales de grupo).

También vive acá get_default_target_date (última fecha con precios), usada
por todo el pipeline señales → estrategias.
"""
import logging
import sqlalchemy as sa
from collections import defaultdict
from datetime import date as date_type, timedelta

from app.database import get_session
from app.models import Asset
from app.models.indicator_store import ASOF_MAX_LOOKBACK_DAYS, get_ind_table

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

# La barra semanal/mensual se guarda etiquetada al CIERRE de su período
# (domingo con resample("W"), fin de mes con resample("M")), que cae DESPUÉS
# del último día con precio. La barra cuyo período contiene target_date —la
# EN CURSO, preliminar— es la primera con fecha >= target_date, hasta ~un mes
# más adelante. Este tope acota esa búsqueda hacia adelante para no arrastrar
# una barra muy posterior cuando el activo tiene un hueco. Compartido con
# signal_backfill_range para que el camino por-fecha y el de rango coincidan.
COVERING_MAX_AHEAD_DAYS = 40


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


def _load_asset_meta(s) -> dict:
    """{asset_id: {group_type: group_id}} para todos los activos."""
    return {
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


def _read_asset_trends(s, target_date: date_type) -> dict:
    """{asset_id: {tf: regime_detail}} vigente en target_date, leído de las
    ind_trend_*. Cada cadencia toma su barra VIGENTE aunque target_date no sea
    día hábil del activo (p.ej. un sábado que cotizan monedas y las acciones no):

    - Diaria: as-of hacia atrás — última barra <= target_date (la barra diaria
      se etiqueta en el día hábil real), no más vieja que ASOF_MAX_LOOKBACK_DAYS.
    - Semanal/mensual: covering hacia adelante — primera barra >= target_date
      (cierran en domingo / fin de mes, DESPUÉS de target_date), tope
      COVERING_MAX_AHEAD_DAYS para no arrastrar una barra lejana si hay hueco.
    """
    asset_trends: dict[int, dict[str, str]] = {}
    for code in _TREND_CODES:
        tf = _TF_MAP[code]
        try:
            t = get_ind_table(code)
        except Exception:
            continue
        if tf == "d":
            cutoff = target_date - timedelta(days=ASOF_MAX_LOOKBACK_DAYS)
            rows = s.execute(
                sa.select(t.c.asset_id, t.c.value)
                .where(t.c.date >= cutoff, t.c.date <= target_date,
                       t.c.value.isnot(None))
                .order_by(t.c.date)           # ascendente → la ÚLTIMA por activo gana
            ).fetchall()
            for asset_id, value_str in rows:
                asset_trends.setdefault(asset_id, {})[tf] = value_str
        else:
            rows = s.execute(
                sa.select(t.c.asset_id, t.c.value)
                .where(t.c.date >= target_date,
                       t.c.date <= target_date + timedelta(days=COVERING_MAX_AHEAD_DAYS),
                       t.c.value.isnot(None))
                .order_by(t.c.date)           # ascendente → la PRIMERA por activo gana
            ).fetchall()
            seen: set = set()
            for asset_id, value_str in rows:
                if asset_id not in seen:
                    seen.add(asset_id)
                    asset_trends.setdefault(asset_id, {})[tf] = value_str
    return asset_trends


def group_scores_for(target_date: date_type) -> dict[tuple, dict]:
    """Scores de tendencia por grupo para target_date, CALCULADOS AL VUELO —
    NO se persisten. Es la fuente del Mapa de Tendencia de Mercado. Devuelve
    {(group_type, group_id): {regime_score_d/w/m, n_assets}} (mismo shape que
    aggregate_group_scores). La tendencia por activo ya está persistida para
    toda la historia, así que cualquier target_date es válido."""
    s = get_session()
    asset_trends = _read_asset_trends(s, target_date)
    if not asset_trends:
        return {}
    return aggregate_group_scores(asset_trends, _load_asset_meta(s))
