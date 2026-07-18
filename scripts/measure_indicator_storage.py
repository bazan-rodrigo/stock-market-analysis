"""
Mide el footprint REAL de las tablas de indicadores (ind_*) y lo compara con
sig_*/strat_res_*/group_scores/current_indicator_values, para decidir con
NUMEROS si el refactor a tablas anchas por cadencia (ind_daily/weekly/monthly)
vale la pena.

READ-ONLY: solo SELECT/COUNT + information_schema/pg_catalog. No escribe, no
crea, no borra nada — seguro de correr contra la BD real.

Funciona en MariaDB/MySQL y en PostgreSQL (detecta el motor por engine.dialect).

Uso (en el Codespace, con la BD levantada):
    python scripts/measure_indicator_storage.py

Secciones de salida:
  1. Tamaño por tabla ind_* (datos vs indice, filas exactas, bytes/fila)
  2. Agregado por cadencia (diario tecnico / semanal / mensual / fundamental)
  3. Total ind_* + ratio datos/indice (¿domina el overhead de fila+indice?)
  4. Profundidad de historia (prices) + nro de activos con precios
  5. Normalizacion por activo + extrapolacion lineal a 10.000 activos
  6. Comparacion con current_indicator_values / sig_* / strat_res_* / group_scores
  7. Proyeccion del footprint con tablas anchas por cadencia + ahorro estimado

La proyeccion (7) es una ESTIMACION con supuestos explicitos; las secciones
1-6 son medicion directa.
"""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import sqlalchemy as sa

from app.database import engine, get_session
from app.models import Price
from app.models.indicator_definition import IndicatorDefinition

# Supuesto para la proyeccion (7): bytes "utiles" promedio por celda de valor
# (FLOAT=4-8 B; los VARCHAR(50) de trend_*/volatility_* guardan strings cortos
# ~15 B). Es el unico numero inventado; todo lo demas sale de la medicion.
_VALUE_BYTES_ASSUMED = 8


# ── helpers ──────────────────────────────────────────────────────────────────
def _is_mysql() -> bool:
    return engine.dialect.name in ("mysql", "mariadb")


def _fmt(nbytes) -> str:
    if not nbytes:
        return "        -"
    mb = nbytes / 1024 / 1024
    if mb >= 1024:
        return f"{mb / 1024:8.2f} GB"
    return f"{mb:8.1f} MB"


def _cadence(code: str) -> str:
    if code.startswith("fundamental_"):
        return "fundamental"
    if code.endswith("_weekly"):
        return "weekly"
    if code.endswith("_monthly"):
        return "monthly"
    return "daily"


def _quote(name: str) -> str:
    return f"`{name}`" if _is_mysql() else f'"{name}"'


def _all_table_sizes(s) -> list[tuple]:
    """[(name, approx_rows, data_bytes, index_bytes)] de TODAS las tablas del
    schema actual (una sola query barata; los tamaños son exactos, table_rows
    es aproximado y solo se usa para tablas que no contamos exacto)."""
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


# ── main ─────────────────────────────────────────────────────────────────────
def main() -> None:
    s = get_session()
    print(f"\nMotor: {engine.dialect.name}   |   script READ-ONLY\n")

    sizes = _all_table_sizes(s)
    by_name = {name: (approx, data, idx) for name, approx, data, idx in sizes}

    # Tablas ind_* de VALORES (excluye ind_asset_meta, que es cache de metadatos)
    ind_tables = sorted(
        n for n in by_name
        if n.startswith("ind_") and n != "ind_asset_meta"
    )

    if not ind_tables:
        print("No hay tablas ind_* en esta base. ¿Corriste el pipeline de "
              "indicadores? (sin datos no hay nada que medir)")
        return

    # ── 1. Por tabla ────────────────────────────────────────────────────────
    print("=" * 88)
    print("1. TAMAÑO POR TABLA ind_*  (filas exactas)")
    print("=" * 88)
    hdr = f"{'tabla':<34}{'cadencia':<12}{'filas':>13}  {'datos':>11}{'indice':>11}{'total':>11}  {'B/fila':>7}"
    print(hdr)
    print("-" * 88)

    per_cadence: dict[str, dict] = {}
    grand_rows = grand_data = grand_idx = 0
    rows_by_table: dict[str, int] = {}

    measured = []
    for name in ind_tables:
        _, data, idx = by_name[name]
        n = _exact_count(s, name)
        rows_by_table[name] = n
        cad = _cadence(name[len("ind_"):])
        total = data + idx
        bpr = (total / n) if n else 0
        measured.append((name, cad, n, data, idx, total, bpr))
        c = per_cadence.setdefault(cad, {"tables": 0, "rows": 0, "data": 0, "idx": 0})
        c["tables"] += 1
        c["rows"] += n
        c["data"] += data
        c["idx"] += idx
        grand_rows += n
        grand_data += data
        grand_idx += idx

    for name, cad, n, data, idx, total, bpr in sorted(
            measured, key=lambda r: r[5], reverse=True):
        print(f"{name:<34}{cad:<12}{n:>13,}  {_fmt(data)}{_fmt(idx)}{_fmt(total)}  {bpr:>6.0f}")

    # ── 2. Por cadencia ───────────────────────────────────────────────────────
    print("\n" + "=" * 88)
    print("2. AGREGADO POR CADENCIA")
    print("=" * 88)
    print(f"{'cadencia':<14}{'tablas':>7}{'filas':>15}  {'datos':>11}{'indice':>11}{'total':>11}{'% total':>9}")
    print("-" * 88)
    grand_total = grand_data + grand_idx
    for cad in ("daily", "weekly", "monthly", "fundamental"):
        c = per_cadence.get(cad)
        if not c:
            continue
        t = c["data"] + c["idx"]
        pct = (100 * t / grand_total) if grand_total else 0
        print(f"{cad:<14}{c['tables']:>7}{c['rows']:>15,}  "
              f"{_fmt(c['data'])}{_fmt(c['idx'])}{_fmt(t)}{pct:>8.1f}%")

    # ── 3. Total + ratio datos/indice ─────────────────────────────────────────
    print("\n" + "=" * 88)
    print("3. TOTAL ind_* + PESO DEL OVERHEAD")
    print("=" * 88)
    print(f"  Tablas ind_*:        {len(ind_tables)}")
    print(f"  Filas totales:       {grand_rows:,}")
    print(f"  Datos:               {_fmt(grand_data)}")
    print(f"  Indice (ix_date+PK): {_fmt(grand_idx)}")
    print(f"  TOTAL:               {_fmt(grand_total)}")
    if grand_data:
        print(f"  Ratio indice/datos:  {grand_idx / grand_data:.2f}  "
              f"(alto => el overhead de fila+indice domina => la tabla ancha "
              f"amortiza mucho)")

    # ── 4. Historia de precios ────────────────────────────────────────────────
    print("\n" + "=" * 88)
    print("4. PROFUNDIDAD DE HISTORIA (prices)")
    print("=" * 88)
    dmin, dmax, ndates = s.query(
        sa.func.min(Price.date), sa.func.max(Price.date),
        sa.func.count(sa.distinct(Price.date))
    ).one()
    n_assets = int(s.query(sa.func.count(sa.distinct(Price.asset_id))).scalar() or 0)
    print(f"  Activos con precios: {n_assets:,}")
    print(f"  Rango de fechas:     {dmin} .. {dmax}")
    print(f"  Fechas distintas:    {ndates:,}")

    # ── 5. Por activo + extrapolacion a 10.000 ────────────────────────────────
    print("\n" + "=" * 88)
    print("5. NORMALIZACION POR ACTIVO + EXTRAPOLACION LINEAL A 10.000")
    print("=" * 88)
    if n_assets:
        per_asset = grand_total / n_assets
        factor = 10_000 / n_assets
        print(f"  ind_* por activo:            {_fmt(per_asset)}  "
              f"({grand_rows / n_assets:,.0f} filas/activo)")
        print(f"  Proyeccion a 10.000 activos: {_fmt(grand_total * factor)}  "
              f"(x{factor:.1f}, supone misma profundidad de historia)")
        print("  Nota: si los activos nuevos entran con menos historia, es una "
              "cota superior.")

    # ── 6. Comparacion con otras tablas del pipeline ──────────────────────────
    print("\n" + "=" * 88)
    print("6. COMPARACION CON OTRAS TABLAS DEL PIPELINE")
    print("=" * 88)

    def _prefix_agg(prefix: str) -> tuple:
        names = [n for n in by_name if n.startswith(prefix)]
        data = sum(by_name[n][1] for n in names)
        idx = sum(by_name[n][2] for n in names)
        return len(names), data + idx

    for label, prefix in (("sig_* (una por señal)", "sig_"),
                          ("strat_res_* (una por estrategia)", "strat_res_")):
        cnt, tot = _prefix_agg(prefix)
        print(f"  {label:<36} {cnt:>3} tablas   {_fmt(tot)}")

    for tbl in ("current_indicator_values", "group_scores"):
        if tbl in by_name:
            data, idx = by_name[tbl][1], by_name[tbl][2]
            n = _exact_count(s, tbl)
            print(f"  {tbl:<36} {n:>13,} filas   {_fmt(data + idx)}")

    print(f"\n  >>> ind_* (los 3 anchos candidatos) = {_fmt(grand_total)} "
          f"({100 * grand_total / (grand_total + 1):.0f}% del bloque medido de indicadores)")

    # ── 7. Proyeccion tabla ancha por cadencia ────────────────────────────────
    print("\n" + "=" * 88)
    print("7. PROYECCION: TABLAS ANCHAS POR CADENCIA  (ESTIMACION)")
    print("=" * 88)
    print(f"  Supuesto: ~{_VALUE_BYTES_ASSUMED} B utiles por celda de valor. "
          f"El overhead de fila+indice se paga UNA vez por (activo,fecha)")
    print(f"  en la tabla ancha, en vez de una vez por cada codigo de la cadencia.\n")
    print(f"  {'cadencia':<14}{'codigos':>8}{'filas ancha':>14}  "
          f"{'actual':>11}{'proyectado':>12}{'ahorro':>11}{'x':>6}")
    print("  " + "-" * 84)

    total_now = total_proj = 0
    for cad in ("daily", "weekly", "monthly"):
        group = [(n, rows_by_table[n], by_name[n][1] + by_name[n][2])
                 for n in ind_tables if _cadence(n[len("ind_"):]) == cad]
        if not group:
            continue
        n_codes = len(group)
        cur_bytes = sum(g[2] for g in group)
        # filas de la tabla ancha ~ distinct (activo,fecha) de la cadencia
        # ~ la tabla mas poblada del grupo (todos los codigos comparten grilla)
        wide_rows = max(g[1] for g in group)
        # bytes/fila de la tabla mas grande = overhead + 1 valor + indice
        big = max(group, key=lambda g: g[2])
        rep_bpr = (big[2] / big[1]) if big[1] else 0
        overhead_idx = max(rep_bpr - _VALUE_BYTES_ASSUMED, 0)
        wide_bpr = overhead_idx + n_codes * _VALUE_BYTES_ASSUMED
        proj_bytes = wide_rows * wide_bpr
        saving = cur_bytes - proj_bytes
        ratio = (cur_bytes / proj_bytes) if proj_bytes else 0
        total_now += cur_bytes
        total_proj += proj_bytes
        print(f"  {cad:<14}{n_codes:>8}{wide_rows:>14,}  "
              f"{_fmt(cur_bytes)}{_fmt(proj_bytes)}{_fmt(saving)}{ratio:>5.1f}x")

    print("  " + "-" * 84)
    saving_tot = total_now - total_proj
    ratio_tot = (total_now / total_proj) if total_proj else 0
    print(f"  {'TOTAL tecnico':<14}{'':>8}{'':>14}  "
          f"{_fmt(total_now)}{_fmt(total_proj)}{_fmt(saving_tot)}{ratio_tot:>5.1f}x")
    if n_assets:
        print(f"\n  Ahorro proyectado a 10.000 activos (x{10_000 / n_assets:.1f}): "
              f"~{_fmt(saving_tot * 10_000 / n_assets)}")
    print("\n  (fundamentales quedan FUERA de la fase 1: son diarios pero los "
          "escribe otro servicio)\n")


if __name__ == "__main__":
    main()
