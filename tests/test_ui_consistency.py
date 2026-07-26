"""Trinquete del sistema de diseño — evita que la UI vuelva a derivar.

La app se armó por partes y cada pantalla fue eligiendo su propio verde, su
propio gris y su propio tamaño de título. Consolidar eso una vez no alcanza:
sin un test que lo sostenga, la próxima pantalla vuelve a copiar-pegar un
`#1f2937` y en unos meses estamos igual. Este archivo es esa red.

Reglas (todas con la misma forma: "lo que ya tiene nombre, se usa por su nombre"):

  1. Ningún color con constante se escribe a mano.
  2. El título de pantalla sale de `page_header()`, no de un html.H* propio.
  3. Todo módulo de UI importa sin NameError.
  4. El presupuesto de colores sueltos no crece.

Si agregás un color que el sistema no tiene, la respuesta correcta casi siempre
es sumarlo a `app/components/ui_constants.py` con un nombre que diga qué rol
cumple — no anotarlo en las excepciones de acá.
"""
import ast
import re
from collections import Counter
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
UI_DIRS = [ROOT / "app" / "pages", ROOT / "app" / "callbacks"]
UI_CONSTANTS = ROOT / "app" / "components" / "ui_constants.py"

HEX_RE = re.compile(r"#[0-9a-fA-F]{6}\b")

# ── Excepciones, todas con motivo ────────────────────────────────────────────
# El f-string JS de chart_callbacks: son colores de VELAS (convención de
# mercado: verde sube / rojo baja) dentro de JavaScript, no chrome de interfaz.
RANGOS_EXENTOS: dict[str, tuple[int, int]] = {
    "app/callbacks/chart_callbacks.py": (452, 1582),
}

# Colores de DATOS: el tono codifica un valor, no un estado de interfaz.
# Unificarlos destruiría información, así que no entran en la regla 1.
LINEAS_DE_DATOS = re.compile(
    r"marker|colorscale|_PALETTE|CHART_PALETTE|addLineSeries|upColor|downColor",
    re.I,
)

# TEMPORAL — estos archivos estaban modificados por otra sesión cuando se hizo
# la consolidación, así que quedaron afuera para no pisar ese trabajo. NO son
# una excepción de diseño: hay que pasarles los tres paquetes (colores a
# constantes, encabezado a page_header) y borrarlos de esta lista.
PENDIENTES_DE_CONSOLIDAR = {
    "app/pages/screener_signals.py",
    "app/callbacks/screener_signals_callbacks.py",
    "app/callbacks/price_viewer_callbacks.py",
}


def _fuentes(incluir_pendientes: bool = False):
    for d in UI_DIRS:
        for p in sorted(d.glob("*.py")):
            rel = p.relative_to(ROOT).as_posix()
            if rel in PENDIENTES_DE_CONSOLIDAR and not incluir_pendientes:
                continue
            yield rel, p.read_text(encoding="utf-8")


def _constantes_de_color() -> dict[str, str]:
    """{valor_hex: NOMBRE} de todo color con nombre en ui_constants."""
    arbol = ast.parse(UI_CONSTANTS.read_text(encoding="utf-8"))
    out = {}
    for nodo in arbol.body:
        if not isinstance(nodo, ast.Assign):
            continue
        if not (isinstance(nodo.value, ast.Constant)
                and isinstance(nodo.value.value, str)):
            continue
        valor = nodo.value.value
        if HEX_RE.fullmatch(valor):
            for t in nodo.targets:
                if isinstance(t, ast.Name):
                    out.setdefault(valor.lower(), t.id)
    return out


def _lineas_relevantes(rel: str, src: str):
    """(nro, texto) de las líneas donde aplica la regla de color."""
    rango = RANGOS_EXENTOS.get(rel)
    for i, linea in enumerate(src.splitlines(), start=1):
        if rango and rango[0] <= i <= rango[1]:
            continue
        if linea.lstrip().startswith("#"):
            continue
        if LINEAS_DE_DATOS.search(linea):
            continue
        yield i, linea


# ── Regla 1 ──────────────────────────────────────────────────────────────────

def test_ningun_color_con_constante_se_escribe_a_mano():
    """`#1f2937` a mano donde ya existe BG_CARD es cómo empezó la deriva."""
    constantes = _constantes_de_color()
    assert constantes, "ui_constants deberia definir colores con nombre"

    infracciones = []
    for rel, src in _fuentes():
        for nro, linea in _lineas_relevantes(rel, src):
            for hexa in HEX_RE.findall(linea):
                nombre = constantes.get(hexa.lower())
                if nombre:
                    infracciones.append(f"{rel}:{nro} → {hexa} es {nombre}")

    assert not infracciones, (
        "Colores escritos a mano que ya tienen constante en ui_constants.\n"
        "Importá la constante en vez de repetir el hex:\n  "
        + "\n  ".join(infracciones)
    )


# ── Regla 2 ──────────────────────────────────────────────────────────────────

_H_CON_HELP = re.compile(r"html\.H[1-6]\(\s*\[[^\]]*help_link\(", re.S)


def test_el_titulo_de_pantalla_sale_de_page_header():
    """Que cada pantalla eligiera su nivel de título (había H3/H4/H5/H6
    conviviendo) es lo que más se nota al navegar entre pantallas."""
    culpables = [rel for rel, src in _fuentes() if _H_CON_HELP.search(src)]
    assert not culpables, (
        "Estas pantallas arman el encabezado a mano en vez de usar "
        "page_header('Título', 'slug'):\n  " + "\n  ".join(culpables)
    )


# ── Regla 3 ──────────────────────────────────────────────────────────────────

def test_los_modulos_de_ui_importan_sin_nameerror():
    """Una sustitución masiva de colores puede dejar una constante usada sin
    importar: compila igual y explota recién al abrir la pantalla."""
    import importlib

    import dash

    try:
        dash.Dash(__name__, use_pages=True, pages_folder="")
    except Exception:
        pass  # ya instanciada por otro test

    fallan = []
    for rel, _ in _fuentes(incluir_pendientes=True):   # importar vale para todos
        mod = rel.removesuffix(".py").replace("/", ".")
        if mod.endswith(".__init__"):
            continue
        try:
            importlib.import_module(mod)
        except ModuleNotFoundError as e:
            # yfinance no está en la PC de desarrollo (ver CLAUDE.md)
            if "yfinance" not in str(e):
                fallan.append(f"{mod}: {e}")
        except Exception as e:
            fallan.append(f"{mod}: {type(e).__name__}: {e}")

    assert not fallan, "Módulos de UI que no importan:\n  " + "\n  ".join(fallan)


# ── Regla 4 ──────────────────────────────────────────────────────────────────
# Techo del estado tras la consolidación. Los que quedan son colores sin rol
# compartido (paletas del RRG, escala de tendencia, semáforos puntuales).
# Bajarlo cuando se consoliden más; subirlo solo con una razón escrita acá.
TECHO_COLORES_SUELTOS = 175


def test_el_presupuesto_de_colores_sueltos_no_crece():
    sueltos = Counter()
    for rel, src in _fuentes():
        for nro, linea in _lineas_relevantes(rel, src):
            for hexa in HEX_RE.findall(linea):
                sueltos[hexa.lower()] += 1

    total = sum(sueltos.values())
    assert total <= TECHO_COLORES_SUELTOS, (
        f"Hay {total} colores sueltos y el techo es {TECHO_COLORES_SUELTOS}.\n"
        "Si agregaste un color, dale un nombre en ui_constants.py en vez de "
        "escribirlo a mano.\nMás frecuentes: "
        + ", ".join(f"{c}×{n}" for c, n in sueltos.most_common(8))
    )
