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

Dos consumidores comparten esta lógica: scripts/verify_delta_correctness.py
(CLI) y app/callbacks/admin_verify_callbacks.py (panel /admin/verify).
"""
import random

import pandas as pd
import sqlalchemy as sa

from app.database import get_session
from app.models import Asset, Price
from app.models.indicator_store import get_ind_table
from app.services.technical_service import (
    _BACKFILL_FNS, _DELTA_TAIL_MODE, _get_regime_config,
    _get_volatility_config, _resample_ohlc, _series_dates_values,
)

_TOL = 0.01  # tolerancia numérica: mismo redondeo que usa el sistema (.round(2))


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
