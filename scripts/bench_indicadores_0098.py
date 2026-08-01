"""
Cuánto encarece el cómputo del delta agregar los indicadores de la 0098
(price_position_52w, adx_daily/weekly/monthly, rvol_daily).

QUÉ MIDE Y QUÉ NO. Mide el CÓMPUTO por activo de cada función de backfill:
las series de pandas, que es lo que el ProcessPool paraleliza y lo único que
los indicadores nuevos agregan al trabajo de CPU. NO mide el I/O de traer la
columna `volume` desde la base, ni la escritura de las 5 columnas nuevas, ni
el arranque del pool. Para eso hace falta la base real y va aparte
(profile_indicator_delta_real.py, en Railway).

POR QUÉ SE PUEDE CORRER ACÁ. Las funciones _bf_* son lógica pura sobre
DataFrames: no tocan la base. La PC de desarrollo no tiene base ni yfinance,
pero sí puede correr esto — y las CONCLUSIONES RELATIVAS (qué fracción del
cómputo agregan los nuevos sobre los que ya estaban) se trasladan, aunque los
milisegundos absolutos de esta máquina no sean los de Railway.

LO QUE ESTE NÚMERO NO AUTORIZA A CONCLUIR. Está anotado en
project_scaling_target.md y ya costó tres estimaciones malas: **las partes
aisladas no suman el todo** (subestimaron 2.8x la última vez). Medir los _bf_*
uno por uno NO da el costo del delta completo, que incluye prefetch, dict
compare, escritura y commits. Por eso el script reporta la RELACIÓN
nuevos/existentes y no una proyección a 10.000 activos: la relación es lo que
sobrevive al cambio de entorno.

CONTROL DE DERIVA: el primer código medido se repite al final. Si las dos
mediciones difieren mucho, la máquina estuvo ruidosa y la tanda no sirve.

SOLO LECTURA, SIN BASE: usa un sqlite descartable (igual que tests/conftest)
solo para que las configs de régimen y volatilidad se creen con sus defaults,
y datos de precios SINTÉTICOS. No se conecta a ninguna base real.

Uso:
    python scripts/bench_indicadores_0098.py              # 40 activos x 5000 barras
    python scripts/bench_indicadores_0098.py 80 8000      # activos, barras
"""
import os
import sys
import tempfile
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

# Stub sqlite ANTES de importar app (mismo patrón que tests/conftest.py): las
# configs de régimen/volatilidad se autocrean con sus defaults al pedirlas.
# En el directorio temporal del sistema, NO en el repo: en Windows sqlite
# retiene el archivo aunque se llame a dispose(), así que el unlink del final
# falla y el stub queda tirado en la raíz del working tree.
_STUB = Path(tempfile.gettempdir()) / f"bench-ind-0098-{os.getpid()}.db"
os.environ["DATABASE_URL"] = f"sqlite:///{_STUB}"

import numpy as np                                            # noqa: E402
import pandas as pd                                           # noqa: E402

from app.database import Base, engine                         # noqa: E402
from app.services.technical_service import (                  # noqa: E402
    _BACKFILL_FNS, _get_regime_config, _get_volatility_config, _resample_ohlc,
)

# Los cinco de la migración 0098.
NUEVOS = ["price_position_52w", "adx_daily", "adx_weekly", "adx_monthly",
          "rvol_daily"]

# relative_strength_52w queda afuera del baseline: su costo depende de un
# SEGUNDO activo (el benchmark) y de la base, así que en este banco sintético
# mediría su camino corto —benchmark ausente— y ensuciaría la comparación.
EXCLUIDOS = ["relative_strength_52w"]

REPETICIONES = 3   # por código; se toma el MÍNIMO (menos sensible al ruido)


def _fake_asset(n_bars: int, seed: int) -> pd.DataFrame:
    """OHLCV sintético con forma realista: random walk geométrico, rango
    intradiario proporcional al precio y volumen lognormal (asimétrico, como
    el real). Días hábiles, para que el resample semanal/mensual dé la misma
    cantidad de barras que en datos verdaderos."""
    rng    = np.random.default_rng(seed)
    ret    = rng.normal(0.0005, 0.02, n_bars)
    close  = 100.0 * np.exp(np.cumsum(ret))
    intra  = np.abs(rng.normal(0.0, 0.012, n_bars))
    dates  = [d.date() for d in pd.bdate_range("2000-01-03", periods=n_bars)]
    return pd.DataFrame({
        "date":   dates,
        "close":  close,
        "high":   close * (1 + intra),
        "low":    close * (1 - intra),
        # float32: es como lo cargan _load_all_prices/_load_prices_for_assets.
        "volume": rng.lognormal(13.0, 0.7, n_bars).astype("float32"),
    })


def _time_code(code, fn, assets, regime_cfg, vol_cfg):
    """ms por activo del código, y cuántos valores no nulos produjo (sanity:
    un indicador que devuelve todo None mediría 'rapidísimo' sin hacer nada)."""
    mejor, no_nulos = float("inf"), 0
    for _ in range(REPETICIONES):
        t0 = time.perf_counter()
        vivos = 0
        for df, df_w, df_m in assets:
            out = fn(df=df, df_w=df_w, df_m=df_m, regime_cfg=regime_cfg,
                     vol_cfg=vol_cfg, session=None, asset_id=1,
                     price_cache=None, best_sma_cache={})
            vals = list(out) if not isinstance(out, pd.Series) else list(out.to_numpy())
            vivos += sum(1 for v in vals if v is not None and v == v)
        elapsed = (time.perf_counter() - t0) * 1000.0 / len(assets)
        mejor, no_nulos = min(mejor, elapsed), vivos
    return mejor, no_nulos


def main() -> None:
    n_assets = int(sys.argv[1]) if len(sys.argv) > 1 else 40
    n_bars   = int(sys.argv[2]) if len(sys.argv) > 2 else 5000

    Base.metadata.create_all(engine)
    regime_cfg, vol_cfg = _get_regime_config(), _get_volatility_config()

    print(f"Generando {n_assets} activos x {n_bars} barras...")
    assets = []
    for i in range(n_assets):
        df = _fake_asset(n_bars, seed=1000 + i)
        assets.append((df, _resample_ohlc(df, "W"), _resample_ohlc(df, "M")))

    # Peso de la columna nueva en el DataFrame que viaja al ProcessPool.
    df0     = assets[0][0]
    mem_tot = df0.memory_usage(deep=True).sum()
    mem_vol = df0.memory_usage(deep=True)["volume"]
    print(f"\nMemoria del df de un activo: {mem_tot/1024:.0f} KB "
          f"| columna volume (float32): {mem_vol/1024:.0f} KB "
          f"({mem_vol/mem_tot*100:.1f}%)")
    print(f"  a 10.000 activos de {n_bars} barras, la columna volume son "
          f"{mem_vol*10_000/1024/1024:.0f} MB "
          f"(en int64 serían {mem_vol*2*10_000/1024/1024:.0f} MB)")

    codigos = [c for c in _BACKFILL_FNS if c not in EXCLUIDOS]
    base    = [c for c in codigos if c not in NUEVOS]
    nuevos  = [c for c in codigos if c in NUEVOS]

    # CALENTAMIENTO: la primerísima medición paga el costo de calentar pandas
    # (imports diferidos, cachés internos) y sale inflada sin que eso tenga
    # nada que ver con el código medido — con el control de deriva al final
    # comparándose contra ella, la tanda entera se declaraba no confiable.
    for code in (base[0], nuevos[0]):
        _time_code(code, _BACKFILL_FNS[code], assets[:2], regime_cfg, vol_cfg)

    print(f"\n{'código':<28} {'ms/activo':>10} {'no-nulos':>10}")
    print("-" * 50)
    medidas, deriva_code = {}, base[0]
    deriva_1, _ = _time_code(deriva_code, _BACKFILL_FNS[deriva_code], assets,
                             regime_cfg, vol_cfg)

    for grupo, titulo in ((base, "YA ESTABAN"), (nuevos, "NUEVOS (0098)")):
        print(f"\n-- {titulo} --")
        for code in grupo:
            ms, nn = _time_code(code, _BACKFILL_FNS[code], assets,
                                regime_cfg, vol_cfg)
            medidas[code] = ms
            print(f"{code:<28} {ms:>10.3f} {nn:>10,}")

    deriva_2, _ = _time_code(deriva_code, _BACKFILL_FNS[deriva_code], assets,
                             regime_cfg, vol_cfg)
    t_base   = sum(medidas[c] for c in base)
    t_nuevos = sum(medidas[c] for c in nuevos)

    print("\n" + "=" * 50)
    print(f"Existentes ({len(base)} códigos): {t_base:>8.2f} ms/activo")
    print(f"Nuevos     ({len(nuevos)} códigos): {t_nuevos:>8.2f} ms/activo")
    print(f"El delta de cómputo se encarece {t_nuevos/t_base*100:.1f}% "
          f"(x{1 + t_nuevos/t_base:.3f})")
    print("  ES UNA COTA SUPERIOR, no el número exacto: el baseline de este")
    print("  banco está SUBESTIMADO por dos motivos, los dos a su favor —")
    print("  dist_optimal_sma_* cae a su camino corto (sin best_sma_* no")
    print("  produce ningún valor, ver la columna no-nulos) y")
    print("  relative_strength_52w está excluido. Con esos tres pesando lo")
    print("  que pesan de verdad, el porcentaje real es algo MENOR.")

    desvio = abs(deriva_2 - deriva_1) / max(deriva_1, 1e-9) * 100
    print(f"\nControl de deriva ({deriva_code}): {deriva_1:.3f} -> "
          f"{deriva_2:.3f} ms ({desvio:.1f}%)")
    if desvio > 15:
        print("  ATENCIÓN: la máquina estuvo ruidosa, esta tanda NO es confiable.")

    try:
        engine.dispose()
        _STUB.unlink(missing_ok=True)
    except OSError:
        pass


if __name__ == "__main__":
    main()
