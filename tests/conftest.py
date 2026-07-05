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

os.environ.setdefault("DATABASE_URL", f"sqlite:///{ROOT / '.pytest-stub.db'}")
