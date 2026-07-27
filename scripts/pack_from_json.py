"""
Convierte un pack JSON (strategy_packs/SPEC.md) en las dos planillas Excel que
importa la app: `<pack>_senales.xlsx` y `<pack>_estrategia.xlsx`.

La app importa el JSON directamente, así que esto es opcional. Sirve para
publicar un pack en el formato histórico de `strategy_packs/`, o para revisar
y ajustar su contenido en una planilla antes de importarlo.

Uso:
    python scripts/pack_from_json.py mi_pack.json
    python scripts/pack_from_json.py mi_pack.json --out-dir strategy_packs

El nombre de los archivos sale del campo `pack` del JSON (o del nombre del
archivo, si no está). Valida antes de escribir: un pack con errores no genera
planillas.
"""
import json
import os
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

# Ver scripts/validate_pack.py: la consola de Windows es cp1252 y los símbolos
# ✓/✗ la tumban.
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

# Ver la nota de scripts/validate_pack.py: un sqlite que nunca se conecta, solo
# para poder importar los módulos sin tener una base a mano.
os.environ.setdefault(
    "DATABASE_URL",
    f"sqlite:///{Path(tempfile.gettempdir()) / 'pack_validator_stub.db'}")


def _write(path: Path, title: str, columns, rows: list[dict],
           extra_sheet=None) -> None:
    import openpyxl

    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = title
    ws.append(list(columns))
    for row in rows:
        ws.append([row.get(c) for c in columns])
    if extra_sheet:
        nombre, cols, filas = extra_sheet
        ws2 = wb.create_sheet(nombre)
        ws2.append(list(cols))
        for row in filas:
            ws2.append([row.get(c) for c in cols])
    wb.save(path)


def main(argv: list[str]) -> int:
    from app.services import pack_service

    args = [a for a in argv if not a.startswith("--")]
    if not args:
        print(__doc__)
        return 2

    pack_path = Path(args[0])
    out_dir = Path(argv[argv.index("--out-dir") + 1]) if "--out-dir" in argv \
        else pack_path.parent
    catalog = None
    if "--catalog" in argv:
        catalog = json.loads(
            Path(argv[argv.index("--catalog") + 1]).read_text(encoding="utf-8-sig"))

    try:
        pack = pack_service.parse_pack(pack_path.read_bytes())
    except FileNotFoundError:
        print(f"✗ no existe el archivo: {pack_path}")
        return 2
    except pack_service.PackError as exc:
        print(f"✗ {pack_path.name}: {exc}")
        return 1

    resultado = pack_service.validate_pack(pack, catalog)
    if resultado["errors"]:
        print(f"✗ el pack tiene {len(resultado['errors'])} error(es); no se "
              f"generan planillas. Corré scripts/validate_pack.py para verlos.")
        return 1

    nombre = pack.get("pack") or pack_path.stem
    out_dir.mkdir(parents=True, exist_ok=True)
    generados = []

    if pack.get("signals"):
        destino = out_dir / f"{nombre}_senales.xlsx"
        _write(destino, "Señales", pack_service.SIGNAL_COLUMNS,
               pack_service.signal_rows_from_pack(pack))
        generados.append(destino)

    if pack.get("strategies"):
        rows_s, rows_c = pack_service.strategy_rows_from_pack(pack)
        destino = out_dir / f"{nombre}_estrategia.xlsx"
        _write(destino, "Estrategias", pack_service.STRATEGY_COLUMNS, rows_s,
               extra_sheet=("Componentes", pack_service.COMPONENT_COLUMNS, rows_c))
        generados.append(destino)

    for g in generados:
        print(f"✓ {g}")
    if resultado["warnings"]:
        print(f"  ({len(resultado['warnings'])} aviso(s) — "
              f"corré validate_pack.py para verlos)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
