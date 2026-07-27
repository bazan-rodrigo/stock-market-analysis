"""
Valida un pack de señales/estrategias SIN base de datos y SIN levantar la app.

Es la herramienta que cierra el círculo del estándar (strategy_packs/SPEC.md):
quien escribe un pack —una persona o un modelo de lenguaje— puede iterar hasta
que salga limpio antes de mandarlo, en vez de descubrir los errores recién al
importarlo contra producción.

Uso:
    python scripts/validate_pack.py mi_pack.json
    python scripts/validate_pack.py mi_pack.json --catalog catalogo.json

El catálogo (botón «Catálogo» en la pantalla de Señales) es opcional pero
recomendado: sin él no se puede verificar que los indicadores existan ni que
los sectores/mercados del filtro estén cargados, y el script lo dice en vez de
dar un OK que no significa nada.

Salida: 0 si no hay errores, 1 si los hay. Los AVISOS no afectan el código de
salida — son trampas silenciosas (una señal que nunca puntúa, un ranking que
un solo activo puede dominar), no rechazos.
"""
import json
import os
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

# La consola de Windows usa cp1252 por defecto: sin esto los mensajes con
# tildes salen mal y los símbolos ✓/✗ directamente tumban el script.
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

# El validador es lógica pura, pero cuelga de módulos que importan la capa de
# base (app.database arma el engine al importarse). Se apunta a un sqlite
# inexistente: el engine se construye pero nunca se conecta, así que el archivo
# no llega a crearse. Tiene que ser un sqlite de ARCHIVO y no ':memory:' —
# el de memoria usa SingletonThreadPool, que no acepta los parámetros de pool
# que pasa app.database.
os.environ.setdefault(
    "DATABASE_URL",
    f"sqlite:///{Path(tempfile.gettempdir()) / 'pack_validator_stub.db'}")


def _load(path: Path) -> dict:
    try:
        return json.loads(path.read_text(encoding="utf-8-sig"))
    except FileNotFoundError:
        print(f"✗ no existe el archivo: {path}")
        raise SystemExit(2)
    except json.JSONDecodeError as exc:
        print(f"✗ {path.name}: JSON inválido en la línea {exc.lineno}, "
              f"columna {exc.colno}: {exc.msg}")
        raise SystemExit(1)


def main(argv: list[str]) -> int:
    from app.services import pack_service

    args = [a for a in argv if not a.startswith("--")]
    if not args:
        print(__doc__)
        return 2

    pack_path = Path(args[0])
    catalog = None
    if "--catalog" in argv:
        idx = argv.index("--catalog")
        if idx + 1 >= len(argv):
            print("✗ --catalog necesita la ruta del archivo de catálogo")
            return 2
        catalog = _load(Path(argv[idx + 1]))

    try:
        pack = pack_service.parse_pack(pack_path.read_bytes())
    except FileNotFoundError:
        print(f"✗ no existe el archivo: {pack_path}")
        return 2
    except pack_service.PackError as exc:
        print(f"✗ {pack_path.name}: {exc}")
        return 1

    resultado = pack_service.validate_pack(pack, catalog)

    nombre = pack.get("pack") or pack_path.stem
    print(f"Pack: {nombre}  "
          f"({len(pack.get('signals') or [])} señal(es), "
          f"{len(pack.get('strategies') or [])} estrategia(s))")
    print(f"Catálogo: {'sí' if catalog else 'NO — validación parcial'}")
    print()

    for error in resultado["errors"]:
        print(f"  ERROR  {error}")
    for aviso in resultado["warnings"]:
        print(f"  AVISO  {aviso}")
    if resultado["errors"] or resultado["warnings"]:
        print()

    print("Verificado: " + "; ".join(resultado["checked"]) + ".")
    if resultado["skipped"]:
        print("NO verificado (falta el catálogo): "
              + "; ".join(resultado["skipped"]) + ".")
    print()

    if resultado["errors"]:
        print(f"✗ {len(resultado['errors'])} error(es): el import lo "
              f"rechazaría entero (es todo-o-nada).")
        return 1
    if resultado["warnings"]:
        print(f"✓ Sin errores. {len(resultado['warnings'])} aviso(s): "
              f"revisá que sean deliberados.")
        return 0
    print("✓ Sin errores ni avisos.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
