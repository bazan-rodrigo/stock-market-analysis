"""Toda pantalla y módulo de callbacks debe registrarse A MANO en
app/__init__.py: la app usa pages_folder="" (sin auto-discovery), así que
crear el archivo no alcanza — si el módulo no está en la lista, la ruta da
404 silenciosamente (pasó con /backtest, jul-2026).

Este test ata el filesystem a las listas _PAGES/_CALLBACKS: agregar una
pantalla nueva sin registrarla rompe la suite acá, no en producción.
"""
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
_INIT_SRC = (ROOT / "app" / "__init__.py").read_text(encoding="utf-8")


def _module_names(package: str) -> list[str]:
    return sorted(p.stem for p in (ROOT / "app" / package).glob("*.py")
                  if p.stem != "__init__")


def test_toda_pagina_esta_en_la_lista_de_pages():
    faltantes = []
    for name in _module_names("pages"):
        src = (ROOT / "app" / "pages" / f"{name}.py").read_text(encoding="utf-8")
        if not re.search(r"\bregister_page\(", src):
            continue  # módulo auxiliar sin ruta propia
        if f'"app.pages.{name}"' not in _INIT_SRC:
            faltantes.append(name)
    assert not faltantes, (
        f"Páginas sin registrar en _PAGES de app/__init__.py (su ruta da "
        f"404): {faltantes}. La app no auto-descubre páginas "
        f'(pages_folder="") — hay que agregarlas a la lista.')


def test_todo_modulo_de_callbacks_esta_en_la_lista():
    faltantes = [name for name in _module_names("callbacks")
                 if f'"app.callbacks.{name}"' not in _INIT_SRC]
    assert not faltantes, (
        f"Módulos sin registrar en _CALLBACKS de app/__init__.py (sus "
        f"callbacks nunca se cargan): {faltantes}.")
