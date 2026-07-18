"""Configuración de la suite.

Los tests cubren SOLO lógica pura (fórmulas, algoritmos, helpers): nunca se
conecta a la base. Para poder importar los servicios sin el driver de MySQL,
la DATABASE_URL se apunta a un stub sqlite ANTES de importar nada de app.
"""
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

# El stub es descartable: se borra en cada corrida para que create_all lo
# recree con el esquema ACTUAL de los modelos (create_all no altera tablas
# existentes — un stub viejo rompería la suite tras agregar una columna).
_STUB = ROOT / ".pytest-stub.db"
_STUB.unlink(missing_ok=True)

os.environ.setdefault("DATABASE_URL", f"sqlite:///{_STUB}")

# La suite corre contra el stub sqlite con tablas ind_{code} per-código: forzar
# el camino per-código (en prod el default de use_wide_ind_tables es wide desde
# la fase 5). Los tests de tablas anchas lo vuelven a "1" con monkeypatch.
os.environ["USE_WIDE_IND_TABLES"] = "0"
