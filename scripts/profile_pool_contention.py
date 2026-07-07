"""
Mide el costo real, SECUENCIAL y de un solo hilo (sin ThreadPoolExecutor), de
correr un indicador sobre TODOS los activos reales — a diferencia de
profile_vol_zones.py (que repite UN activo N veces para aislar el costo por
rep), este script suma el costo real sobre el universo completo, para poder
compararlo directo contra el tiempo de pared que reporta el panel del Centro
de Datos (ver columna "workers" del log de update_indicator_history).

Si el tiempo secuencial de un código (p.ej. volatility_daily) es mucho menor
que su tiempo de pared en el pool concurrente (p.ej. 53s), la diferencia es
contención de GIL entre los workers (todos corriendo Python puro/pandas en el
mismo intérprete) — no falta de vectorización ni cómputo genuino. Si en cambio
el secuencial ya es parecido al tiempo de pared, el cuello de botella real es
otro (I/O, commits, overhead de scheduling).

Uso (en el Codespace, con la BD levantada):
    python scripts/profile_pool_contention.py                 # códigos por defecto (los mas pesados del ultimo delta)
    python scripts/profile_pool_contention.py volatility_daily trend_daily rsi_daily
"""
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from app.database import get_session
from app.services.technical_service import (
    _BACKFILL_FNS, _MIN_ROWS, _get_regime_config, _get_volatility_config,
    _load_all_prices, _load_best_sma_cache, _resample_ohlc,
)

# Los 3 mas pesados del ultimo delta real (561 activos): 53s/30s/30s de pared
_DEFAULT_CODES = ["volatility_daily", "trend_daily", "volatility_weekly"]


def main():
    codes = sys.argv[1:] or _DEFAULT_CODES
    for code in codes:
        if code not in _BACKFILL_FNS:
            raise SystemExit(f"Código desconocido o sin función de backfill: {code!r}")

    s = get_session()
    print("Cargando precios en memoria...")
    price_cache = _load_all_prices(s)
    n_assets = len(price_cache)
    print(f"{n_assets} activos cargados")

    print("Precalculando resamples semanales/mensuales...")
    df_w_cache = {aid: _resample_ohlc(df, "W") for aid, df in price_cache.items()}
    df_m_cache = {aid: _resample_ohlc(df, "M") for aid, df in price_cache.items()}
    best_sma_cache = _load_best_sma_cache(s)
    regime_cfg = _get_regime_config()
    vol_cfg = _get_volatility_config()

    for code in codes:
        compute_fn = _BACKFILL_FNS[code]
        n_done = 0
        t0 = time.perf_counter()
        for asset_id, df in price_cache.items():
            if len(df) < _MIN_ROWS:
                continue
            compute_fn(
                df=df, df_w=df_w_cache[asset_id], df_m=df_m_cache[asset_id],
                regime_cfg=regime_cfg, vol_cfg=vol_cfg,
                session=s, asset_id=asset_id,
                price_cache=price_cache, best_sma_cache=best_sma_cache,
            )
            n_done += 1
        elapsed = time.perf_counter() - t0
        print(f"\n{'=' * 70}\n{code}: {elapsed:.2f}s secuencial total "
              f"({n_done} activos, {elapsed / n_done * 1000:.1f}ms/activo)\n{'=' * 70}")


if __name__ == "__main__":
    main()
