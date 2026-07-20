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

    if "--confirm" not in sys.argv:
        print("Esto eliminará indicadores, ratios fundamentales, señales,")
        print("resultados de estrategias, logs y las corridas guardadas de")
        print("backtest y cartera. Se conservan activos, precios, fuentes,")
        print("catálogos, definiciones, carteras y usuarios.")
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
