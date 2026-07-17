"""
Comparador de paridad entre dos motores (fase 5 del soporte dual —
docs/notes/design_postgresql_dual.md).

Compara el RESULTADO del pipeline (indicadores, señales, estrategias,
group_scores) entre dos bases pobladas con el mismo dataset — típicamente
MariaDB y PostgreSQL en el Codespace con DB_ENGINE=both, después de correr
"Recalcular completo" contra cada una.

Uso:
    python scripts/compare_engines.py \
        "mysql+mysqldb://root@127.0.0.1:3306/stock_analysis?charset=utf8mb4" \
        "postgresql+psycopg://postgres:postgres@127.0.0.1:5432/stock_analysis" \
        [--tolerance 1e-6] [--top 20]

Qué compara (todo por SQL agregado, sin traer millones de filas):
  1. Conteo de filas por tabla (fijas de resultados + dinámicas comunes).
  2. Series numéricas (ind_*, sig_*, strat_res_*, group_*): agregados por
     fecha (COUNT + SUM redondeada) con tolerancia — los motores almacenan
     float con distinta precisión (FLOAT de 4 bytes en MySQL vs double
     precision en PG), la igualdad exacta no aplica.
  3. Ranking de cada estrategia en la última fecha común: el ORDEN de los
     asset_id (score DESC, NULLs al final) debe coincidir — es el output
     de negocio; un empate resuelto distinto se reporta como WARN si los
     scores difieren menos que la tolerancia.

Sale con código 0 si todo coincide, 1 si hay diferencias.
"""
import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import sqlalchemy as sa

# Tablas fijas de resultados del pipeline (las de catálogo/definiciones no
# se comparan: se importan idénticas por fuera del pipeline)
_FIXED_TABLES = (
    "prices", "current_indicator_values", "ind_asset_meta",
    "group_scores", "group_signal_value", "signal_eval_log",
)


def _dyn_tables(engine) -> list[str]:
    insp = sa.inspect(engine)
    return sorted(
        n for n in insp.get_table_names()
        if (n.startswith("ind_") and n != "ind_asset_meta")
        or n.startswith("sig_") or n.startswith("strat_res_")
    )


def _count(conn, table: str) -> int:
    return conn.execute(sa.text(f"SELECT COUNT(*) FROM {table}")).scalar() or 0


def _date_aggregates(conn, table: str, value_col: str) -> dict:
    """{date: (count, sum)} — solo filas con valor numérico no nulo."""
    rows = conn.execute(sa.text(
        f"SELECT date, COUNT({value_col}), SUM({value_col}) "
        f"FROM {table} GROUP BY date")).fetchall()
    return {str(r[0]): (int(r[1]), float(r[2]) if r[2] is not None else 0.0)
            for r in rows}


def _ranking(conn, table: str, target_date) -> list[tuple[int, float | None]]:
    rows = conn.execute(sa.text(
        f"SELECT asset_id, score FROM {table} WHERE date = :d "
        f"ORDER BY (score IS NULL), score DESC, asset_id"),
        {"d": target_date}).fetchall()
    return [(int(a), float(s) if s is not None else None) for a, s in rows]


def _value_col(engine, table: str) -> str | None:
    cols = {c["name"] for c in sa.inspect(engine).get_columns(table)}
    for cand in ("value", "score"):
        if cand in cols:
            return cand
    return None


def compare_date_aggregates(agg_a: dict, agg_b: dict, tolerance: float):
    """Devuelve lista de problemas: fechas faltantes, counts distintos o
    sumas fuera de tolerancia (relativa sobre max(1, |suma|))."""
    problems = []
    for d in sorted(set(agg_a) | set(agg_b)):
        if d not in agg_a or d not in agg_b:
            problems.append(f"fecha {d} solo en {'B' if d not in agg_a else 'A'}")
            continue
        (ca, sa_), (cb, sb) = agg_a[d], agg_b[d]
        if ca != cb:
            problems.append(f"fecha {d}: count {ca} vs {cb}")
        elif abs(sa_ - sb) > tolerance * max(1.0, abs(sa_)):
            problems.append(f"fecha {d}: sum {sa_!r} vs {sb!r}")
    return problems


def compare_rankings(rank_a: list, rank_b: list, tolerance: float):
    """Compara el ORDEN de asset_id. Un swap entre scores que difieren
    menos que la tolerancia (empate por precisión de float) es WARN, no
    error. Devuelve (errores, warnings)."""
    errors, warnings = [], []
    if len(rank_a) != len(rank_b):
        return [f"largo distinto: {len(rank_a)} vs {len(rank_b)}"], []
    score_a = dict(rank_a)
    score_b = dict(rank_b)
    if set(score_a) != set(score_b):
        return ["conjuntos de asset_id distintos"], []
    for i, ((aid_a, _), (aid_b, _)) in enumerate(zip(rank_a, rank_b)):
        if aid_a == aid_b:
            continue
        va, vb = score_a[aid_a], score_a[aid_b]
        if va is not None and vb is not None and \
                abs(va - vb) <= tolerance * max(1.0, abs(va)):
            warnings.append(
                f"pos {i}: {aid_a} vs {aid_b} (scores ~iguales, empate)")
        else:
            errors.append(
                f"pos {i}: asset {aid_a} (A) vs {aid_b} (B) — scores "
                f"{va!r} / {score_b.get(aid_b)!r}")
            break   # el primer desorden real invalida el resto
    return errors, warnings


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("url_a", help="URL SQLAlchemy del motor A (referencia, ej. MySQL)")
    ap.add_argument("url_b", help="URL SQLAlchemy del motor B (ej. PostgreSQL)")
    ap.add_argument("--tolerance", type=float, default=1e-6,
                    help="tolerancia relativa para sumas/scores (default 1e-6)")
    ap.add_argument("--top", type=int, default=0,
                    help="comparar solo las primeras N posiciones del ranking (0 = todas)")
    args = ap.parse_args()

    eng_a = sa.create_engine(args.url_a)
    eng_b = sa.create_engine(args.url_b)

    dyn_a, dyn_b = set(_dyn_tables(eng_a)), set(_dyn_tables(eng_b))
    only_a, only_b = sorted(dyn_a - dyn_b), sorted(dyn_b - dyn_a)
    common_dyn = sorted(dyn_a & dyn_b)

    failures = 0
    warns = 0

    def _fail(msg):
        nonlocal failures
        failures += 1
        print(f"[DIFF] {msg}")

    if only_a:
        _fail(f"tablas dinámicas solo en A: {', '.join(only_a)}")
    if only_b:
        _fail(f"tablas dinámicas solo en B: {', '.join(only_b)}")

    with eng_a.connect() as ca, eng_b.connect() as cb:
        # 1+2. Conteos y agregados por fecha
        for table in (*_FIXED_TABLES, *common_dyn):
            na, nb = _count(ca, table), _count(cb, table)
            if na != nb:
                _fail(f"{table}: {na} filas (A) vs {nb} (B)")
                continue
            vcol = _value_col(eng_a, table)
            has_date = any(c["name"] == "date"
                           for c in sa.inspect(eng_a).get_columns(table))
            if vcol and has_date:
                problems = compare_date_aggregates(
                    _date_aggregates(ca, table, vcol),
                    _date_aggregates(cb, table, vcol),
                    args.tolerance)
                for p in problems[:5]:
                    _fail(f"{table}: {p}")
                if len(problems) > 5:
                    _fail(f"{table}: ... y {len(problems) - 5} fechas más")
                if not problems:
                    print(f"[OK]   {table}: {na} filas, agregados por fecha coinciden")
            else:
                print(f"[OK]   {table}: {na} filas")

        # 3. Ranking por estrategia en la última fecha común
        for table in (t for t in common_dyn if t.startswith("strat_res_")):
            last_a = ca.execute(sa.text(f"SELECT MAX(date) FROM {table}")).scalar()
            last_b = cb.execute(sa.text(f"SELECT MAX(date) FROM {table}")).scalar()
            if last_a != last_b:
                _fail(f"{table}: última fecha {last_a} (A) vs {last_b} (B)")
                continue
            if last_a is None:
                continue
            ra, rb = _ranking(ca, table, last_a), _ranking(cb, table, last_a)
            if args.top:
                ra, rb = ra[:args.top], rb[:args.top]
            errors, warnings = compare_rankings(ra, rb, args.tolerance)
            for e in errors:
                _fail(f"{table} ranking {last_a}: {e}")
            for w in warnings[:5]:
                warns += 1
                print(f"[WARN] {table} ranking {last_a}: {w}")
            if not errors:
                print(f"[OK]   {table}: ranking de {last_a} coincide "
                      f"({len(ra)} activos{f', {len(warnings)} empates' if warnings else ''})")

    print()
    if failures:
        print(f"RESULTADO: {failures} diferencias ({warns} warnings) — SIN paridad")
        return 1
    print(f"RESULTADO: paridad OK ({warns} warnings de empates por precisión)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
