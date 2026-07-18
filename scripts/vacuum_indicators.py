"""Compacta las tablas del pipeline a demanda para recuperar espacio de tuplas
muertas (bloat): VACUUM FULL (PostgreSQL) / OPTIMIZE TABLE (MySQL/MariaDB).

NO borra datos — reescribe las tablas y devuelve el espacio al disco. Toma un
lock exclusivo por tabla mientras dura (mejor en un momento tranquilo). Ver
docs/notes/design_ind_wide_tables.md (qué es el bloat).

Uso (Codespace, o `railway run` contra prod):
    python scripts/vacuum_indicators.py            # tablas propensas a bloat
    python scripts/vacuum_indicators.py ind_daily ind_weekly   # tablas puntuales
"""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from app.services import maintenance_service


def _fmt(nbytes: int) -> str:
    mb = nbytes / 1024 / 1024
    return f"{mb / 1024:8.2f} GB" if mb >= 1024 else f"{mb:8.1f} MB"


def main() -> None:
    targets = [a for a in sys.argv[1:] if not a.startswith("-")]
    if targets:
        print(f"Compactando {len(targets)} tabla(s) puntual(es)...")
        res = maintenance_service.vacuum_tables(targets)
    else:
        tables = maintenance_service.bloat_tables()
        print(f"Compactando {len(tables)} tablas propensas a bloat...")
        res = maintenance_service.vacuum_tables(tables)

    print(f"\nMotor: {res['dialect']}\n")
    rows = sorted(res["tables"].items(), key=lambda kv: -(kv[1][0] - kv[1][1]))
    if rows:
        print(f"  {'tabla':<34}{'antes':>11}{'después':>11}{'liberado':>11}")
        print("  " + "-" * 66)
        for t, (before, after) in rows:
            print(f"  {t:<34}{_fmt(before)}{_fmt(after)}{_fmt(max(0, before - after))}")
    print(f"\nEspacio liberado total: {_fmt(res['freed_bytes'])}")


if __name__ == "__main__":
    main()
