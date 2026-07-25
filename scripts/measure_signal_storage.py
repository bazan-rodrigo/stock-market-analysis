"""
Mide el footprint REAL de las tablas de señales (sig_*) y estrategias
(strat_res_*) y proyecta cuánto ahorraría el refactor a TABLAS ANCHAS
(una columna por señal / dos por estrategia), para decidir con NUMEROS si
vale la pena — el mismo criterio con el que se midieron los indicadores
(scripts/measure_indicator_storage.py).

READ-ONLY por defecto: solo SELECT/COUNT + information_schema/pg_catalog. No
escribe, no crea, no borra nada — seguro de correr contra la BD real (Railway).

Funciona en MariaDB/MySQL y en PostgreSQL (detecta el motor por engine.dialect).

Uso:
    python scripts/measure_signal_storage.py
    python scripts/measure_signal_storage.py --exact-union   # cuenta la unión
        # real de (activo,fecha) de todas las sig_* (query PESADA: escanea
        # todas las filas de todas las tablas — correr con la app tranquila).

Secciones de salida:
  0. Tamaño total de la base (presupuesto de Railway)
  1. Tamaño por tabla sig_* / strat_res_* (datos vs índice, filas, B/fila)
  2. Agregado + ratio índice/datos (¿domina el overhead de fila+índice?)
  3. Proyección tabla ancha de SEÑALES + ahorro estimado
  4. Proyección tabla ancha de ESTRATEGIAS + ahorro estimado
  5. Ahorro combinado + extrapolación a 10.000 activos

Las secciones 3-5 son ESTIMACIONES con supuestos explícitos; 0-2 son medición
directa. El número real solo se conoce construyendo la ancha (fase de cutover).
"""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import sqlalchemy as sa

from app.database import engine, get_session
from app.models import Price

# Supuestos de la proyección (secciones 3-4): cada score/pct se guardaría en
# float4 (4 B) en la ancha — es donde float4 POR FIN rinde, porque varias
# columnas float empacan sin el padding MAXALIGN que anula el ahorro en una
# sig_* de un solo score (ver project_reduccion_footprint #4). El overhead de
# fila (header de tupla + null bitmap + asset_id + date) y los DOS índices se
# pagan UNA vez por (activo,fecha) en la ancha, en vez de una vez por señal.
_SIG_VALUE_BYTES   = 4        # score (float4)
_STRAT_VALUE_BYTES = 4        # score y pct, cada uno float4
_STRAT_COLS        = 2        # columnas por estrategia (score, pct)

# Techo de almacenamiento del plan de Railway (ajustar si cambia el plan).
_BUDGET_MB = 500


# ── helpers (calcados de measure_indicator_storage.py; scripts self-contained) ─
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
    """[(name, approx_rows, data_bytes, index_bytes)] de TODAS las tablas del
    schema (una query barata; los tamaños son exactos)."""
    if _is_mysql():
        rows = s.execute(sa.text(
            "SELECT table_name, table_rows, data_length, index_length "
            "FROM information_schema.tables "
            "WHERE table_schema = DATABASE()"
        )).fetchall()
    else:  # postgresql
        rows = s.execute(sa.text(
            "SELECT c.relname, c.reltuples::bigint, "
            "       pg_table_size(c.oid), pg_indexes_size(c.oid) "
            "FROM pg_class c "
            "JOIN pg_namespace n ON n.oid = c.relnamespace "
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
        "SELECT pg_database_size(current_database())"
    )).scalar() or 0)


def _exact_union_rows(s, names: list[str]) -> int:
    """COUNT(*) de la unión DISTINCT de (asset_id, date) de todas las tablas —
    la cantidad EXACTA de filas que tendría la ancha. Query pesada (escanea y
    deduplica todo); solo con --exact-union."""
    if not names:
        return 0
    parts = " UNION ".join(
        f"SELECT asset_id, date FROM {_quote(n)}" for n in names)
    return int(s.execute(sa.text(
        f"SELECT COUNT(*) FROM ({parts}) u")).scalar() or 0)


# ── proyección de una entidad ancha (señales o estrategias) ────────────────────
def _project_wide(label, tables, by_name, rows_by_table, *,
                  cols_per_entity, value_bytes, wide_rows_exact=None) -> tuple:
    """Imprime la proyección per-entidad → tabla ancha y devuelve
    (bytes_actuales, bytes_proyectados). tables: nombres de las per-entidad."""
    print("\n" + "=" * 88)
    print(f"{label}")
    print("=" * 88)
    if not tables:
        print("  (no hay tablas de esta clase en la base)")
        return 0, 0

    n_ent    = len(tables)
    cur      = sum(by_name[n][1] + by_name[n][2] for n in tables)
    rows_max = max(rows_by_table[n] for n in tables)   # cota inferior de la unión
    rows_sum = sum(rows_by_table[n] for n in tables)   # cota superior (sin dedup)

    # filas de la ancha ~ unión DISTINCT de (activo,fecha). Sin --exact-union se
    # usa el máximo (todas comparten casi la misma grilla: mismo calendario, y
    # el evaluador puntúa a casi todos los activos); la unión real cae entre max
    # y sum. Con --exact-union es el número exacto.
    wide_rows = wide_rows_exact if wide_rows_exact is not None else rows_max

    # bytes/fila representativo = overhead de fila + índices + los valores que
    # HOY guarda cada fila per-entidad. Se aísla el overhead+índice restándole
    # los value_bytes que ya trae, y se le suman los de TODAS las columnas de la
    # ancha. Una sola tabla ancha conserva UN par de índices (no n_ent pares).
    big     = max(tables, key=lambda n: by_name[n][1] + by_name[n][2])
    big_tot = by_name[big][1] + by_name[big][2]
    big_bpr = (big_tot / rows_by_table[big]) if rows_by_table[big] else 0
    cur_val_bytes = cols_per_entity * value_bytes          # lo que trae hoy la fila
    overhead_idx  = max(big_bpr - cur_val_bytes, 0)        # header + null bitmap + PK + ix
    wide_bpr      = overhead_idx + n_ent * cols_per_entity * value_bytes
    proj          = wide_rows * wide_bpr
    saving        = cur - proj
    ratio         = (cur / proj) if proj else 0

    print(f"  Entidades (tablas per-entidad):  {n_ent}")
    print(f"  Filas per-entidad (max/sum):     {rows_max:,} / {rows_sum:,}")
    src = "unión EXACTA" if wide_rows_exact is not None else "max (cota inf.)"
    print(f"  Filas de la ancha ({src}): {wide_rows:,}")
    print(f"  B/fila hoy (tabla mayor, c/índice): {big_bpr:.0f}   "
          f"→ overhead+índice aislado: {overhead_idx:.0f}")
    print(f"  B/fila ancha (overhead+índice + {n_ent}×{cols_per_entity}×{value_bytes} B): "
          f"{wide_bpr:.0f}")
    print("  " + "-" * 66)
    print(f"  Actual (suma per-entidad):  {_fmt(cur)}")
    print(f"  Proyectado (una ancha):     {_fmt(proj)}")
    print(f"  Ahorro:                     {_fmt(saving)}   ({ratio:.1f}x)")
    return cur, proj


# ── main ───────────────────────────────────────────────────────────────────────
def main(exact_union: bool = False) -> None:
    s = get_session()
    print(f"\nMotor: {engine.dialect.name}   |   script READ-ONLY"
          f"{'  |  --exact-union (query pesada)' if exact_union else ''}\n")

    sizes = _all_table_sizes(s)
    by_name = {name: (approx, data, idx) for name, approx, data, idx in sizes}

    sig_tables   = sorted(n for n in by_name if n.startswith("sig_"))
    strat_tables = sorted(n for n in by_name if n.startswith("strat_res_"))

    # ── 0. Presupuesto de Railway ─────────────────────────────────────────────
    total_db = _total_db_bytes(s)
    budget_bytes = _BUDGET_MB * 1024 * 1024
    print("=" * 88)
    print(f"0. TAMAÑO TOTAL DE LA BASE  (presupuesto ~{_BUDGET_MB} MB)")
    print("=" * 88)
    print(f"  Base completa: {_fmt(total_db)}   "
          f"({100 * total_db / budget_bytes:.1f}% de {_BUDGET_MB} MB)")
    print("  Top 15 tablas por tamaño:")
    print(f"  {'tabla':<40}{'total':>11}")
    print("  " + "-" * 52)
    for name, _a, data, idx in sorted(
            sizes, key=lambda r: r[2] + r[3], reverse=True)[:15]:
        print(f"  {name:<40}{_fmt(data + idx):>11}")

    if not sig_tables and not strat_tables:
        print("\nNo hay tablas sig_*/strat_res_* en esta base. ¿Corriste el "
              "backfill de señales/estrategias? (sin datos no hay qué medir)")
        return

    # ── 1. Por tabla ──────────────────────────────────────────────────────────
    print("\n" + "=" * 88)
    print("1. TAMAÑO POR TABLA sig_* / strat_res_*  (filas exactas)")
    print("=" * 88)
    print(f"{'tabla':<24}{'filas':>15}  {'datos':>11}{'índice':>11}"
          f"{'total':>11}  {'B/fila':>7}  {'idx/dat':>8}")
    print("-" * 88)

    rows_by_table: dict[str, int] = {}
    for name in sig_tables + strat_tables:
        _, data, idx = by_name[name]
        n = _exact_count(s, name)
        rows_by_table[name] = n
        total = data + idx
        bpr = (total / n) if n else 0
        r_id = (idx / data) if data else 0
        print(f"{name:<24}{n:>15,}  {_fmt(data)}{_fmt(idx)}{_fmt(total)}  "
              f"{bpr:>6.0f}  {r_id:>7.2f}")

    # ── 2. Agregado + ratio índice/datos ──────────────────────────────────────
    print("\n" + "=" * 88)
    print("2. AGREGADO + PESO DEL OVERHEAD  (índice/datos alto ⇒ la ancha "
          "amortiza mucho)")
    print("=" * 88)
    for label, tables in (("Señales (sig_*)", sig_tables),
                          ("Estrategias (strat_res_*)", strat_tables)):
        if not tables:
            continue
        data = sum(by_name[n][1] for n in tables)
        idx = sum(by_name[n][2] for n in tables)
        tot = data + idx
        r = (idx / data) if data else 0
        pct = (100 * tot / total_db) if total_db else 0
        print(f"  {label:<28} {len(tables):>3} tablas   "
              f"datos {_fmt(data)}  índice {_fmt(idx)}  total {_fmt(tot)}  "
              f"idx/dat {r:.2f}  ({pct:.1f}% base)")

    # ── 3-4. Proyecciones ancha ────────────────────────────────────────────────
    sig_union = (_exact_union_rows(s, sig_tables)
                 if exact_union and sig_tables else None)
    strat_union = (_exact_union_rows(s, strat_tables)
                   if exact_union and strat_tables else None)

    sig_cur, sig_proj = _project_wide(
        "3. PROYECCIÓN: TABLA ANCHA DE SEÑALES  (ESTIMACIÓN)",
        sig_tables, by_name, rows_by_table,
        cols_per_entity=1, value_bytes=_SIG_VALUE_BYTES,
        wide_rows_exact=sig_union)

    strat_cur, strat_proj = _project_wide(
        "4. PROYECCIÓN: TABLA ANCHA DE ESTRATEGIAS  (ESTIMACIÓN)",
        strat_tables, by_name, rows_by_table,
        cols_per_entity=_STRAT_COLS, value_bytes=_STRAT_VALUE_BYTES,
        wide_rows_exact=strat_union)

    # ── 5. Combinado + extrapolación ──────────────────────────────────────────
    print("\n" + "=" * 88)
    print("5. AHORRO COMBINADO + EXTRAPOLACIÓN A 10.000 ACTIVOS")
    print("=" * 88)
    cur = sig_cur + strat_cur
    proj = sig_proj + strat_proj
    saving = cur - proj
    ratio = (cur / proj) if proj else 0
    print(f"  Actual (sig_* + strat_res_*):   {_fmt(cur)}")
    print(f"  Proyectado (2 anchas):          {_fmt(proj)}")
    print(f"  Ahorro:                         {_fmt(saving)}   ({ratio:.1f}x)")
    print(f"  Base tras el refactor (aprox):  {_fmt(total_db - saving)}   "
          f"({100 * (total_db - saving) / budget_bytes:.1f}% de {_BUDGET_MB} MB)")

    n_assets = int(s.query(sa.func.count(sa.distinct(Price.asset_id))).scalar() or 0)
    if n_assets:
        factor = 10_000 / n_assets
        print(f"\n  Activos con precios: {n_assets:,}")
        print(f"  Ahorro proyectado a 10.000 activos (x{factor:.1f}): "
              f"~{_fmt(saving * factor)}")
        print("  Nota: el ahorro CRECE con la cantidad de señales/estrategias "
              "(más columnas ⇒ más amortización del overhead).")

    print("\n  Recordá: 3-5 son ESTIMACIONES; el número real se confirma "
          "construyendo la ancha en el cutover (migración de pivot).\n")


if __name__ == "__main__":
    main(exact_union="--exact-union" in sys.argv)
