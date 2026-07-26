"""
Mide el footprint REAL de las tablas ANCHAS de señales (signal_values_wide) y
estrategias (strategy_results_wide) — el estado post-cutover
(docs/notes/design_sig_wide_tables.md). Muestra cuántas columnas de valor tiene
cada una (= cuántas señales / estrategias), el split dato/índice, y la economía
marginal (lo que cuesta una señal en la ancha vs lo que costaba una tabla propia
sig_{id}). Sirve para detectar bloat o escrituras de más sin queries manuales.

Si la base todavía tiene tablas per-entidad sig_*/strat_res_* (pre-cutover),
además las mide y PROYECTA el ahorro de la ancha (compatibilidad hacia atrás).

READ-ONLY: solo SELECT/COUNT + information_schema/pg_catalog. No escribe, no crea,
no borra nada — seguro contra la BD real (Railway). MariaDB/MySQL y PostgreSQL.

Uso:
    python scripts/measure_signal_storage.py

Secciones:
  0. Tamaño total de la base (presupuesto de Railway)
  1. Tablas ANCHAS: filas, dato vs índice, B/fila, nº de columnas de valor
  2. Economía marginal (costo de una señal/estrategia en la ancha vs per-entidad)
  3. (solo si quedan tablas per-entidad) medición + proyección al modelo ancho
"""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import sqlalchemy as sa

from app.database import engine, get_session
from app.models import Price

SIG_WIDE   = "signal_values_wide"
STRAT_WIDE = "strategy_results_wide"

# Costo medido de UNA tabla per-entidad (sig_{id}/strat_res_{id}) por fila, con
# sus 2 índices: ~89 B/fila (medido en Railway pre-cutover, ver
# project_reduccion_footprint). La mitad es índice. Base de la comparación
# marginal "una señal en la ancha (~4 B/fila) vs una tabla propia (~89 B/fila)".
_PERCODE_BYTES_PER_ROW = 89
_FLOAT4_BYTES = 4            # una columna de valor en la ancha (score/pct float4)

_BUDGET_MB = 500


# ── helpers ────────────────────────────────────────────────────────────────────
def _is_mysql() -> bool:
    return engine.dialect.name in ("mysql", "mariadb")


def _fmt(nbytes) -> str:
    if not nbytes:
        return "        -"
    mb = nbytes / 1024 / 1024
    if mb >= 1024:
        return f"{mb / 1024:8.2f} GB"
    return f"{mb:8.1f} MB"


def _quote(name: str) -> str:
    return f"`{name}`" if _is_mysql() else f'"{name}"'


def _all_table_sizes(s) -> list[tuple]:
    if _is_mysql():
        rows = s.execute(sa.text(
            "SELECT table_name, table_rows, data_length, index_length "
            "FROM information_schema.tables WHERE table_schema = DATABASE()"
        )).fetchall()
    else:
        rows = s.execute(sa.text(
            "SELECT c.relname, c.reltuples::bigint, "
            "       pg_table_size(c.oid), pg_indexes_size(c.oid) "
            "FROM pg_class c JOIN pg_namespace n ON n.oid = c.relnamespace "
            "WHERE n.nspname = current_schema() AND c.relkind = 'r'"
        )).fetchall()
    return [(r[0], int(r[1] or 0), int(r[2] or 0), int(r[3] or 0)) for r in rows]


def _exact_count(s, name: str) -> int:
    return int(s.execute(sa.text(f"SELECT COUNT(*) FROM {_quote(name)}")).scalar() or 0)


def _total_db_bytes(s) -> int:
    if _is_mysql():
        return int(s.execute(sa.text(
            "SELECT COALESCE(SUM(data_length + index_length), 0) "
            "FROM information_schema.tables WHERE table_schema = DATABASE()"
        )).scalar() or 0)
    return int(s.execute(sa.text(
        "SELECT pg_database_size(current_database())")).scalar() or 0)


def _value_columns(table: str) -> list[str]:
    """Columnas de valor de una tabla ancha (todas menos asset_id, date)."""
    return [c["name"] for c in sa.inspect(engine).get_columns(table)
            if c["name"] not in ("asset_id", "date")]


# ── secciones ───────────────────────────────────────────────────────────────────
def _report_wide(s, by_name, table, entity, cols_per_entity, total_db):
    """Mide una tabla ancha y estima la economía vs per-entidad."""
    _, data, idx = by_name[table]
    total = data + idx
    rows = _exact_count(s, table)
    vcols = _value_columns(table)
    n_val = len(vcols)
    n_ent = n_val // cols_per_entity
    bpr = (total / rows) if rows else 0
    r_id = (idx / data) if data else 0
    pct = (100 * total / total_db) if total_db else 0

    print("\n" + "=" * 88)
    print(f"1. TABLA ANCHA: {table}")
    print("=" * 88)
    print(f"  {entity.capitalize()}s (columnas de valor): {n_ent}"
          f"  ({n_val} columnas, {cols_per_entity} por {entity})")
    print(f"  Filas:               {rows:,}")
    print(f"  Datos:               {_fmt(data)}")
    print(f"  Índice:              {_fmt(idx)}")
    print(f"  TOTAL:               {_fmt(total)}   ({pct:.1f}% de la base)")
    print(f"  B/fila:              {bpr:.0f}")
    print(f"  Índice/datos:        {r_id:.2f}  "
          f"(alto ⇒ el overhead de fila+índice —pagado UNA vez— domina)")

    if not n_ent or not rows:
        return
    # Marginal: una columna float4 más ≈ rows × 4 B. Una tabla per-entidad ≈
    # rows × 89 B (dato + 2 índices propios). El ahorro está en el overhead que
    # la ancha paga una sola vez.
    wide_marginal = rows * _FLOAT4_BYTES * cols_per_entity
    perentidad_1  = rows * _PERCODE_BYTES_PER_ROW
    perentidad_all = perentidad_1 * n_ent
    print("\n  Economía (estimación, base ~89 B/fila per-entidad medido):")
    print(f"    · Cada {entity} en la ancha:   ~{_fmt(wide_marginal)}  "
          f"({cols_per_entity} col float4 × {rows:,} filas)")
    print(f"    · Cada {entity} en per-entidad: ~{_fmt(perentidad_1 * cols_per_entity)}  "
          f"(una tabla propia con sus 2 índices)")
    ratio = (perentidad_all / total) if total else 0
    print(f"    · {n_ent} {entity}(s) HOY: {_fmt(total)} ancha  vs  "
          f"~{_fmt(perentidad_all)} per-entidad  (~{ratio:.1f}×)")


def _percode_projection(s, by_name, total_db):
    """Compatibilidad pre-cutover: si quedan tablas per-entidad, medirlas."""
    def _agg(prefix):
        names = [n for n in by_name if n.startswith(prefix)]
        data = sum(by_name[n][1] for n in names)
        idx = sum(by_name[n][2] for n in names)
        return names, data + idx

    sig_names, sig_tot = _agg("sig_")
    strat_names, strat_tot = _agg("strat_res_")
    if not sig_names and not strat_names:
        return
    print("\n" + "=" * 88)
    print("3. TABLAS PER-ENTIDAD TODAVÍA PRESENTES (pre-cutover)")
    print("=" * 88)
    if sig_names:
        print(f"  sig_*:        {len(sig_names):>3} tablas   {_fmt(sig_tot)}")
    if strat_names:
        print(f"  strat_res_*:  {len(strat_names):>3} tablas   {_fmt(strat_tot)}")
    print("  (el cutover a las anchas todavía no dropeó estas — migración 0094)")


# ── main ─────────────────────────────────────────────────────────────────────
def main() -> None:
    s = get_session()
    print(f"\nMotor: {engine.dialect.name}   |   script READ-ONLY\n")

    sizes = _all_table_sizes(s)
    by_name = {name: (a, d, i) for name, a, d, i in sizes}
    total_db = _total_db_bytes(s)
    budget = _BUDGET_MB * 1024 * 1024

    print("=" * 88)
    print(f"0. TAMAÑO TOTAL DE LA BASE  (presupuesto ~{_BUDGET_MB} MB)")
    print("=" * 88)
    print(f"  Base completa: {_fmt(total_db)}   "
          f"({100 * total_db / budget:.1f}% de {_BUDGET_MB} MB)")
    print("  Top 12 tablas por tamaño:")
    for name, _a, data, idx in sorted(
            sizes, key=lambda r: r[2] + r[3], reverse=True)[:12]:
        print(f"    {name:<34}{_fmt(data + idx):>11}")

    have_wide = False
    for table, entity, cpe in ((SIG_WIDE, "señal", 1),
                               (STRAT_WIDE, "estrategia", 2)):
        if table in by_name:
            have_wide = True
            _report_wide(s, by_name, table, entity, cpe, total_db)

    _percode_projection(s, by_name, total_db)

    if not have_wide and not any(
            n.startswith(("sig_", "strat_res_")) for n in by_name):
        print("\nNo hay tablas de señal/estrategia (ni anchas ni per-entidad). "
              "¿Corriste el backfill? (sin datos no hay qué medir)")
        return

    n_assets = int(s.query(sa.func.count(sa.distinct(Price.asset_id))).scalar() or 0)
    if have_wide and n_assets:
        print("\n" + "=" * 88)
        print(f"  Activos con precios: {n_assets:,}   "
              f"(el ahorro CRECE con la cantidad de señales/estrategias)")
    print()


if __name__ == "__main__":
    main()
