"""
Verifica que los valores guardados en ind_{code} (escritos por el sistema
de delta — _DELTA_TAIL_MODE, checksums, huecos, activos "vacíos") coincidan
con un recálculo fresco desde cero, para una muestra de activos reales.

Solo lee de la base (SELECT) — nunca escribe, nunca trunca, no toca
force=True ni ninguna tabla ind_*. Seguro de correr contra producción en
cualquier momento, cuantas veces se quiera.

Cómo funciona: para cada (código, activo), llama a la misma función de
cómputo que usa backfill_indicator (_BACKFILL_FNS[code]) directo en
memoria, sin pasar por el camino rápido/lento — el resultado es
equivalente a lo que produciría un rebuild completo (force=True) para ese
activo puntual. Compara esa serie "fresca" contra lo que hoy está
guardado en ind_{code}, fecha por fecha.

También hace chequeos de cordura (¿el valor tiene sentido, sin importar
cómo se calculó?) — RSI fuera de [0,100], un trend_* que no es ninguna
categoría conocida, un retorno diario de +50000%. Esto es independiente
de la comparación delta-vs-fresco: agarra bugs de FÓRMULA, no de caché
(si la fórmula está mal, el delta y el recálculo fresco van a coincidir
igual, calculando ambos el mismo valor incorrecto).

Y desde la extensión a fundamentales: mismo patrón para
_compute_quarterly_ratios/_compute_daily_ratios (ind_fundamental_*), con
el mismo motivo pero un riesgo distinto — el delta de fundamentales
(_backfill_fund_indicator) no tiene el caché sofisticado de indicadores
técnicos, así que no puede repetir esos bugs, pero tampoco vuelve a
calcular una fecha ya escrita si el trimestre correspondiente se revisa
más tarde (salvo el último trimestre, tratado como "preliminar").

Dos consumidores comparten esta lógica: scripts/verify_delta_correctness.py
(CLI) y app/callbacks/admin_verify_callbacks.py (panel /admin/verify).
"""
import random

import numpy as np
import pandas as pd
import sqlalchemy as sa

from app.database import get_session
from app.models import Asset, FundamentalQuarterly, Price
from app.models.indicator_store import get_ind_table
from app.services.fundamental_service import (
    _ALL_FUND_CODES, _FUND_DAILY_CODES, _Quarter, _compute_quarterly_ratios,
    _daily_ratio_series,
)
from app.services.technical_service import (
    _BACKFILL_FNS, _DELTA_TAIL_MODE, _get_regime_config,
    _get_volatility_config, _resample_ohlc, _series_dates_values,
)

_TOL = 0.01  # tolerancia numérica: mismo redondeo que usa el sistema (.round(2))

# ── Chequeos de cordura: ¿el valor tiene sentido, sin importar cómo se
# calculó? Límites deliberadamente laxos — el objetivo es atrapar lo
# obviamente roto (inf, signo invertido, error de unidades), no discutir
# si un valor extremo pero real es "razonable". Un activo genuinamente
# muy volátil no tiene que disparar un falso positivo acá.
_NUMERIC_BOUNDS: dict[str, tuple[float, float]] = {
    "rsi_daily": (0, 100), "rsi_weekly": (0, 100), "rsi_monthly": (0, 100),
    "atr_percentile_daily": (0, 100), "atr_percentile_weekly": (0, 100),
    "atr_percentile_monthly": (0, 100),
    # dist_sma20/50/200: (precio-sma)/sma*100 — distancia PORCENTUAL, no
    # z-score. Para activos volátiles (small caps, cripto) puede pasar
    # cómodamente 100-200% sin ser un bug — límite generoso.
    "dist_sma20": (-500, 2000), "dist_sma50": (-500, 2000), "dist_sma200": (-500, 2000),
    # dist_optimal_sma_*: (precio-sma)/desvío — esto sí es un z-score,
    # límite ajustado tiene sentido acá.
    "dist_optimal_sma_daily": (-50, 50), "dist_optimal_sma_weekly": (-50, 50),
    "dist_optimal_sma_monthly": (-50, 50),
    "return_daily": (-100, 2000),
    "return_monthly": (-100, 5000), "return_quarterly": (-100, 5000),
    "return_yearly": (-100, 20000), "return_52w": (-100, 20000),
    "relative_strength_52w": (-20000, 20000),
    # fundamentales: _safe_div_r devuelve fracciones (0.1 = 10%), no %
    "fundamental_net_margin": (-100, 100), "fundamental_gross_margin": (-100, 100),
    "fundamental_operating_margin": (-100, 100), "fundamental_roic": (-100, 100),
    "fundamental_debt_to_equity": (-10000, 10000),
    "fundamental_revenue_growth_yoy": (-1000, 100000),
    "fundamental_eps_growth_yoy": (-1000, 100000),
    "fundamental_pe_growth_yoy": (-1000, 100000),
    "fundamental_pe_ttm": (-100000, 100000), "fundamental_pb": (-100000, 100000),
    "fundamental_ps_ttm": (-100000, 100000),
}

# trend_*: combinaciones de _regime_detail (technical_service.py:164).
_TREND_VALUES = frozenset({
    "bullish", "bearish", "lateral",
    "bullish_nascent", "bearish_nascent", "lateral_nascent",
    "bullish_strong", "bearish_strong",
    "bullish_nascent_strong", "bearish_nascent_strong",
})
# volatility_*: f"{vol_regime}_{dur_regime}" (technical_service.py:282, 248).
_VOLATILITY_VALUES = frozenset({
    f"{v}_{d}" for v in ("baja", "normal", "alta", "extrema")
    for d in ("corta", "media", "larga")
})
_CATEGORICAL_VALUES: dict[str, frozenset] = {
    "trend_daily": _TREND_VALUES, "trend_weekly": _TREND_VALUES,
    "trend_monthly": _TREND_VALUES,
    "volatility_daily": _VOLATILITY_VALUES, "volatility_weekly": _VOLATILITY_VALUES,
    "volatility_monthly": _VOLATILITY_VALUES,
}


def check_sanity(code: str, value) -> str | None:
    """None si el valor es razonable para ese código; si no, una
    descripción corta de qué límite violó."""
    if value is None:
        return None
    if code in _CATEGORICAL_VALUES:
        if str(value) not in _CATEGORICAL_VALUES[code]:
            return f"categoría desconocida para {code}: {value!r}"
        return None
    bounds = _NUMERIC_BOUNDS.get(code)
    if bounds is None:
        return None
    try:
        v = float(value)
    except (TypeError, ValueError):
        return f"se esperaba numérico para {code}, vino {value!r}"
    lo, hi = bounds
    if not (lo <= v <= hi):
        return f"fuera de rango [{lo},{hi}] para {code}: {v}"
    return None


def _load_price_df(session, asset_id: int) -> pd.DataFrame:
    rows = session.execute(
        sa.select(Price.date, Price.close, Price.high, Price.low)
        .where(Price.asset_id == asset_id)
        .order_by(Price.date.asc())
    ).all()
    return pd.DataFrame(rows, columns=["date", "close", "high", "low"])


def _stored_values(session, code: str, asset_id: int) -> dict:
    t = get_ind_table(code)
    rows = session.execute(
        sa.select(t.c.date, t.c.value).where(t.c.asset_id == asset_id)
    ).all()
    return {d: v for d, v in rows}


def _values_equal(fresh, stored) -> bool:
    try:
        return abs(float(fresh) - float(stored)) <= _TOL
    except (TypeError, ValueError):
        return str(fresh) == str(stored)


def verify_asset_code(session, code: str, asset_id: int, df, regime_cfg, vol_cfg) -> list:
    """Devuelve la lista de diferencias (fecha, motivo, guardado, fresco)."""
    df_w = _resample_ohlc(df, "W")
    df_m = _resample_ohlc(df, "M")
    compute_fn = _BACKFILL_FNS[code]
    values = compute_fn(
        df=df, df_w=df_w, df_m=df_m,
        regime_cfg=regime_cfg, vol_cfg=vol_cfg,
        session=session, asset_id=asset_id,
        price_cache=None, best_sma_cache=None,
    )
    dates_list, vals_list = _series_dates_values(values, df)
    fresh = {d: v for d, v in zip(dates_list, vals_list) if pd.notna(v)}
    stored = _stored_values(session, code, asset_id)

    diffs = []
    for d in sorted(set(fresh) | set(stored)):
        fv, sv = fresh.get(d), stored.get(d)
        if fv is None and sv is not None:
            diffs.append((d, "solo en DB (¿debería haberse borrado?)", sv, fv))
        elif fv is not None and sv is None:
            diffs.append((d, "falta en DB (¿el delta no la escribió?)", sv, fv))
        elif not _values_equal(fv, sv):
            diffs.append((d, "valor distinto", sv, fv))
        if fv is not None:
            sanity = check_sanity(code, fv)
            if sanity:
                diffs.append((d, sanity, sv, fv))
    return diffs


def pick_sample_ids(session, sample: int) -> list:
    all_ids = [r[0] for r in session.execute(sa.select(Asset.id)).all()]
    return random.sample(all_ids, min(sample, len(all_ids)))


def ids_from_tickers(session, tickers: list) -> tuple[list, list]:
    """Devuelve (asset_ids, tickers_no_encontrados)."""
    rows = session.execute(
        sa.select(Asset.id, Asset.ticker).where(Asset.ticker.in_(tickers))
    ).all()
    found = {t: aid for aid, t in rows}
    missing = [t for t in tickers if t not in found]
    return list(found.values()), missing


def run_verification(codes: list | None = None, sample: int = 30,
                     tickers: list | None = None, progress_cb=None) -> dict:
    """Corre la verificación completa.

    codes: lista de códigos a chequear (default: todos los de _DELTA_TAIL_MODE
    que tengan función de backfill).
    tickers: si se pasa, verifica esos activos puntuales en vez de una
    muestra al azar (sample se ignora).
    progress_cb(cur, tot, label): opcional, para barra de progreso en UI.

    Devuelve {"codes", "asset_ids", "missing_tickers", "combos", "results"}
    — "results" es una lista de {"code", "asset_id", "ticker", "diffs"}
    solo para las combinaciones que SÍ tuvieron diferencias."""
    s = get_session()
    codes = [c for c in (codes or list(_DELTA_TAIL_MODE)) if c in _BACKFILL_FNS]

    missing_tickers = []
    if tickers:
        asset_ids, missing_tickers = ids_from_tickers(s, tickers)
    else:
        asset_ids = pick_sample_ids(s, sample)

    regime_cfg = _get_regime_config()
    vol_cfg    = _get_volatility_config()
    ticker_map = {a.id: a.ticker for a in
                  s.query(Asset).filter(Asset.id.in_(asset_ids)).all()}

    total_work = len(codes) * len(asset_ids)
    done = 0
    results = []

    if progress_cb:
        progress_cb(0, max(total_work, 1), "")

    for asset_id in asset_ids:
        df = _load_price_df(s, asset_id)
        if df.empty:
            done += len(codes)
            if progress_cb:
                progress_cb(done, max(total_work, 1), "")
            continue
        for code in codes:
            diffs = verify_asset_code(s, code, asset_id, df, regime_cfg, vol_cfg)
            if diffs:
                results.append({
                    "code": code, "asset_id": asset_id,
                    "ticker": ticker_map.get(asset_id, "?"),
                    "diffs": diffs,
                })
            done += 1
            if progress_cb:
                progress_cb(done, max(total_work, 1),
                           f"{code} / {ticker_map.get(asset_id, '?')}")

    return {
        "codes": codes, "asset_ids": asset_ids,
        "missing_tickers": missing_tickers,
        "combos": total_work, "results": results,
    }


# ── Fundamentales: mismo patrón, otra fuente de cómputo ──────────────────────

def _load_quarters(session, asset_id: int) -> list:
    rows = (session.query(FundamentalQuarterly)
            .filter_by(asset_id=asset_id)
            .order_by(FundamentalQuarterly.period_date.asc())
            .all())
    return [_Quarter(**{f: getattr(q, f) for f in _Quarter._fields}) for q in rows]


def _load_fund_price_rows(session, asset_id: int) -> list:
    rows = session.execute(
        sa.select(Price.date, Price.close)
        .where(Price.asset_id == asset_id, Price.close.isnot(None))
        .order_by(Price.date.asc())
    ).all()
    return [(d, float(c)) for d, c in rows]


def verify_asset_ratio_code(session, code: str, asset_id: int,
                            quarters: list, price_rows: list) -> list:
    """Equivalente a verify_asset_code, para un código fundamental."""
    if not quarters:
        return []
    q_ords = np.array([q.period_date.toordinal() for q in quarters])

    if code in _FUND_DAILY_CODES:
        if not price_rows:
            return []
        dates_seq       = [d for d, _ in price_rows]
        price_dates_ord = np.array([d.toordinal() for d, _ in price_rows])
        price_closes    = np.array([c for _, c in price_rows])
        series = _daily_ratio_series(quarters, q_ords, dates_seq,
                                     price_dates_ord, price_closes)
        fresh = {d: v for d, v in zip(dates_seq, series[code]) if not np.isnan(v)}
    else:
        fresh = {}
        for idx, q in enumerate(quarters):
            val = _compute_quarterly_ratios(quarters, idx).get(code)
            if val is not None:
                fresh[q.period_date] = val

    stored = _stored_values(session, code, asset_id)

    diffs = []
    for d in sorted(set(fresh) | set(stored)):
        fv, sv = fresh.get(d), stored.get(d)
        if fv is None and sv is not None:
            diffs.append((d, "solo en DB (¿debería haberse borrado?)", sv, fv))
        elif fv is not None and sv is None:
            diffs.append((d, "falta en DB (¿el delta no la escribió?)", sv, fv))
        elif not _values_equal(fv, sv):
            diffs.append((d, "valor distinto", sv, fv))
        if fv is not None:
            sanity = check_sanity(code, fv)
            if sanity:
                diffs.append((d, sanity, sv, fv))
    return diffs


def pick_fund_sample_ids(session, sample: int) -> list:
    """Solo activos con al menos un trimestre cargado (sin eso no hay
    nada que comparar)."""
    all_ids = [r[0] for r in session.execute(
        sa.select(FundamentalQuarterly.asset_id).distinct()
    ).all()]
    return random.sample(all_ids, min(sample, len(all_ids)))


def run_fund_verification(codes: list | None = None, sample: int = 30,
                          tickers: list | None = None, progress_cb=None) -> dict:
    """Equivalente a run_verification, para ratios fundamentales
    (ind_fundamental_*) — ver verify_asset_ratio_code."""
    s = get_session()
    codes = [c for c in (codes or sorted(_ALL_FUND_CODES)) if c in _ALL_FUND_CODES]

    missing_tickers = []
    if tickers:
        asset_ids, missing_tickers = ids_from_tickers(s, tickers)
    else:
        asset_ids = pick_fund_sample_ids(s, sample)

    ticker_map = {a.id: a.ticker for a in
                  s.query(Asset).filter(Asset.id.in_(asset_ids)).all()}

    total_work = len(codes) * len(asset_ids)
    done = 0
    results = []

    if progress_cb:
        progress_cb(0, max(total_work, 1), "")

    for asset_id in asset_ids:
        quarters   = _load_quarters(s, asset_id)
        price_rows = _load_fund_price_rows(s, asset_id)
        if not quarters:
            done += len(codes)
            if progress_cb:
                progress_cb(done, max(total_work, 1), "")
            continue
        for code in codes:
            diffs = verify_asset_ratio_code(s, code, asset_id, quarters, price_rows)
            if diffs:
                results.append({
                    "code": code, "asset_id": asset_id,
                    "ticker": ticker_map.get(asset_id, "?"),
                    "diffs": diffs,
                })
            done += 1
            if progress_cb:
                progress_cb(done, max(total_work, 1),
                           f"{code} / {ticker_map.get(asset_id, '?')}")

    return {
        "codes": codes, "asset_ids": asset_ids,
        "missing_tickers": missing_tickers,
        "combos": total_work, "results": results,
    }
