"""
Convierte las dos planillas de un pack (`<pack>_senales.xlsx` +
`<pack>_estrategia.xlsx`) en el pack JSON del estándar — la inversa de
`scripts/pack_from_json.py`.

El JSON es el formato canónico de `strategy_packs/SPEC.md`: es el que se sube
a la pantalla Packs, el que se le entrega a quien escribe un pack afuera del
sistema y el único que se puede leer y diffear a mano. Esto sirve para pasar al
canónico lo que solo existe como planilla — los packs históricos de
`strategy_packs/`, o lo que exportó la app desde las pantallas de Señales y
Estrategias.

Uso:
    python scripts/pack_to_json.py strategy_packs/pullback
    python scripts/pack_to_json.py pullback_senales.xlsx pullback_estrategia.xlsx
    python scripts/pack_to_json.py strategy_packs/pullback --out otro/lado.json

Un prefijo (sin `.xlsx`) busca los dos archivos con la nomenclatura del
directorio. Se puede convertir una sola planilla: el pack resultante trae solo
esa mitad, y el validador avisa lo que falte.

Valida el resultado antes de escribir. Con `--catalog catalogo.json` verifica
además indicadores y sectores contra esa instalación; sin él, solo la forma.
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


def _json_legible(obj, sangria: int = 0) -> str:
    """`json.dumps(indent=2)` pero sin partir en cuatro líneas cada par
    `[límite, puntaje]`: las listas de escalares quedan en una sola.

    Es presentación, no formato: el archivo parsea igual. Importa porque el
    JSON es el formato que se lee, se edita y se diffea a mano — un pack con
    thresholds explotados verticalmente es ilegible justo en la parte que más
    se revisa.
    """
    pad = " " * sangria
    if isinstance(obj, dict):
        if not obj:
            return "{}"
        cuerpo = ",\n".join(
            f"{pad}  {json.dumps(str(k), ensure_ascii=False)}: "
            f"{_json_legible(v, sangria + 2)}" for k, v in obj.items())
        return "{\n" + cuerpo + f"\n{pad}}}"
    if isinstance(obj, list):
        if not obj:
            return "[]"
        if all(not isinstance(x, (dict, list)) for x in obj):
            return json.dumps(obj, ensure_ascii=False)
        cuerpo = ",\n".join(f"{pad}  {_json_legible(v, sangria + 2)}"
                            for v in obj)
        return "[\n" + cuerpo + f"\n{pad}]"
    return json.dumps(obj, ensure_ascii=False)


def _planillas(args: list[str]) -> tuple[Path | None, Path | None, str]:
    """Argumentos → (planilla de señales, planilla de estrategia, nombre)."""
    if len(args) == 1 and not args[0].lower().endswith((".xlsx", ".xlsm", ".xls")):
        base = Path(args[0])
        senales = base.with_name(f"{base.name}_senales.xlsx")
        estrategia = base.with_name(f"{base.name}_estrategia.xlsx")
        return (senales if senales.exists() else None,
                estrategia if estrategia.exists() else None,
                base.name)

    senales = estrategia = None
    for a in args:
        path = Path(a)
        # Por nomenclatura cuando la hay; si no, por contenido más abajo.
        if "_senales" in path.stem.lower():
            senales = path
        elif "_estrategia" in path.stem.lower():
            estrategia = path
        elif senales is None:
            senales = path
        else:
            estrategia = path
    nombre = (senales or estrategia).stem
    for sufijo in ("_senales", "_estrategia"):
        nombre = nombre.replace(sufijo, "")
    return senales, estrategia, nombre


def main(argv: list[str]) -> int:
    from app.services import pack_service, signal_service, strategy_service

    args = []
    saltear = False
    for i, a in enumerate(argv):
        if saltear:
            saltear = False
            continue
        if a.startswith("--"):
            saltear = a in ("--out", "--catalog")
            continue
        args.append(a)

    if not args:
        print(__doc__)
        return 2

    senales, estrategia, nombre = _planillas(args)
    if senales is None and estrategia is None:
        print(f"✗ no se encontró ninguna planilla para '{args[0]}' "
              f"(se buscan <pack>_senales.xlsx y <pack>_estrategia.xlsx)")
        return 2

    catalog = None
    if "--catalog" in argv:
        catalog = json.loads(
            Path(argv[argv.index("--catalog") + 1]).read_text(encoding="utf-8-sig"))

    filas_s = filas_e = filas_c = None
    try:
        if senales is not None:
            filas_s = signal_service._signal_rows_from_xlsx(senales.read_bytes())
        if estrategia is not None:
            filas_e, filas_c = strategy_service._strategy_rows_from_xlsx(
                estrategia.read_bytes())
            if filas_e is None:                       # planilla equivocada
                print(f"✗ {estrategia.name}: {filas_c[0]['detail']}")
                return 1
    except (ValueError, OSError) as exc:
        print(f"✗ no se pudieron leer las planillas: {exc}")
        return 1

    try:
        pack = pack_service.pack_from_rows(filas_s, filas_e, filas_c, name=nombre)
    except pack_service.PackError as exc:
        print(f"✗ {exc}")
        return 1

    resultado = pack_service.validate_pack(pack, catalog)
    if resultado["errors"]:
        print(f"✗ lo convertido tiene {len(resultado['errors'])} error(es); no "
              f"se escribe nada:")
        for e in resultado["errors"]:
            print(f"    · {e}")
        return 1

    texto = _json_legible(pack) + "\n"
    # El serializador es casero: antes de escribir, que lo que sale parsee
    # exactamente al mismo objeto. Un pack corrupto acá se publica y se copia.
    if json.loads(texto) != pack:
        print("✗ error interno: el JSON generado no reproduce el pack")
        return 1

    destino = (Path(argv[argv.index("--out") + 1]) if "--out" in argv
               else (senales or estrategia).with_name(f"{nombre}.json"))
    destino.parent.mkdir(parents=True, exist_ok=True)
    destino.write_text(texto, encoding="utf-8")

    print(f"✓ {destino}")
    for aviso in resultado["warnings"]:
        print(f"  AVISO: {aviso}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
