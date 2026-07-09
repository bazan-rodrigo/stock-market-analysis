"""
CLI para app.services.verification_service.run_verification — ver ese
módulo para el detalle de cómo funciona la comparación (delta vs.
recálculo fresco). Solo lee de la base, nunca escribe.

Uso (en el Codespace, con la BD levantada):
    python scripts/verify_delta_correctness.py                    # 30 activos al azar, todos los códigos
    python scripts/verify_delta_correctness.py --sample 100
    python scripts/verify_delta_correctness.py --codes trend_daily,relative_strength_52w
    python scripts/verify_delta_correctness.py --tickers AAPL,GGAL.BA

También disponible como panel web en /admin/verify (mismo código,
parámetros elegibles por pantalla).
"""
import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from app.services.verification_service import run_verification


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--codes", default=None,
                        help="códigos separados por coma (default: todos los de _DELTA_TAIL_MODE)")
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

    result = run_verification(codes=codes, sample=args.sample, tickers=tickers,
                              progress_cb=_progress)

    if result["missing_tickers"]:
        print(f"(aviso: tickers no encontrados, salteados: {', '.join(result['missing_tickers'])})")

    total_diffs = 0
    for r in result["results"]:
        total_diffs += len(r["diffs"])
        print(f"\n[DIFF] {r['code']} / {r['ticker']} (id={r['asset_id']}): {len(r['diffs'])} diferencias")
        for d, kind, stored, fresh in r["diffs"][:args.max_print]:
            print(f"    {d}  {kind}  guardado={stored!r}  recalculado={fresh!r}")
        if len(r["diffs"]) > args.max_print:
            print(f"    ... y {len(r['diffs']) - args.max_print} más")

    print(f"\n{'=' * 70}")
    if total_diffs == 0:
        print(f"OK — sin diferencias en {len(result['codes'])} códigos x "
              f"{len(result['asset_ids'])} activos ({result['combos']} combinaciones).")
    else:
        print(f"ENCONTRADAS {total_diffs} diferencias en {len(result['results'])} "
              f"combinaciones código/activo — revisar el detalle arriba.")


if __name__ == "__main__":
    main()
