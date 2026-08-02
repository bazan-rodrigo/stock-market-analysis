"""
Limpia datos derivados/operativos de la BD, preservando activos, precios,
fuentes de precio, catálogos, definiciones, carteras y usuarios.

Entrada de línea de comandos a `app/services/cleanup_service.py`, que define
el alcance y lo comparte con la pantalla /admin/cleanup. El alcance NO se
define acá: las dos entradas tenían su propia lista y divergieron (ver el
docstring del servicio).

Uso:
    python scripts/clean_data.py
    python scripts/clean_data.py --confirm   (sin pregunta interactiva)

    python scripts/clean_data.py --reset             (reinicio TOTAL a fábrica)
    python scripts/clean_data.py --reset --confirm   (sin pregunta interactiva)

El `--reset` es MUCHO más destructivo: deja la base como recién instalada
(reset_to_fresh_install) — borra TODO, incluido lo que la limpieza preserva
(activos, precios, catálogos, definiciones, carteras y usuarios), resiembra los
datos integrados y recrea admin/admin123.
"""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import logging

logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
logger = logging.getLogger(__name__)


if __name__ == "__main__":
    from app.services import cleanup_service

    if "--reset" in sys.argv:
        print("⚠ RESET TOTAL: deja la base COMO RECIÉN INSTALADA.")
        print("Borra TODO —activos, precios, catálogos, definiciones, señales,")
        print("estrategias, sintéticos, conversión, carteras y TODOS los")
        print("usuarios—, resiembra los datos de fábrica y recrea admin/admin123.")
        if "--confirm" not in sys.argv:
            resp = input("Escribí REINICIAR para confirmar: ").strip().upper()
            if resp != "REINICIAR":
                print("Cancelado.")
                sys.exit(0)
        try:
            res = cleanup_service.reset_to_fresh_install()
        except Exception as exc:
            logger.error("Error durante el reinicio a fábrica: %s", exc)
            raise
        print(f"Listo. Base reiniciada a fábrica: {len(res['tables'])} tablas "
              "vaciadas, datos integrados resembrados, admin/admin123 recreado.")
        sys.exit(0)

    if "--confirm" not in sys.argv:
        print("Esto eliminará indicadores, ratios fundamentales, señales,")
        print("resultados de estrategias, logs, el historial de corridas y las")
        print("corridas guardadas de backtest y cartera. Se conservan activos,")
        print("precios, fuentes, catálogos, definiciones, carteras y usuarios.")
        resp = input("¿Confirmar? (s/N): ").strip().lower()
        if resp != "s":
            print("Cancelado.")
            sys.exit(0)

    try:
        res = cleanup_service.clean_data()
    except Exception as exc:
        logger.error("Error durante la limpieza: %s", exc)
        raise
    print(f"Listo. {len(res['tables'])} tablas vaciadas.")
