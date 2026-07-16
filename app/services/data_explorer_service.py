"""Explorador de datos crudos: lecturas de SOLO LECTURA de las tablas internas
del pipeline (indicadores históricos/vigentes, fundamentales, señales, scores)
para inspección manual sin escribir SQL. Lo consume la pantalla admin
`/admin/data-explorer`.

Cada función devuelve (nombre_de_tabla, columnas, registros) para que la UI
muestre de dónde sale el dato (así el usuario va conociendo las tablas) y lo
pinte en una DataTable genérica."""
from __future__ import annotations

import datetime

import sqlalchemy as sa

from app.database import get_session
from app.models.indicator_store import CurrentIndicatorValue, get_ind_table

# Tope defensivo de filas por consulta (las series históricas pueden ser largas)
MAX_ROWS = 5000

# Catálogo de conjuntos de datos: qué combos necesita cada uno. Lo usan tanto
# la página (para mostrar/ocultar combos) como el callback (para validar).
DATASETS = {
    "ind_hist":     {"label": "Indicador técnico – histórico",
                     "combos": ["indicator", "asset"]},
    "ind_current":  {"label": "Indicador técnico – vigente",
                     "combos": ["asset"]},
    "fundamentals": {"label": "Fundamentales (trimestral)",
                     "combos": ["asset"]},
    "signal_asset": {"label": "Señal – por activo",
                     "combos": ["signal", "asset"]},
    "signal_group": {"label": "Señal – por grupo",
                     "combos": ["signal", "group_type", "group"]},
    "group_scores": {"label": "Group scores (tendencia de grupo)",
                     "combos": ["group_type", "group"]},
    "strategy":     {"label": "Resultado de estrategia",
                     "combos": ["strategy", "asset"]},
}


def _fmt(v):
    if isinstance(v, (datetime.date, datetime.datetime)):
        return str(v)
    return v


# ── Indicadores técnicos ──────────────────────────────────────────────────────

def indicator_history(code: str, asset_id: int):
    """Serie histórica de un indicador para un activo, desde ind_{code}."""
    s = get_session()
    tbl = get_ind_table(code)  # puede lanzar si la tabla no existe (indicador
                               # sin historia calculada) — lo maneja el callback
    cols = [c for c in tbl.c if c.name != "asset_id"]
    names = [c.name for c in cols]
    rows = s.execute(
        sa.select(*cols)
        .where(tbl.c.asset_id == asset_id)
        .order_by(tbl.c.date)
        .limit(MAX_ROWS)
    ).all()
    records = [{n: _fmt(v) for n, v in zip(names, row)} for row in rows]
    return f"ind_{code}", names, records


def current_indicators(asset_id: int):
    """Todos los indicadores vigentes (sin historia) de un activo."""
    from app.models.indicator_definition import IndicatorDefinition

    s = get_session()
    name_by_code = {d.code: d.name
                    for d in s.query(IndicatorDefinition.code,
                                     IndicatorDefinition.name).all()}
    rows = (s.query(CurrentIndicatorValue)
            .filter(CurrentIndicatorValue.asset_id == asset_id)
            .order_by(CurrentIndicatorValue.code).all())
    records = [{"code": r.code, "name": name_by_code.get(r.code, ""),
                "value_num": r.value_num, "value_str": r.value_str}
               for r in rows]
    return "current_indicator_values", ["code", "name", "value_num", "value_str"], records


# ── Fundamentales ─────────────────────────────────────────────────────────────

_FUND_COLS = ["period_date", "revenue", "gross_profit", "operating_income",
              "net_income", "ebitda", "total_debt", "equity", "shares",
              "fcf", "operating_cf", "eps_actual", "eps_estimated",
              "nopat", "invested_capital_avg"]


def fundamentals(asset_id: int):
    """Historia trimestral de fundamentales de un activo (más reciente arriba)."""
    from app.models.fundamental_quarterly import FundamentalQuarterly

    s = get_session()
    rows = (s.query(FundamentalQuarterly)
            .filter(FundamentalQuarterly.asset_id == asset_id)
            .order_by(FundamentalQuarterly.period_date.desc()).all())
    records = [{c: _fmt(getattr(r, c)) for c in _FUND_COLS} for r in rows]
    return "fundamental_quarterly", _FUND_COLS, records


# ── Scores (señales, grupos, estrategias) ─────────────────────────────────────

def signal_asset(signal_id: int, asset_id: int):
    import sqlalchemy as sa
    from app.models import signal_store

    s = get_session()
    t = signal_store.ensure_sig_table(signal_id, bind=s.connection())
    rows = s.execute(
        sa.select(t.c.date, t.c.score)
        .where(t.c.asset_id == asset_id)
        .order_by(t.c.date).limit(MAX_ROWS)).all()
    return t.name, ["date", "score"], \
        [{"date": str(d), "score": sc} for d, sc in rows]


def signal_group(signal_id: int, group_type: str, group_id: int):
    from app.models.group_signal_value import GroupSignalValue

    s = get_session()
    rows = (s.query(GroupSignalValue.date, GroupSignalValue.score)
            .filter(GroupSignalValue.signal_id == signal_id,
                    GroupSignalValue.group_type == group_type,
                    GroupSignalValue.group_id == group_id)
            .order_by(GroupSignalValue.date).limit(MAX_ROWS).all())
    return "group_signal_value", ["date", "score"], \
        [{"date": str(d), "score": sc} for d, sc in rows]


def group_scores(group_type: str, group_id: int):
    from app.models.group_scores import GroupScore

    s = get_session()
    cols = ["date", "regime_score_d", "regime_score_w", "regime_score_m", "n_assets"]
    rows = (s.query(GroupScore.date, GroupScore.regime_score_d,
                    GroupScore.regime_score_w, GroupScore.regime_score_m,
                    GroupScore.n_assets)
            .filter(GroupScore.group_type == group_type,
                    GroupScore.group_id == group_id)
            .order_by(GroupScore.date).limit(MAX_ROWS).all())
    return "group_scores", cols, \
        [dict(zip(cols, (str(r[0]), *r[1:]))) for r in rows]


def strategy_result(strategy_id: int, asset_id: int):
    import sqlalchemy as sa
    from app.models import signal_store

    s = get_session()
    t = signal_store.ensure_strat_table(strategy_id, bind=s.connection())
    rows = s.execute(
        sa.select(t.c.date, t.c.score)
        .where(t.c.asset_id == asset_id)
        .order_by(t.c.date).limit(MAX_ROWS)).all()
    return t.name, ["date", "score"], \
        [{"date": str(d), "score": sc} for d, sc in rows]


# ── Despacho ──────────────────────────────────────────────────────────────────

def fetch(dataset: str, *, indicator=None, asset=None, signal=None,
          strategy=None, group_type=None, group=None):
    """Devuelve (tabla, columnas, registros) para el conjunto elegido. Asume
    que el caller ya validó que estén los combos requeridos (DATASETS)."""
    if dataset == "ind_hist":
        return indicator_history(indicator, int(asset))
    if dataset == "ind_current":
        return current_indicators(int(asset))
    if dataset == "fundamentals":
        return fundamentals(int(asset))
    if dataset == "signal_asset":
        return signal_asset(int(signal), int(asset))
    if dataset == "signal_group":
        return signal_group(int(signal), group_type, int(group))
    if dataset == "group_scores":
        return group_scores(group_type, int(group))
    if dataset == "strategy":
        return strategy_result(int(strategy), int(asset))
    raise ValueError(f"Conjunto de datos desconocido: {dataset}")
