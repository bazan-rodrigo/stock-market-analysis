"""
Mide cuánto tarda un backtest de cuantiles contra la base REAL, desglosado por
fase, para saber si `run_backtest_preview` (la herramienta MCP) entra en el
tiempo que un cliente de IA está dispuesto a esperar.

Es de SOLO LECTURA: no escribe nada, no persiste el run y no toma el `run_lock`.
Igual corre contra producción, así que lee bastante — no lo dispares en medio de
una corrida del Centro de Datos.

Qué desglosa (las tres fases de backtest_service._computar):

  1. leer_scores        — los scores de la estrategia en el período
  2. _retornos_forward  — precios + retornos forward. **La parte cara.**
  3. _agregar           — cross-sections por fecha × horizonte y agregados

La pregunta que contesta: **¿acotar el período sirve?** Hoy la query de precios
de la fase 2 NO filtra por fecha —carga la historia completa de cada activo
aunque pidas un año—, así que `date_from`/`date_to` recortan las fases 1 y 3
pero no la 2. Si la fase 2 domina, acotar el período no compra casi nada y el
arreglo es filtrar los precios; si no domina, no hay nada que optimizar.

    python scripts/profile_backtest_preview.py <strategy_id> [--desde AAAA-MM-DD]

Sin --desde corre sobre toda la historia (el peor caso, que es justo el que
importa medir). Con --desde se compara contra esa misma corrida completa.
"""
import argparse
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

# La consola de Windows es cp1252 y revienta con UnicodeEncodeError ante
# cualquier acento o flecha. Se fuerza UTF-8 con `errors="replace"` para que,
# si igual no puede, salga un signo raro y no una traza: un script de medición
# que se cae por el formato del informe no mide nada.
for _flujo in (sys.stdout, sys.stderr):
    try:
        _flujo.reconfigure(encoding="utf-8", errors="replace")
    except (AttributeError, ValueError):
        pass


def _fmt(seg: float) -> str:
    return f"{seg * 1000:8.0f} ms" if seg < 1 else f"{seg:8.2f} s "


def medir(strategy_id: int, desde: str | None, hasta: str | None,
          horizontes: list[int]) -> dict:
    from app.database import Session, get_session
    from app.services import backtest_service as bs

    cfg = bs.normalize_config({"horizons": horizontes,
                               "date_from": desde, "date_to": hasta})
    s = get_session()

    t0 = time.perf_counter()
    scores = bs.leer_scores(s, strategy_id, cfg)
    t_scores = time.perf_counter() - t0

    t0 = time.perf_counter()
    fwd = bs._retornos_forward(s, scores, cfg, None)
    t_precios = time.perf_counter() - t0

    t0 = time.perf_counter()
    datos = bs._agregar(bs._por_fecha(scores, fwd, cfg), cfg, None)
    t_agregar = time.perf_counter() - t0

    Session.remove()
    total = t_scores + t_precios + t_agregar
    return {
        "total": total,
        "fases": [("leer_scores", t_scores), ("_retornos_forward", t_precios),
                  ("_agregar", t_agregar)],
        "filas_score": len(scores),
        "activos": len(fwd),
        "fechas": datos["n_dates"],
        "rango": f"{datos['date_from']} .. {datos['date_to']}",
    }


def _informe(titulo: str, r: dict) -> None:
    print(f"\n── {titulo} ──")
    print(f"   {r['filas_score']:,} scores · {r['activos']} activos · "
          f"{r['fechas']} fechas · {r['rango']}")
    for nombre, seg in r["fases"]:
        pct = (seg / r["total"] * 100) if r["total"] else 0
        print(f"   {nombre:<20} {_fmt(seg)}  {pct:5.1f}%")
    print(f"   {'TOTAL':<20} {_fmt(r['total'])}")


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("strategy_id", type=int)
    p.add_argument("--desde", help="AAAA-MM-DD para la corrida acotada")
    p.add_argument("--hasta", help="AAAA-MM-DD")
    p.add_argument("--horizontes", default="1,5,20,60")
    args = p.parse_args()

    horizontes = [int(h) for h in args.horizontes.split(",") if h.strip()]

    print(f"Estrategia {args.strategy_id} · horizontes {horizontes}")
    completa = medir(args.strategy_id, None, None, horizontes)
    _informe("HISTORIA COMPLETA", completa)

    if args.desde:
        acotada = medir(args.strategy_id, args.desde, args.hasta, horizontes)
        _informe(f"ACOTADA desde {args.desde}", acotada)

        ahorro = 1 - (acotada["total"] / completa["total"]) if completa["total"] else 0
        precios_c = dict(completa["fases"])["_retornos_forward"]
        precios_a = dict(acotada["fases"])["_retornos_forward"]
        print(f"\n── ¿SIRVE ACOTAR EL PERÍODO? ──")
        print(f"   total:            −{ahorro * 100:.0f}%")
        print(f"   solo los precios: −{(1 - precios_a / precios_c) * 100 if precios_c else 0:.0f}%"
              f"   (si es ~0%, la query de precios no filtra por fecha y ahí"
              f" está el arreglo)")

    print(f"\nUn cliente de IA suele cortar entre 30 y 60 s. "
          f"Peor caso medido: {_fmt(completa['total']).strip()}")


if __name__ == "__main__":
    main()
