"""
CLI para app.services.verification_service (run_verification /
run_fund_verification) — ver ese módulo para el detalle de cómo funciona
la comparación (delta vs. recálculo fresco) y los chequeos de cordura
(valores fuera de rango o categorías desconocidas). Solo lee de la base,
nunca escribe.

Uso (en el Codespace, con la BD levantada):
    python scripts/verify_delta_correctness.py                          # indicadores técnicos, 30 activos al azar
    python scripts/verify_delta_correctness.py --sample 100
    python scripts/verify_delta_correctness.py --codes trend_daily,relative_strength_52w
    python scripts/verify_delta_correctness.py --tickers AAPL,GGAL.BA
    python scripts/verify_delta_correctness.py --domain fundamentals    # ratios fundamentales en vez de indicadores

También disponible como panel web en /admin/verify (mismo código,
parámetros elegibles por pantalla, incluye la suite de pytest).
"""
import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from app.services.verification_service import run_fund_verification, run_verification


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--domain", choices=["indicators", "fundamentals"], default="indicators",
                        help="indicadores técnicos (default) o ratios fundamentales")
    parser.add_argument("--codes", default=None,
                        help="códigos separados por coma (default: todos los del dominio elegido)")
    parser.add_argument("--sample", type=int, default=30,
                        help="cantidad de activos al azar (default: 30, ignorado si se pasa --tickers)")
    parser.add_argument("--tickers", default=None,
                        help="tickers puntuales separados por coma, en vez de muestra al azar")
    parser.add_argument("--max-print", type=int, default=10,
                        help="diferencias a imprimir por (código, activo) antes de resumir")
    args = parser.parse_args()

    codes   = args.codes.split(",") if args.codes else None
    tickers = [t.strip() for t in args.tickers.split(",")] if args.tickers else None

    def _progress(cur, tot, label=""):
        if cur % 10 == 0 or cur == tot:
            print(f"  ... {cur}/{tot}  {label}", file=sys.stderr)

    run_fn = run_verification if args.domain == "indicators" else run_fund_verification
    result = run_fn(codes=codes, sample=args.sample, tickers=tickers, progress_cb=_progress)

    if result["missing_tickers"]:
        print(f"(aviso: tickers no encontrados, salteados: {', '.join(result['missing_tickers'])})")

    def _print_summary(combos):
        # un renglón por activo (no por código/activo): cuántos códigos y
        # diferencias tiene, ordenado de más a menos, para ver de un
        # vistazo qué activos concentran el problema antes del detalle.
        by_asset: dict = {}
        for r in combos:
            key = (r["asset_id"], r["ticker"])
            agg = by_asset.setdefault(key, {"codes": 0, "diffs": 0})
            agg["codes"] += 1
            agg["diffs"] += len(r["diffs"])
        print(f"Resumen: {len(by_asset)} activo(s) afectados:")
        for (asset_id, ticker), agg in sorted(by_asset.items(), key=lambda kv: -kv[1]["diffs"]):
            print(f"  {ticker} (id={asset_id}): {agg['codes']} código(s), "
                  f"{agg['diffs']} diferencia(s)")

    def _print_section(title, combos):
        if not combos:
            return
        print(f"\n{'=' * 70}\n{title}\n{'=' * 70}")
        _print_summary(combos)
        for r in combos:
            print(f"\n[DIFF] {r['code']} / {r['ticker']} (id={r['asset_id']}): "
                  f"{len(r['diffs'])} diferencias")
            for d, kind, stored, fresh, _cat in r["diffs"][:args.max_print]:
                print(f"    {d}  {kind}  guardado={stored!r}  recalculado={fresh!r}")
            if len(r["diffs"]) > args.max_print:
                print(f"    ... y {len(r['diffs']) - args.max_print} más")

    # "calc": guardado != recalculado — sospecha real de bug de caché/delta.
    # "sanity": guardado == recalculado pero el valor no tiene sentido — no
    # es un bug de esta herramienta, es un dato de entrada raro (o una
    # fórmula con un caso límite, pero no algo que el delta cachee mal).
    calc    = [{**r, "diffs": d} for r in result["results"]
               if (d := [x for x in r["diffs"] if x[4] == "calc"])]
    sanity  = [{**r, "diffs": d} for r in result["results"]
               if (d := [x for x in r["diffs"] if x[4] == "sanity"])]
    n_calc   = sum(len(r["diffs"]) for r in calc)
    n_sanity = sum(len(r["diffs"]) for r in sanity)

    _print_section("DISCREPANCIAS DE CÁLCULO (guardado != recalculado — posible bug)", calc)
    _print_section("POSIBLES ERRORES DE DATOS DE ORIGEN "
                   "(guardado == recalculado, fuera de rango — no es un bug de caché)", sanity)

    print(f"\n{'=' * 70}")
    if n_calc == 0 and n_sanity == 0:
        print(f"OK — sin diferencias en {len(result['codes'])} códigos x "
              f"{len(result['asset_ids'])} activos ({result['combos']} combinaciones).")
    else:
        print(f"{n_calc} discrepancias de cálculo + {n_sanity} posibles errores de "
              f"datos de origen, en {len(result['results'])} combinaciones código/activo "
              f"— revisar el detalle arriba.")


if __name__ == "__main__":
    main()
