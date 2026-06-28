"""
Servicio de screener.
Calcula métricas técnicas por activo y las persiste en screener_snapshot (caché de gráficos)
e indicator_values (serie temporal EAV de indicadores).
"""
import json
import logging
from concurrent.futures import ThreadPoolExecutor as _TPE
from datetime import date, datetime

import numpy as np
import pandas as pd

from sqlalchemy import and_, func
from sqlalchemy.orm import joinedload

from app.database import get_session
from app.models import Asset, DrawdownConfig, Price, RegimeConfig, VolatilityConfig
from app.models.indicator_definition import IndicatorDefinition
from app.models.indicator_value import IndicatorValue
from app.services import sr_service

logger = logging.getLogger(__name__)

# Mínimo de filas de precios para calcular métricas
_MIN_ROWS = 20

# Barras cargadas en modo quick (~4 años, suficiente warmup para EMA mensual + pendiente)
_QUICK_DAYS = 1500

# Workers para paralelizar cálculos pandas dentro de un snapshot (régimen/vol/best_ma)
_CALC_WORKERS = 4
# Workers para paralelizar snapshots en recompute_all (un activo por thread)
_SNAPSHOT_WORKERS = 6

# Score de tendencia por régimen: -100 a +100
_REGIME_SCORE: dict[str, int] = {
    "bullish_strong":         100,
    "bullish_nascent_strong":  75,
    "bullish":                 60,
    "bullish_nascent":         40,
    "lateral_nascent":          5,
    "lateral":                  0,
    "bearish_nascent":        -40,
    "bearish_nascent_strong": -75,
    "bearish":                -60,
    "bearish_strong":        -100,
}

_GS_DIMS = [
    ("sector_id",          "sector_name"),
    ("industry_id",        "industry_name"),
    ("country_id",         "country_name"),
    ("instrument_type_id", "itype_name"),
    ("market_id",          "market_name"),
]

_MA_PERIODS = [5, 8, 10, 13, 15, 21, 25, 30, 34, 50, 55, 89, 100, 144, 200, 233]


def _find_best_ma(close: pd.Series, high: pd.Series, low: pd.Series, kind: str = "sma") -> int | None:
    """
    Devuelve el período de SMA/EMA que el precio respeta más como soporte/resistencia.
    Métrica: tasa de rebote = velas_que_tocaron_y_aguantaron / velas_que_tocaron.
    Sin sesgo de período: compara la fracción de veces que el precio rebotó al tocar la MA.
    """
    best_period = None
    best_score  = -1.0
    prev_c = close.shift(1)

    for period in _MA_PERIODS:
        if len(close) < period * 2:
            continue

        ma = close.rolling(period).mean() if kind == "sma" \
             else close.ewm(span=period, adjust=False).mean()

        valid         = ma.notna()
        touched       = valid & (low <= ma) & (ma <= high)
        total_touches = int(touched.sum())

        if total_touches < 5:
            continue

        bounce       = ((prev_c >= ma) & (close >= ma)) | ((prev_c <= ma) & (close <= ma))
        bounces_held = int((touched & bounce).sum())

        score = bounces_held / total_touches
        if score > best_score:
            best_score  = score
            best_period = period

    return best_period


def _resample_ohlc(df: pd.DataFrame, freq: str) -> pd.DataFrame:
    tmp = df.copy()
    tmp["date"] = pd.to_datetime(tmp["date"])
    tmp = tmp.set_index("date")
    rule = "W" if freq == "W" else "M"
    agg = {"close": "last", "high": "max", "low": "min"}
    try:
        resampled = tmp.resample(rule).agg(agg)
    except ValueError:
        resampled = tmp.resample("ME").agg(agg)
    resampled = resampled.dropna(subset=["close"])
    resampled.index.name = "date"
    return resampled.reset_index()


def _get_drawdown_config():
    s = get_session()
    cfg = s.query(DrawdownConfig).filter(DrawdownConfig.id == 1).first()
    if cfg is None:
        cfg = DrawdownConfig(id=1, min_depth_pct=20.0)
        s.add(cfg)
        s.commit()
    return cfg


def _compute_dd_events(df: pd.DataFrame, min_depth_pct: float) -> list[dict]:
    """Identifica caídas significativas entre máximos históricos consecutivos."""
    close = df["close"].values
    dates = df["date"].values
    events = []
    ath = close[0]
    in_dd = False
    dd_start_i = trough_i = 0

    for i in range(len(close)):
        if close[i] >= ath:
            if in_dd:
                depth = (close[trough_i] - ath) / ath * 100
                if depth <= -min_depth_pct:
                    events.append({
                        "start":  _date_str(dates[dd_start_i]),
                        "trough": _date_str(dates[trough_i]),
                        "end":    _date_str(dates[i]),
                        "depth":  round(depth, 1),
                    })
                in_dd = False
            ath = close[i]
        else:
            if not in_dd:
                in_dd, dd_start_i, trough_i = True, i, i
            elif close[i] < close[trough_i]:
                trough_i = i

    if in_dd:
        depth = (close[trough_i] - ath) / ath * 100
        if depth <= -min_depth_pct:
            events.append({
                "start":  _date_str(dates[dd_start_i]),
                "trough": _date_str(dates[trough_i]),
                "end":    None,
                "depth":  round(depth, 1),
            })
    return events


def _get_regime_config():
    s = get_session()
    cfg = s.query(RegimeConfig).filter(RegimeConfig.id == 1).first()
    if cfg is None:
        cfg = RegimeConfig(
            id=1,
            ema_period_d=200,
            ema_period_w=50,
            ema_period_m=20,
            slope_lookback=20,
            slope_threshold_pct=0.5,
            confirm_bars=3,
            nascent_bars=20,
            strong_slope_multiplier=2.0,
        )
        s.add(cfg)
        s.commit()
    return cfg


def _get_volatility_config():
    s = get_session()
    cfg = s.query(VolatilityConfig).filter(VolatilityConfig.id == 1).first()
    if cfg is None:
        cfg = VolatilityConfig(
            id=1,
            atr_period=14,
            pct_low=25.0,
            pct_high=75.0,
            pct_extreme=90.0,
            confirm_bars=3,
            dur_short_pct=33.0,
            dur_long_pct=67.0,
        )
        s.add(cfg)
        s.commit()
    return cfg


def _date_str(val) -> str:
    return str(val.date()) if hasattr(val, "date") else str(val)


def _regime_detail(regime: str, bars: int, slope_last: float,
                   threshold_pct: float, nascent_bars: int, strong_mult: float) -> str:
    is_nascent = bars < nascent_bars
    is_strong  = abs(slope_last) > threshold_pct * strong_mult
    if regime in ("bullish", "bearish"):
        if is_nascent and is_strong:
            return f"{regime}_nascent_strong"
        if is_nascent:
            return f"{regime}_nascent"
        if is_strong:
            return f"{regime}_strong"
        return regime
    # lateral: no puede ser "fuerte" por definición (pendiente dentro del umbral)
    return "lateral_nascent" if is_nascent else "lateral"


def _atr_series(df: pd.DataFrame, period: int) -> pd.Series:
    prev_close = df["close"].shift(1)
    tr = pd.concat([
        df["high"] - df["low"],
        (df["high"] - prev_close).abs(),
        (df["low"] - prev_close).abs(),
    ], axis=1).max(axis=1)
    return tr.ewm(alpha=1 / period, min_periods=period, adjust=False).mean()


def _classify_duration(bars: int, hist: list[int], dur_short_pct: float, dur_long_pct: float) -> str:
    if len(hist) < 3:
        return "media"
    p_short = float(np.percentile(hist, dur_short_pct))
    p_long = float(np.percentile(hist, dur_long_pct))
    if bars <= p_short:
        return "corta"
    if bars >= p_long:
        return "larga"
    return "media"


def _compute_vol_zones(
    df: pd.DataFrame,
    atr_period: int,
    confirm_bars: int,
    pct_low: float,
    pct_high: float,
    pct_extreme: float,
    dur_short_pct: float,
    dur_long_pct: float,
) -> list[dict]:
    min_bars = atr_period * 3
    if len(df) < min_bars:
        return []

    atr = _atr_series(df, atr_period)
    valid = atr.dropna()
    if valid.empty:
        return []

    # Umbrales de percentil sobre toda la historia
    th_low     = float(np.nanpercentile(valid, pct_low))
    th_high    = float(np.nanpercentile(valid, pct_high))
    th_extreme = float(np.nanpercentile(valid, pct_extreme))

    # ── Clasificación vectorizada (libera GIL via numpy) ────────────────────
    atr_vals = atr.values
    # Códigos: 0=NaN, 1=baja, 2=normal, 3=alta, 4=extrema
    raw_codes = np.where(np.isnan(atr_vals), 0,
                np.where(atr_vals >= th_extreme, 4,
                np.where(atr_vals >= th_high,    3,
                np.where(atr_vals <= th_low,     1, 2)))).astype(np.int8)

    # ── Confirmación anti-whipsaw ────────────────────────────────────────────
    n = len(raw_codes)
    confirmed = np.zeros(n, dtype=np.int8)
    current = pending = pending_n = 0
    for i in range(n):
        r = int(raw_codes[i])
        if r == 0:
            confirmed[i] = current
        elif r == current:
            pending = pending_n = 0
            confirmed[i] = current
        elif r == pending:
            pending_n += 1
            if pending_n >= confirm_bars:
                current = r; pending = pending_n = 0
            confirmed[i] = current
        else:
            pending = r; pending_n = 1
            confirmed[i] = current

    # ── Construir zonas ──────────────────────────────────────────────────────
    _CODE = [None, "baja", "normal", "alta", "extrema"]
    dates_arr = df["date"].values
    # Percentile rank vectorizado via searchsorted: O(N log M) vs O(N*M) anterior
    valid_sorted = np.sort(valid.values)
    n_valid = len(valid_sorted)
    atr_pct_ranks = np.full(n, np.nan)
    if n_valid > 0:
        valid_mask = ~np.isnan(atr_vals)
        atr_pct_ranks[valid_mask] = (
            np.searchsorted(valid_sorted, atr_vals[valid_mask]) / n_valid * 100
        )

    zones = []
    for i in range(n):
        c = int(confirmed[i])
        if c == 0:
            continue
        vr = _CODE[c]
        dt = _date_str(dates_arr[i])
        apr = atr_pct_ranks[i]
        atr_pct_rank = float(apr) if not np.isnan(apr) else None

        if not zones or zones[-1]["vol_regime"] != vr:
            if zones:
                zones[-1]["end"] = _date_str(dates_arr[i - 1])
            zones.append({
                "start": dt, "end": dt,
                "vol_regime": vr,
                "_bars": 1,
                "atr_pct": round(atr_pct_rank, 1) if atr_pct_rank is not None else None,
            })
        else:
            zones[-1]["_bars"] += 1
            if atr_pct_rank is not None:
                zones[-1]["atr_pct"] = round(atr_pct_rank, 1)

    if not zones:
        return []
    zones[-1]["end"] = _date_str(dates_arr[-1])

    # Clasificar duración de cada zona comparando contra historia del mismo régimen
    # Recopilar duraciones de zonas completadas (todas salvo la última)
    dur_hist: dict[str, list[int]] = {"baja": [], "normal": [], "alta": [], "extrema": []}
    for z in zones[:-1]:
        dur_hist[z["vol_regime"]].append(z["_bars"])

    for z in zones:
        z["dur_regime"] = _classify_duration(
            z["_bars"], dur_hist[z["vol_regime"]], dur_short_pct, dur_long_pct
        )
        z.pop("_bars", None)

    return zones


def _compute_regime_zones(
    df: pd.DataFrame,
    ema_period: int,
    slope_lookback: int,
    slope_threshold_pct: float,
    confirm_bars: int,
    nascent_bars: int = 20,
    strong_slope_multiplier: float = 2.0,
) -> list[dict]:
    min_bars = ema_period + slope_lookback + confirm_bars
    if len(df) < min_bars:
        return []

    close = df["close"]
    ema   = close.ewm(span=ema_period, adjust=False).mean()
    slope = (ema - ema.shift(slope_lookback)) / ema.shift(slope_lookback) * 100

    # ── Clasificación vectorizada (libera GIL via numpy) ────────────────────
    s_vals = slope.values
    e_vals = ema.values
    c_vals = close.values
    nan_mask = np.isnan(s_vals) | np.isnan(e_vals)
    # Códigos: 0=NaN, 1=lateral, 2=bullish, 3=bearish
    raw_codes = np.where(nan_mask, 0,
                np.where((s_vals > slope_threshold_pct) & (c_vals > e_vals), 2,
                np.where((s_vals < -slope_threshold_pct) & (c_vals < e_vals), 3, 1))).astype(np.int8)

    # ── Confirmación ─────────────────────────────────────────────────────────
    n = len(raw_codes)
    confirmed = np.zeros(n, dtype=np.int8)
    current = pending = pending_n = 0
    for i in range(n):
        r = int(raw_codes[i])
        if r == 0:
            confirmed[i] = current
        elif r == current:
            pending = pending_n = 0
            confirmed[i] = current
        elif r == pending:
            pending_n += 1
            if pending_n >= confirm_bars:
                current = r; pending = pending_n = 0
            confirmed[i] = current
        else:
            pending = r; pending_n = 1
            confirmed[i] = current

    # ── Construir zonas con sub-categoría ────────────────────────────────────
    _CODE = [None, "lateral", "bullish", "bearish"]
    dates_arr = df["date"].values
    zones = []
    for i in range(n):
        c = int(confirmed[i])
        if c == 0:
            continue
        regime = _CODE[c]
        dt = _date_str(dates_arr[i])
        sl_val = float(s_vals[i]) if not np.isnan(s_vals[i]) else 0.0
        if not zones or zones[-1]["regime"] != regime:
            if zones:
                prev = zones[-1]
                prev["end"] = _date_str(dates_arr[i - 1])
                prev["regime_detail"] = _regime_detail(
                    prev["regime"], prev["_bars"], prev["_slope_last"],
                    slope_threshold_pct, nascent_bars, strong_slope_multiplier,
                )
            zones.append({"start": dt, "end": dt, "regime": regime,
                          "_bars": 1, "_slope_last": sl_val})
        else:
            zones[-1]["_bars"] += 1
            zones[-1]["_slope_last"] = sl_val

    if zones:
        last = zones[-1]
        last["end"] = _date_str(df.iloc[-1]["date"])
        last["regime_detail"] = _regime_detail(
            last["regime"], last["_bars"], last["_slope_last"],
            slope_threshold_pct, nascent_bars, strong_slope_multiplier,
        )

    # Limpiar campos internos
    for z in zones:
        z.pop("_bars", None)
        z.pop("_slope_last", None)

    return zones


def _rsi(close: pd.Series, period: int = 14) -> float | None:
    if len(close) < period + 1:
        return None
    delta = close.diff()
    gain = delta.clip(lower=0)
    loss = -delta.clip(upper=0)
    avg_gain = gain.ewm(alpha=1 / period, min_periods=period, adjust=False).mean()
    avg_loss = loss.ewm(alpha=1 / period, min_periods=period, adjust=False).mean()
    rs = avg_gain / avg_loss.replace(0, float("nan"))
    rsi_series = (100 - (100 / (1 + rs))).fillna(100)
    val = rsi_series.iloc[-1]
    return float(val) if not pd.isna(val) else None


def _sma_zscore(close: pd.Series, period: int) -> float | None:
    """Distancia del último cierre desde la SMA_period, en desviaciones estándar."""
    if len(close) < period + 1:
        return None
    sma = close.rolling(period).mean()
    std = close.rolling(period).std()
    last_sma = sma.iloc[-1]
    last_std = std.iloc[-1]
    if pd.isna(last_sma) or pd.isna(last_std) or last_std == 0:
        return None
    return round((float(close.iloc[-1]) - float(last_sma)) / float(last_std), 2)


def _pct_change(current: float, reference: float) -> float | None:
    if current is not None and reference is not None and reference != 0:
        return round((current - reference) / reference * 100, 2)
    return None


def _closest_price_on_or_before(df: pd.DataFrame, target: date) -> float | None:
    """Precio de cierre en o antes de target."""
    subset = df[df["date"] <= target]
    if subset.empty:
        return None
    return float(subset.iloc[-1]["close"])


# Cache de indicator_id por code para evitar queries repetidas por snapshot
_ind_id_cache: dict[str, int] = {}
# IDs de indicadores con keep_history=False (solo se conserva el valor vigente)
_ind_no_history_ids: set[int] = set()


def _ensure_ind_cache(session) -> None:
    global _ind_id_cache, _ind_no_history_ids
    if not _ind_id_cache:
        for d in session.query(IndicatorDefinition).all():
            _ind_id_cache[d.code] = d.id
            if not d.keep_history:
                _ind_no_history_ids.add(d.id)


def _write_indicator_values(session, asset_id: int, snap_date, values: dict) -> None:
    """Upsert de indicator_values para un activo en snap_date.

    Para indicadores con keep_history=False elimina filas previas de cualquier
    fecha antes de insertar, conservando solo el valor vigente.
    """
    _ensure_ind_cache(session)

    # Borrar filas previas para indicadores sin historia
    no_hist_ids = [
        _ind_id_cache[code]
        for code in values
        if code in _ind_id_cache and _ind_id_cache[code] in _ind_no_history_ids
    ]
    if no_hist_ids:
        session.query(IndicatorValue).filter(
            IndicatorValue.asset_id == asset_id,
            IndicatorValue.indicator_id.in_(no_hist_ids),
        ).delete(synchronize_session=False)

    existing = {
        iv.indicator_id: iv
        for iv in session.query(IndicatorValue).filter(
            IndicatorValue.asset_id == asset_id,
            IndicatorValue.date == snap_date,
        ).all()
    }

    for code, value in values.items():
        ind_id = _ind_id_cache.get(code)
        if ind_id is None:
            continue
        val_num = None
        val_str = None
        if isinstance(value, str):
            val_str = value
        elif value is not None:
            val_num = float(value)

        iv = existing.get(ind_id)
        if iv is None:
            iv = IndicatorValue(asset_id=asset_id, indicator_id=ind_id, date=snap_date)
            session.add(iv)
            existing[ind_id] = iv
        iv.value_num = val_num
        iv.value_str = val_str

    session.commit()


def compute_and_save_snapshot(
    asset_id: int,
    *,
    _dd_cfg=None,
    _regime_cfg=None,
    _vol_cfg=None,
    _sr_cfg=None,
    quick: bool = False,
) -> None:
    """
    Calcula y persiste el snapshot de screener para un activo.

    quick=True: carga solo los últimos _QUICK_DAYS de precios y reutiliza del snapshot
    previo los campos que requieren historia completa (best_ma, dd_events, dd_max1-3).
    Si no existe snapshot previo, hace full automáticamente.
    """
    s = get_session()

    # En modo quick, leer best_ma previo desde indicator_values para reutilizarlo
    _ensure_ind_cache(s)
    _prev_best: dict[str, int] = {}
    if quick:
        _bm_codes = ["best_sma_d", "best_ema_d", "best_sma_w", "best_ema_w", "best_sma_m", "best_ema_m"]
        _bm_ids = {code: _ind_id_cache[code] for code in _bm_codes if code in _ind_id_cache}
        if _bm_ids:
            _bm_rows = s.query(IndicatorValue.indicator_id, IndicatorValue.value_num).filter(
                IndicatorValue.asset_id == asset_id,
                IndicatorValue.indicator_id.in_(list(_bm_ids.values())),
            ).all()
            _id_to_code = {v: k for k, v in _bm_ids.items()}
            _prev_best = {
                _id_to_code[ind_id]: int(val)
                for ind_id, val in _bm_rows
                if val is not None and ind_id in _id_to_code
            }

    # Sin best_ma previo no hay valores que reutilizar → forzar full
    if quick and not _prev_best.get("best_sma_d"):
        quick = False

    # --- Carga de precios ---
    if quick:
        rows = (
            s.query(Price.date, Price.close, Price.high, Price.low)
            .filter(Price.asset_id == asset_id)
            .order_by(Price.date.desc())
            .limit(_QUICK_DAYS)
            .all()
        )
        rows = list(reversed(rows))
    else:
        rows = (
            s.query(Price.date, Price.close, Price.high, Price.low)
            .filter(Price.asset_id == asset_id)
            .order_by(Price.date.asc())
            .all()
        )

    if len(rows) < _MIN_ROWS:
        return

    df = pd.DataFrame(rows, columns=["date", "close", "high", "low"])

    # --- Drawdown ---
    if quick:
        # ATH via query escalar (1 fila) para dd_current exacto
        ath = s.query(func.max(Price.close)).filter(Price.asset_id == asset_id).scalar()
        dd_current = float((df.iloc[-1]["close"] - ath) / ath * 100) if ath else 0.0
        # dd_max1-3: leer de indicator_values (última entrada disponible)
        dd_max1 = dd_max2 = dd_max3 = None
        if not _ind_id_cache:
            for d in s.query(IndicatorDefinition).all():
                _ind_id_cache[d.code] = d.id
        for code, attr in [("drawdown_max1", "dd_max1"), ("drawdown_max2", "dd_max2"), ("drawdown_max3", "dd_max3")]:
            ind_id = _ind_id_cache.get(code)
            if ind_id:
                row = (
                    s.query(IndicatorValue.value_num)
                    .filter(IndicatorValue.asset_id == asset_id, IndicatorValue.indicator_id == ind_id)
                    .order_by(IndicatorValue.date.desc())
                    .first()
                )
                if row and row[0] is not None:
                    if code == "drawdown_max1": dd_max1 = row[0]
                    elif code == "drawdown_max2": dd_max2 = row[0]
                    else: dd_max3 = row[0]
        dd_events = []  # se calcula bajo demanda en el gráfico
    else:
        running_max = df["close"].cummax()
        dd_series   = (df["close"] - running_max) / running_max * 100
        dd_current  = float(dd_series.iloc[-1])
        dd_sorted   = dd_series.nsmallest(3).values
        dd_max1 = float(dd_sorted[0]) if len(dd_sorted) > 0 else None
        dd_max2 = float(dd_sorted[1]) if len(dd_sorted) > 1 else None
        dd_max3 = float(dd_sorted[2]) if len(dd_sorted) > 2 else None
        dd_cfg    = _dd_cfg if _dd_cfg is not None else _get_drawdown_config()
        dd_events = _compute_dd_events(df, dd_cfg.min_depth_pct)

    # --- Preparar configs y resamplings (secuencial, necesario antes del bloque paralelo) ---
    cfg = _regime_cfg if _regime_cfg is not None else _get_regime_config()
    sl, st_pct, cb = cfg.slope_lookback, cfg.slope_threshold_pct, cfg.confirm_bars
    nb  = cfg.nascent_bars
    sm  = cfg.strong_slope_multiplier

    vcfg = _vol_cfg if _vol_cfg is not None else _get_volatility_config()
    _vol_args = dict(
        atr_period=vcfg.atr_period,
        confirm_bars=vcfg.confirm_bars,
        pct_low=vcfg.pct_low,
        pct_high=vcfg.pct_high,
        pct_extreme=vcfg.pct_extreme,
        dur_short_pct=vcfg.dur_short_pct,
        dur_long_pct=vcfg.dur_long_pct,
    )

    df_w_reg = _resample_ohlc(df, "W")
    df_m_reg = _resample_ohlc(df, "M")

    # --- Régimen, volatilidad y (en full) best_MA ---
    # En modo quick las 6 tareas son rápidas (numpy vectorizado ~10-50ms c/u):
    # el overhead de crear threads supera la ganancia; se corre en secuencia.
    # En modo full se agrega _find_best_ma (pesado) y vale la pena el pool.
    if quick:
        rz_d = _compute_regime_zones(df,       cfg.ema_period_d, sl, st_pct, cb, nb, sm)
        rz_w = _compute_regime_zones(df_w_reg, cfg.ema_period_w, sl, st_pct, cb, nb, sm)
        rz_m = _compute_regime_zones(df_m_reg, cfg.ema_period_m, sl, st_pct, cb, nb, sm)
        vz_d = _compute_vol_zones(df,       **_vol_args)
        vz_w = _compute_vol_zones(df_w_reg, **_vol_args)
        vz_m = _compute_vol_zones(df_m_reg, **_vol_args)
    else:
        with _TPE(max_workers=_CALC_WORKERS) as _pool:
            f_rz_d  = _pool.submit(_compute_regime_zones, df,       cfg.ema_period_d, sl, st_pct, cb, nb, sm)
            f_rz_w  = _pool.submit(_compute_regime_zones, df_w_reg, cfg.ema_period_w, sl, st_pct, cb, nb, sm)
            f_rz_m  = _pool.submit(_compute_regime_zones, df_m_reg, cfg.ema_period_m, sl, st_pct, cb, nb, sm)
            f_vz_d  = _pool.submit(_compute_vol_zones, df,       **_vol_args)
            f_vz_w  = _pool.submit(_compute_vol_zones, df_w_reg, **_vol_args)
            f_vz_m  = _pool.submit(_compute_vol_zones, df_m_reg, **_vol_args)
            f_sma_d = _pool.submit(_find_best_ma, df["close"],       df["high"],       df["low"],       "sma")
            f_ema_d = _pool.submit(_find_best_ma, df["close"],       df["high"],       df["low"],       "ema")
            f_sma_w = _pool.submit(_find_best_ma, df_w_reg["close"], df_w_reg["high"], df_w_reg["low"], "sma")
            f_ema_w = _pool.submit(_find_best_ma, df_w_reg["close"], df_w_reg["high"], df_w_reg["low"], "ema")
            f_sma_m = _pool.submit(_find_best_ma, df_m_reg["close"], df_m_reg["high"], df_m_reg["low"], "sma")
            f_ema_m = _pool.submit(_find_best_ma, df_m_reg["close"], df_m_reg["high"], df_m_reg["low"], "ema")
        rz_d = f_rz_d.result()
        rz_w = f_rz_w.result()
        rz_m = f_rz_m.result()
        vz_d = f_vz_d.result()
        vz_w = f_vz_w.result()
        vz_m = f_vz_m.result()

    if quick:
        best_sma_d = _prev_best.get("best_sma_d")
        best_ema_d = _prev_best.get("best_ema_d")
        best_sma_w = _prev_best.get("best_sma_w")
        best_ema_w = _prev_best.get("best_ema_w")
        best_sma_m = _prev_best.get("best_sma_m")
        best_ema_m = _prev_best.get("best_ema_m")
    else:
        best_sma_d, best_ema_d = f_sma_d.result(), f_ema_d.result()
        best_sma_w, best_ema_w = f_sma_w.result(), f_ema_w.result()
        best_sma_m, best_ema_m = f_sma_m.result(), f_ema_m.result()

    # --- Distancia en desv. estándar desde la SMA más respetada por timeframe ---
    dist_sma_d = _sma_zscore(df["close"], best_sma_d) if best_sma_d else None
    dist_sma_w = _sma_zscore(df_w_reg["close"], best_sma_w) if best_sma_w else None
    dist_sma_m = _sma_zscore(df_m_reg["close"], best_sma_m) if best_sma_m else None

    # --- RSI semanal y mensual ---
    rsi_w = _rsi(df_w_reg["close"])
    rsi_m = _rsi(df_m_reg["close"])

    # Para el resto de métricas usar solo los últimos 260 días
    df = df.tail(260).reset_index(drop=True)

    today = df.iloc[-1]["date"]
    last_close = float(df.iloc[-1]["close"])

    # --- Variaciones ---
    prev_close = float(df.iloc[-2]["close"]) if len(df) >= 2 else None

    month_start = date(today.year, today.month, 1)
    q_month = {1: 1, 2: 1, 3: 1, 4: 4, 5: 4, 6: 4, 7: 7, 8: 7, 9: 7, 10: 10, 11: 10, 12: 10}
    quarter_start = date(today.year, q_month[today.month], 1)
    year_start = date(today.year, 1, 1)
    w52_start = date(today.year - 1, today.month, today.day)

    ref_month = _closest_price_on_or_before(df, month_start)
    ref_quarter = _closest_price_on_or_before(df, quarter_start)
    ref_year = _closest_price_on_or_before(df, year_start)
    ref_52w = _closest_price_on_or_before(df, w52_start)

    # --- SMAs ---
    close = df["close"]
    sma20_series = close.rolling(20).mean()
    sma50_series = close.rolling(50).mean()
    sma200_series = close.rolling(200).mean()

    sma20 = float(sma20_series.iloc[-1]) if not pd.isna(sma20_series.iloc[-1]) else None
    sma50 = float(sma50_series.iloc[-1]) if not pd.isna(sma50_series.iloc[-1]) else None
    sma200 = float(sma200_series.iloc[-1]) if not pd.isna(sma200_series.iloc[-1]) else None

    # --- RSI diario (14) ---
    rsi = _rsi(close)

    def _vol_key(zones):
        if not zones:
            return None
        last = zones[-1]
        return f"{last['vol_regime']}_{last['dur_regime']}"

    def _atr_pct_last(zones):
        if not zones:
            return None
        return zones[-1].get("atr_pct")

    # Valores de indicadores computados
    ind_trend_d    = rz_d[-1]["regime_detail"] if rz_d else None
    ind_trend_w    = rz_w[-1]["regime_detail"] if rz_w else None
    ind_trend_m    = rz_m[-1]["regime_detail"] if rz_m else None
    ind_vol_d      = _vol_key(vz_d)
    ind_vol_w      = _vol_key(vz_w)
    ind_vol_m      = _vol_key(vz_m)
    ind_atr_pct_d  = _atr_pct_last(vz_d)
    ind_atr_pct_w  = _atr_pct_last(vz_w)
    ind_atr_pct_m  = _atr_pct_last(vz_m)
    ind_rsi_d      = round(rsi, 2)   if rsi   is not None else None
    ind_rsi_w      = round(rsi_w, 2) if rsi_w is not None else None
    ind_rsi_m      = round(rsi_m, 2) if rsi_m is not None else None

    sma20_v  = round(sma20,  4) if sma20  is not None else None
    sma50_v  = round(sma50,  4) if sma50  is not None else None
    sma200_v = round(sma200, 4) if sma200 is not None else None

    ind_resist_pct  = None
    ind_support_pct = None

    # --- S/R pivots ---
    try:
        sr = sr_service.compute_sr_from_df(df, cfg=_sr_cfg)
        if sr:
            ind_resist_pct  = sr["pivot_resist_pct"]
            ind_support_pct = sr["pivot_support_pct"]
    except Exception as exc:
        logger.warning("SR compute falló para asset_id=%d: %s", asset_id, exc)

    # --- Escribir indicator_values (serie temporal EAV + best_ma vigente) ---
    _write_indicator_values(s, asset_id, today, {
        "best_sma_d": best_sma_d,
        "best_ema_d": best_ema_d,
        "best_sma_w": best_sma_w,
        "best_ema_w": best_ema_w,
        "best_sma_m": best_sma_m,
        "best_ema_m": best_ema_m,
        "trend_daily":              ind_trend_d,
        "trend_weekly":             ind_trend_w,
        "trend_monthly":            ind_trend_m,
        "volatility_daily":         ind_vol_d,
        "volatility_weekly":        ind_vol_w,
        "volatility_monthly":       ind_vol_m,
        "atr_percentile_daily":     ind_atr_pct_d,
        "atr_percentile_weekly":    ind_atr_pct_w,
        "atr_percentile_monthly":   ind_atr_pct_m,
        "rsi_daily":                ind_rsi_d,
        "rsi_weekly":               ind_rsi_w,
        "rsi_monthly":              ind_rsi_m,
        "dist_sma20":               _pct_change(last_close, sma20),
        "dist_sma50":               _pct_change(last_close, sma50),
        "dist_sma200":              _pct_change(last_close, sma200),
        "dist_optimal_sma_daily":   dist_sma_d,
        "dist_optimal_sma_weekly":  dist_sma_w,
        "dist_optimal_sma_monthly": dist_sma_m,
        "drawdown_current":         round(dd_current, 2),
        "drawdown_max1":            round(dd_max1, 2) if dd_max1 is not None else None,
        "drawdown_max2":            round(dd_max2, 2) if dd_max2 is not None else None,
        "drawdown_max3":            round(dd_max3, 2) if dd_max3 is not None else None,
        "return_daily":             _pct_change(last_close, prev_close),
        "return_monthly":           _pct_change(last_close, ref_month),
        "return_quarterly":         _pct_change(last_close, ref_quarter),
        "return_yearly":            _pct_change(last_close, ref_year),
        "return_52w":               _pct_change(last_close, ref_52w),
        "resistance_pct":           ind_resist_pct,
        "support_pct":              ind_support_pct,
        "last_close":               last_close,
    })


def _snapshot_worker(asset_id: int, dd_cfg, regime_cfg, vol_cfg, sr_cfg) -> None:
    """Wrapper para ejecutar compute_and_save_snapshot en un thread del pool."""
    from app.database import Session
    try:
        compute_and_save_snapshot(
            asset_id,
            _dd_cfg=dd_cfg,
            _regime_cfg=regime_cfg,
            _vol_cfg=vol_cfg,
            _sr_cfg=sr_cfg,
        )
    finally:
        Session.remove()


def recompute_all_snapshots(progress_cb=None) -> dict:
    from concurrent.futures import as_completed
    s = get_session()
    asset_ids = [r[0] for r in s.query(Asset.id).all()]
    total = len(asset_ids)
    errors = []

    dd_cfg     = _get_drawdown_config()
    regime_cfg = _get_regime_config()
    vol_cfg    = _get_volatility_config()
    sr_cfg     = sr_service._get_sr_config()

    done = 0
    with _TPE(max_workers=_SNAPSHOT_WORKERS) as pool:
        futures = {
            pool.submit(_snapshot_worker, aid, dd_cfg, regime_cfg, vol_cfg, sr_cfg): aid
            for aid in asset_ids
        }
        for future in as_completed(futures):
            done += 1
            if progress_cb:
                progress_cb(done, total)
            aid = futures[future]
            try:
                future.result()
            except Exception as exc:
                logger.warning("Error snapshot activo id=%d: %s", aid, exc)
                errors.append(aid)

    return {"total": total, "errors": errors}


# ── Funciones públicas para cálculo lazy en el gráfico ───────────────────────

def get_regime_zones_for_chart(df: "pd.DataFrame", cfg=None) -> dict:
    """Devuelve {"D": [...], "W": [...], "M": [...]} con zonas de régimen."""
    if cfg is None:
        cfg = _get_regime_config()
    sl, st_pct, cb = cfg.slope_lookback, cfg.slope_threshold_pct, cfg.confirm_bars
    nb, sm = cfg.nascent_bars, cfg.strong_slope_multiplier
    df_w = _resample_ohlc(df, "W")
    df_m = _resample_ohlc(df, "M")
    return {
        "D": _compute_regime_zones(df,   cfg.ema_period_d, sl, st_pct, cb, nb, sm),
        "W": _compute_regime_zones(df_w, cfg.ema_period_w, sl, st_pct, cb, nb, sm),
        "M": _compute_regime_zones(df_m, cfg.ema_period_m, sl, st_pct, cb, nb, sm),
    }


def get_vol_zones_for_chart(df: "pd.DataFrame", cfg=None) -> dict:
    """Devuelve {"D": [...], "W": [...], "M": [...]} con zonas de volatilidad."""
    if cfg is None:
        cfg = _get_volatility_config()
    vol_args = dict(
        atr_period=cfg.atr_period,
        confirm_bars=cfg.confirm_bars,
        pct_low=cfg.pct_low,
        pct_high=cfg.pct_high,
        pct_extreme=cfg.pct_extreme,
        dur_short_pct=cfg.dur_short_pct,
        dur_long_pct=cfg.dur_long_pct,
    )
    df_w = _resample_ohlc(df, "W")
    df_m = _resample_ohlc(df, "M")
    return {
        "D": _compute_vol_zones(df,   **vol_args),
        "W": _compute_vol_zones(df_w, **vol_args),
        "M": _compute_vol_zones(df_m, **vol_args),
    }


def get_dd_events_for_chart(df: "pd.DataFrame", cfg=None) -> list:
    """Devuelve lista de eventos de drawdown significativos."""
    if cfg is None:
        cfg = _get_drawdown_config()
    return _compute_dd_events(df, cfg.min_depth_pct)


def _fmt_dd_top3_from_events(dd_events_json: str | None) -> str:
    if not dd_events_json:
        return ""
    try:
        events = json.loads(dd_events_json)
    except Exception:
        return ""
    sorted_events = sorted(events, key=lambda e: e.get("depth", 0))
    top3 = sorted_events[:3]
    return " / ".join(f"{e['depth']:.1f}%" for e in top3)


def get_market_map_data() -> dict:
    """
    Retorna datos para el Mapa de Mercado calculando scores de tendencia
    por grupo a partir de indicator_values.
    {
      "sector": {id: {"name": str, "n": int, "d": float, "w": float, "m": float}},
      "industry": {...},
      ...
    }
    """
    from collections import defaultdict

    s = get_session()

    trend_codes = ("trend_daily", "trend_weekly", "trend_monthly")
    defs = {
        d.code: d.id
        for d in s.query(IndicatorDefinition).filter(
            IndicatorDefinition.code.in_(trend_codes)
        ).all()
    }
    if not defs:
        return {}

    trend_ids = list(defs.values())

    # Subquery: última fecha por (asset_id, indicator_id)
    max_date_sq = (
        s.query(
            IndicatorValue.asset_id,
            IndicatorValue.indicator_id,
            func.max(IndicatorValue.date).label("max_date"),
        )
        .filter(IndicatorValue.indicator_id.in_(trend_ids))
        .group_by(IndicatorValue.asset_id, IndicatorValue.indicator_id)
        .subquery()
    )

    iv_rows = (
        s.query(IndicatorValue.asset_id, IndicatorDefinition.code, IndicatorValue.value_str)
        .join(IndicatorDefinition, IndicatorValue.indicator_id == IndicatorDefinition.id)
        .join(max_date_sq, and_(
            IndicatorValue.asset_id    == max_date_sq.c.asset_id,
            IndicatorValue.indicator_id == max_date_sq.c.indicator_id,
            IndicatorValue.date         == max_date_sq.c.max_date,
        ))
        .all()
    )

    # trends[(asset_id, code)] = regime_str
    trends: dict[tuple, str | None] = {
        (asset_id, code): value_str
        for asset_id, code, value_str in iv_rows
    }

    all_assets = (
        s.query(Asset)
        .options(
            joinedload(Asset.sector),
            joinedload(Asset.industry),
            joinedload(Asset.country),
            joinedload(Asset.instrument_type),
            joinedload(Asset.market),
        )
        .all()
    )

    _dim_key_map = {
        "sector_id":          ("sector",   lambda a: a.sector.name           if a.sector           else None),
        "industry_id":        ("industry", lambda a: a.industry.name         if a.industry         else None),
        "country_id":         ("country",  lambda a: a.country.name          if a.country          else None),
        "instrument_type_id": ("itype",    lambda a: a.instrument_type.name  if a.instrument_type  else None),
        "market_id":          ("market",   lambda a: a.market.name           if a.market           else None),
    }
    _tf_code = {"d": "trend_daily", "w": "trend_weekly", "m": "trend_monthly"}

    score_buckets: dict = defaultdict(list)
    counts: dict = defaultdict(lambda: {"n": 0})
    names: dict = {}

    for asset in all_assets:
        for dim_attr, (dim_key, name_fn) in _dim_key_map.items():
            gid = getattr(asset, dim_attr)
            if gid is None:
                continue
            key = (dim_key, gid)
            counts[key]["n"] += 1
            if key not in names:
                names[key] = name_fn(asset) or f"#{gid}"
            for tf, code in _tf_code.items():
                regime = trends.get((asset.id, code))
                score = _REGIME_SCORE.get(regime or "")
                if score is not None:
                    score_buckets[(dim_attr, gid, tf)].append(score)

    result: dict = {dk: {} for dk, _ in _dim_key_map.values()}
    seen: dict = {dk: set() for dk, _ in _dim_key_map.values()}

    for asset in all_assets:
        for dim_attr, (dim_key, _) in _dim_key_map.items():
            gid = getattr(asset, dim_attr)
            if gid is None or gid in seen[dim_key]:
                continue
            seen[dim_key].add(gid)
            key = (dim_key, gid)
            bd = score_buckets.get((dim_attr, gid, "d"), [])
            bw = score_buckets.get((dim_attr, gid, "w"), [])
            bm = score_buckets.get((dim_attr, gid, "m"), [])
            result[dim_key][gid] = {
                "name": names.get(key, f"#{gid}"),
                "n":    counts[key]["n"],
                "d":    round(sum(bd) / len(bd)) if bd else None,
                "w":    round(sum(bw) / len(bw)) if bw else None,
                "m":    round(sum(bm) / len(bm)) if bm else None,
            }

    return result
